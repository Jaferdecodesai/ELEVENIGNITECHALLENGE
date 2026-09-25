from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .domain import AuditEvent, CaseRecord, PreauthInput


@dataclass(frozen=True)
class EngineData:
    providers: dict[str, dict[str, Any]]
    policies: dict[str, dict[str, Any]]


class PreauthEngine:
    """Deterministic intake and recommendation engine.

    The engine can prepare a recommendation but has no method that issues a
    final outcome. A separate authenticated human action is required.
    """

    def __init__(self, providers: dict[str, dict[str, Any]], policies: dict[str, dict[str, Any]]):
        self.data = EngineData(providers=providers, policies=policies)

    def evaluate(self, request: PreauthInput) -> CaseRecord:
        case = CaseRecord(
            case_id=f"CASE-{uuid4().hex[:10].upper()}",
            request=request,
            status="intake_received",
            recommendation=None,
            rationale="Request received; no outcome issued.",
            source=None,
        )
        case.audit.append(AuditEvent("intake_received", "voice_agent", details={"language": request.language}))

        if not request.disclosure_acknowledged or not request.recording_consent:
            return self._stop(
                case,
                "consent_required",
                "Disclosure or recording consent is missing. Automation stops before case processing.",
            )

        provider = self.data.providers.get(request.clinic_id)
        if not provider or not provider.get("active"):
            return self._stop(
                case,
                "authentication_failed",
                "Clinic is not active in the synthetic provider directory. No policy lookup was performed.",
            )
        if provider.get("registered_number") != request.callback_number:
            return self._stop(
                case,
                "authentication_failed",
                "Callback number does not match the synthetic provider directory.",
            )
        case.audit.append(AuditEvent("clinic_authenticated", "provider_directory", details={"clinic_id": request.clinic_id}))

        if request.urgency == "emergency":
            return self._stop(
                case,
                "human_escalation",
                "Emergency indicators are outside the routine pre-authorisation workflow.",
            )

        policy = self.data.policies.get(request.policy_id)
        if not policy:
            return self._stop(case, "human_escalation", "No synthetic policy version matched the request.")
        rule = policy.get("procedures", {}).get(request.procedure_code)
        if not rule:
            return self._stop(
                case,
                "human_escalation",
                "Procedure is not represented in the synthetic ruleset; a qualified reviewer must assess it.",
            )

        source = f"{policy['source']}, {rule['clause']} (version {policy['version']})"
        case.source = source
        case.audit.append(
            AuditEvent(
                "rule_retrieved",
                "rules_lookup",
                details={"policy_id": request.policy_id, "procedure_code": request.procedure_code, "source": source},
            )
        )

        required_documents = set(rule.get("required_documents", []))
        missing = sorted(required_documents - set(request.documents))
        if missing:
            case.missing_documents = missing
            return self._stop(
                case,
                "needs_evidence",
                f"Required synthetic evidence is missing: {', '.join(missing)}.",
            )

        prefixes = tuple(rule.get("diagnosis_prefixes", []))
        if prefixes and not request.diagnosis_code.startswith(prefixes):
            return self._stop(
                case,
                "human_escalation",
                "Diagnosis and procedure do not match the synthetic rule; no recommendation is issued.",
            )

        if request.cost_aed > float(rule["max_cost_aed"]):
            return self._stop(
                case,
                "human_escalation",
                "Requested amount exceeds the synthetic rule threshold; manual review is required.",
            )

        case.status = "approval_ready"
        case.recommendation = "approve"
        case.rationale = "Synthetic rules matched and required evidence is present. Awaiting qualified employee decision."
        case.audit.append(
            AuditEvent(
                "recommendation_prepared",
                "voice_agent",
                details={"recommendation": "approve", "source": source, "human_gate": True},
            )
        )
        return case

    @staticmethod
    def _stop(case: CaseRecord, status: str, rationale: str) -> CaseRecord:
        case.status = status
        case.recommendation = None
        case.rationale = rationale
        case.audit.append(AuditEvent(status, "workflow", details={"outcome_issued": False}))
        return case
