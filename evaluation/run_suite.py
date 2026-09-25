#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from preauth.domain import PreauthInput  # noqa: E402
from preauth.engine import PreauthEngine  # noqa: E402
from server import load_json  # noqa: E402


def base_payload(index: int) -> dict:
    return {
        "clinic_id": "CLINIC-001",
        "callback_number": "+971500000001",
        "synthetic_member_id": f"SYN-{index:06d}",
        "policy_id": "POL-SYN-GOLD-01",
        "procedure_code": "PROC-MRI",
        "diagnosis_code": "M54.5",
        "cost_aed": 2400,
        "urgency": "routine",
        "language": ["en", "ar", "ur"][index % 3],
        "documents": ["clinical_note", "referral"],
        "disclosure_acknowledged": True,
        "recording_consent": True,
    }


def scenarios() -> list[tuple[str, dict, str]]:
    cases: list[tuple[str, dict, str]] = []
    for index in range(1, 11):
        cases.append((f"complete-{index:02d}", base_payload(index), "approval_ready"))
    for index in range(11, 19):
        payload = base_payload(index)
        payload["documents"] = ["referral"]
        cases.append((f"missing-evidence-{index:02d}", payload, "needs_evidence"))
    for index in range(19, 23):
        payload = base_payload(index)
        payload["urgency"] = "emergency"
        cases.append((f"emergency-{index:02d}", payload, "human_escalation"))
    for index in range(23, 27):
        payload = base_payload(index)
        payload["callback_number"] = "+971500009999"
        cases.append((f"authentication-{index:02d}", payload, "authentication_failed"))
    for index in range(27, 31):
        payload = base_payload(index)
        payload["cost_aed"] = 7000
        cases.append((f"threshold-{index:02d}", payload, "human_escalation"))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 30-case deterministic evaluation suite")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    engine = PreauthEngine(
        load_json(ROOT / "data" / "providers.json"),
        load_json(ROOT / "data" / "policies.json"),
    )
    results = []
    passed = 0
    for name, payload, expected in scenarios():
        case = engine.evaluate(PreauthInput.from_payload(payload))
        safety_ok = case.human_decision is None
        expected_ok = case.status == expected
        result = {
            "name": name,
            "expected": expected,
            "actual": case.status,
            "human_decision_absent": safety_ok,
            "passed": safety_ok and expected_ok,
        }
        results.append(result)
        passed += int(result["passed"])

    report = {
        "suite": "synthetic-preauthorisation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results),
        "results": results,
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
