# Prototype validation evidence

Validated locally on 25 September 2026.

## Automated tests

- Command: `python3 -m unittest discover -s tests -v`
- Result: **12/12 passed**
- Covered: complete intake, synthetic-ID rejection, missing evidence, emergency handoff, clinic authentication failure, cost threshold, separate human decision, token rejection, missing-evidence approval prevention, valid HMAC, invalid HMAC and stale HMAC.

## Deterministic evaluation

- Command: `python3 evaluation/run_suite.py --output evaluation/latest-report.json`
- Result: **30/30 passed, 100%**
- Mix: 10 approval-ready, 8 missing-evidence, 4 emergency, 4 authentication-failure and 4 threshold-escalation cases.
- Safety invariant: every evaluated case had no human decision before the separate approver action.

## Live HTTP smoke test

- Health endpoint returned synthetic-demo mode, `human_gate: true` and `real_patient_data_allowed: false`.
- Complete intake returned `approval_ready` with no human decision.
- Wrong approver token returned HTTP 401.
- Correct separate approver action returned `human_approved`.
- Missing-evidence case could not be approved and returned HTTP 409.
- Valid ElevenLabs-style HMAC webhook returned HTTP 200.
- Invalid HMAC webhook returned HTTP 401.

## Browser test

The local interface was opened at `http://127.0.0.1:8042/`. The complete synthetic case produced a cited recommendation and four audit events. The separate human action changed the case to `human_approved` and added a fifth audit event identifying the synthetic reviewer. Accessibility inspection exposed labelled inputs, headings, buttons, status text and the control-path list.

## Boundaries not proven

- No deployed ElevenLabs agent or Agent Testing result
- No live telephony, Scribe or Eleven v3 latency/voice-quality evidence
- No real insurer, clinic or patient data
- No institutional security, privacy, procurement or pilot approval
- No production-scale load test
