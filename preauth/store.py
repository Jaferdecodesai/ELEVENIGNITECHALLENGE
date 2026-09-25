from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any

from .domain import AuditEvent, CaseRecord


class CaseStore:
    def __init__(self, audit_path: Path | None = None):
        self._cases: dict[str, CaseRecord] = {}
        self._lock = Lock()
        self.audit_path = audit_path

    def add(self, case: CaseRecord) -> CaseRecord:
        with self._lock:
            self._cases[case.case_id] = case
            self._write_audit(case, "case_created")
        return case

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            cases = sorted(self._cases.values(), key=lambda item: item.created_at, reverse=True)
            return [case.to_dict() for case in cases]

    def get(self, case_id: str) -> CaseRecord | None:
        with self._lock:
            return self._cases.get(case_id)

    def decide(self, case_id: str, decision: str, reason: str, approver: str) -> CaseRecord:
        if decision not in {"approve", "deny", "escalate"}:
            raise ValueError("decision must be approve, deny, or escalate")
        if len(reason.strip()) < 8:
            raise ValueError("a specific human rationale of at least 8 characters is required")
        if not approver.strip():
            raise ValueError("approver identity is required")

        with self._lock:
            case = self._cases.get(case_id)
            if not case:
                raise KeyError(case_id)
            if case.human_decision:
                raise ValueError("case already has a human decision")
            if case.status not in {"approval_ready", "needs_evidence", "human_escalation"}:
                raise ValueError(f"case in status {case.status} cannot be decided")
            if decision == "approve" and case.status != "approval_ready":
                raise ValueError("approval is permitted only for an approval-ready evidence packet")

            case.human_decision = decision
            case.human_reason = reason.strip()
            case.decided_by = approver.strip()
            case.status = f"human_{decision}d" if decision != "deny" else "human_denied"
            case.updated_at = datetime.now(timezone.utc).isoformat()
            case.audit.append(
                AuditEvent(
                    "human_decision_recorded",
                    approver.strip(),
                    details={"decision": decision, "reason": reason.strip()},
                )
            )
            self._write_audit(case, "human_decision_recorded")
            return case

    def _write_audit(self, case: CaseRecord, event: str) -> None:
        if not self.audit_path:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "case_id": case.case_id,
            "status": case.status,
            "human_decision": case.human_decision,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
