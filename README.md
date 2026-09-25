# AqionLabs synthetic provider pre-authorisation prototype

This is a local, dependency-free demonstration of the Ignyte × ElevenLabs Track 1 / Use Case 3 concept. It proves the workflow and control boundaries with synthetic data; it is not a live insurer integration and does not create a deployed ElevenLabs agent.

Repository: https://github.com/Jaferdecodesai/ELEVENIGNITECHALLENGE

Team details and assigned email conventions: [TEAM.md](TEAM.md)

## What runs end to end

- AI disclosure and recording-consent gates
- Registered clinic/callback-number authentication against a synthetic directory
- Strict request schema and synthetic member-ID enforcement
- Read-only lookup against a versioned synthetic benefit schedule
- Missing-evidence, emergency, authentication and threshold escalation paths
- Source-cited recommendation preparation
- Separate token-protected human approve/deny/escalate action
- Append-only operational audit events
- ElevenLabs-compatible HMAC webhook verification
- Thirty-case deterministic evaluation suite
- Responsive local approver console

The agent code has no final-decision method. Only the separate approver route can record an outcome.

## Run locally

From this directory:

```bash
python3 server.py --demo --port 8042
```

Open `http://127.0.0.1:8042/`.

The local demo approver token is `demo-approver`. It has no production value. Never reuse it outside the synthetic demo.

## Validate

```bash
python3 -m unittest discover -s tests -v
python3 evaluation/run_suite.py --output evaluation/latest-report.json
```

Expected evaluation result: `30/30`, with no synthetic case carrying a human decision before the separate approval action.

## ElevenLabs build-sprint handoff

After challenge workspace access and credentials are supplied:

1. Create an ElevenLabs agent in the dashboard or with the documented `POST /v1/convai/agents/create` endpoint.
2. Apply `elevenlabs/system_prompt_v1.md`.
3. Configure the five least-privilege server tools described in `elevenlabs/tool_contracts.json`.
4. Build the fixed workflow nodes: disclosure → language → clinic authentication → intake → rule lookup → approval hold → signed outcome or human route.
5. Load only synthetic policy material into the knowledge base during the sprint.
6. Configure Scribe v2 keyterms for policy, procedure and diagnosis codes.
7. Configure Eleven v3 voices for English and Arabic, then validate Urdu handling before claiming coverage.
8. Add the cases in `elevenlabs/agent_testing_suite.json` to Agent Testing and run them probabilistically.
9. Configure a post-call transcription webhook at `/webhooks/elevenlabs/post-call` and set `WEBHOOK_SECRET`.
10. Keep production disabled until the institution and ElevenLabs provide the required written authorisation and privacy/security review.

Official references:

- Agent creation: https://elevenlabs.io/docs/api-reference/agents/create/
- Agent Testing: https://elevenlabs.io/docs/eleven-agents/customization/agent-testing
- Post-call webhooks: https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks

## Data and policy boundary

- Use only IDs matching `SYN-000000`.
- Do not enter patient/member data, credentials, payment data, real policy records or institution-confidential material.
- The included policy and provider files are fictional test fixtures.
- The prototype prepares a recommendation; it does not make a medical or insurance decision.
- This local prototype does not prove production security, latency, scale, multilingual voice quality or institutional acceptance.
