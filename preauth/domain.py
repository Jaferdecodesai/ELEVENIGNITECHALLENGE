from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any


ALLOWED_LANGUAGES = {"en", "ar", "ur"}
ALLOWED_URGENCY = {"routine", "urgent", "emergency"}
SYNTHETIC_ID = re.compile(r"^SYN-[0-9]{6}$")


class ValidationError(ValueError):
    """Raised when a request crosses the demo's data or schema boundary."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PreauthInput:
    clinic_id: str
    callback_number: str
    synthetic_member_id: str
    policy_id: str
    procedure_code: str
    diagnosis_code: str
    cost_aed: float
    urgency: str
    language: str
    documents: tuple[str, ...]
    disclosure_acknowledged: bool
    recording_consent: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PreauthInput":
        required = {
            "clinic_id",
            "callback_number",
            "synthetic_member_id",
            "policy_id",
            "procedure_code",
            "diagnosis_code",
            "cost_aed",
            "urgency",
            "language",
            "documents",
            "disclosure_acknowledged",
            "recording_consent",
        }
        missing = sorted(required - payload.keys())
        unknown = sorted(payload.keys() - required)
        if missing:
            raise ValidationError(f"Missing required fields: {', '.join(missing)}")
        if unknown:
            raise ValidationError(f"Unknown fields are not accepted: {', '.join(unknown)}")

        member_id = str(payload["synthetic_member_id"]).strip()
        if not SYNTHETIC_ID.fullmatch(member_id):
            raise ValidationError("Only synthetic member IDs in the form SYN-000000 are accepted")

        language = str(payload["language"]).lower().strip()
        if language not in ALLOWED_LANGUAGES:
            raise ValidationError("language must be one of: ar, en, ur")

        urgency = str(payload["urgency"]).lower().strip()
        if urgency not in ALLOWED_URGENCY:
            raise ValidationError("urgency must be routine, urgent, or emergency")

        try:
            cost = float(payload["cost_aed"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("cost_aed must be a number") from exc
        if cost <= 0 or cost > 1_000_000:
            raise ValidationError("cost_aed must be between 0 and 1,000,000")

        documents = payload["documents"]
        if not isinstance(documents, list) or not all(isinstance(item, str) for item in documents):
            raise ValidationError("documents must be a list of document codes")

        for consent_field in ("disclosure_acknowledged", "recording_consent"):
            if not isinstance(payload[consent_field], bool):
                raise ValidationError(f"{consent_field} must be true or false")

        return cls(
            clinic_id=str(payload["clinic_id"]).strip(),
            callback_number=str(payload["callback_number"]).strip(),
            synthetic_member_id=member_id,
            policy_id=str(payload["policy_id"]).strip(),
            procedure_code=str(payload["procedure_code"]).upper().strip(),
            diagnosis_code=str(payload["diagnosis_code"]).upper().strip(),
            cost_aed=cost,
            urgency=urgency,
            language=language,
            documents=tuple(sorted({item.lower().strip() for item in documents if item.strip()})),
            disclosure_acknowledged=payload["disclosure_acknowledged"],
            recording_consent=payload["recording_consent"],
        )


@dataclass
class AuditEvent:
    event: str
    actor: str
    at: str = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseRecord:
    case_id: str
    request: PreauthInput
    status: str
    recommendation: str | None
    rationale: str
    source: str | None
    missing_documents: list[str] = field(default_factory=list)
    human_decision: str | None = None
    human_reason: str | None = None
    decided_by: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    audit: list[AuditEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
