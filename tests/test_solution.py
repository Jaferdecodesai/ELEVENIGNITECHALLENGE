from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from preauth.domain import PreauthInput, ValidationError  # noqa: E402
from preauth.engine import PreauthEngine  # noqa: E402
from preauth.security import SignatureError, verify_elevenlabs_signature  # noqa: E402
from preauth.store import CaseStore  # noqa: E402
from server import DemoApplication, load_json  # noqa: E402


def base_payload() -> dict:
    return {
        "clinic_id": "CLINIC-001",
        "callback_number": "+971500000001",
        "synthetic_member_id": "SYN-000101",
        "policy_id": "POL-SYN-GOLD-01",
        "procedure_code": "PROC-MRI",
        "diagnosis_code": "M54.5",
        "cost_aed": 2400,
        "urgency": "routine",
        "language": "en",
        "documents": ["clinical_note", "referral"],
        "disclosure_acknowledged": True,
        "recording_consent": True,
    }


def engine() -> PreauthEngine:
    return PreauthEngine(
        load_json(ROOT / "data" / "providers.json"),
        load_json(ROOT / "data" / "policies.json"),
    )


class EngineTests(unittest.TestCase):
    def test_complete_case_stops_at_human_gate(self):
        case = engine().evaluate(PreauthInput.from_payload(base_payload()))
        self.assertEqual(case.status, "approval_ready")
        self.assertEqual(case.recommendation, "approve")
        self.assertIsNone(case.human_decision)
        self.assertIn("clause 4.2", case.source)

    def test_real_identifier_shape_is_rejected(self):
        payload = base_payload()
        payload["synthetic_member_id"] = "784-1980-1234567-1"
        with self.assertRaisesRegex(ValidationError, "Only synthetic member IDs"):
            PreauthInput.from_payload(payload)

    def test_missing_evidence_issues_no_recommendation(self):
        payload = base_payload()
        payload["documents"] = ["referral"]
        case = engine().evaluate(PreauthInput.from_payload(payload))
        self.assertEqual(case.status, "needs_evidence")
        self.assertIsNone(case.recommendation)
        self.assertEqual(case.missing_documents, ["clinical_note"])

    def test_emergency_routes_to_human_before_policy_lookup(self):
        payload = base_payload()
        payload["urgency"] = "emergency"
        case = engine().evaluate(PreauthInput.from_payload(payload))
        self.assertEqual(case.status, "human_escalation")
        self.assertIsNone(case.source)
        self.assertFalse(any(event.event == "rule_retrieved" for event in case.audit))

    def test_unregistered_callback_fails_authentication(self):
        payload = base_payload()
        payload["callback_number"] = "+971500009999"
        case = engine().evaluate(PreauthInput.from_payload(payload))
        self.assertEqual(case.status, "authentication_failed")
        self.assertIsNone(case.recommendation)

    def test_high_cost_routes_to_human(self):
        payload = base_payload()
        payload["cost_aed"] = 5001
        case = engine().evaluate(PreauthInput.from_payload(payload))
        self.assertEqual(case.status, "human_escalation")
        self.assertIsNone(case.recommendation)


class HumanGateTests(unittest.TestCase):
    def test_store_records_separate_human_decision(self):
        store = CaseStore()
        case = store.add(engine().evaluate(PreauthInput.from_payload(base_payload())))
        decided = store.decide(case.case_id, "approve", "Synthetic evidence reviewed", "Reviewer 7")
        self.assertEqual(decided.status, "human_approved")
        self.assertEqual(decided.human_decision, "approve")
        self.assertEqual(decided.decided_by, "Reviewer 7")

    def test_demo_application_rejects_wrong_token(self):
        app = DemoApplication(
            demo_mode=True,
            approver_token="demo-approver",
            webhook_secret="webhook-secret",
            audit_path=None,
        )
        case = app.create_case(base_payload())
        with self.assertRaises(PermissionError):
            app.decide_case(
                case["case_id"],
                {"decision": "approve", "reason": "Evidence reviewed", "approver": "Reviewer 7"},
                "wrong-token",
            )

    def test_missing_evidence_cannot_be_approved(self):
        payload = base_payload()
        payload["documents"] = ["referral"]
        store = CaseStore()
        case = store.add(engine().evaluate(PreauthInput.from_payload(payload)))
        with self.assertRaisesRegex(ValueError, "approval-ready"):
            store.decide(case.case_id, "approve", "External evidence not present", "Reviewer 7")


class WebhookTests(unittest.TestCase):
    def signature(self, body: bytes, secret: str, timestamp: int) -> str:
        digest = hmac.new(
            secret.encode(),
            str(timestamp).encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v0={digest}"

    def test_valid_signature(self):
        now = int(time.time())
        body = json.dumps({"type": "post_call_transcription", "data": {"conversation_id": "conv_demo"}}).encode()
        verify_elevenlabs_signature(body, self.signature(body, "secret", now), "secret", now=now)

    def test_invalid_signature(self):
        now = int(time.time())
        body = b"{}"
        with self.assertRaises(SignatureError):
            verify_elevenlabs_signature(body, self.signature(body, "other", now), "secret", now=now)

    def test_stale_signature(self):
        now = int(time.time())
        body = b"{}"
        with self.assertRaisesRegex(SignatureError, "Stale"):
            verify_elevenlabs_signature(body, self.signature(body, "secret", now - 4000), "secret", now=now)


if __name__ == "__main__":
    unittest.main()
