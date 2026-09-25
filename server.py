#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from typing import Any

from preauth import CaseStore, PreauthEngine
from preauth.domain import PreauthInput, ValidationError
from preauth.security import SignatureError, verify_elevenlabs_signature


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CASE_PATH = re.compile(r"^/api/cases/([A-Z0-9-]+)$")
DECISION_PATH = re.compile(r"^/api/cases/([A-Z0-9-]+)/decision$")
MAX_BODY = 64 * 1024


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class DemoApplication:
    def __init__(
        self,
        *,
        demo_mode: bool,
        approver_token: str,
        webhook_secret: str,
        audit_path: Path | None,
    ):
        self.demo_mode = demo_mode
        self.approver_token = approver_token
        self.webhook_secret = webhook_secret
        self.engine = PreauthEngine(
            load_json(ROOT / "data" / "providers.json"),
            load_json(ROOT / "data" / "policies.json"),
        )
        self.store = CaseStore(audit_path=audit_path)
        self.webhook_events: list[dict[str, Any]] = []

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = PreauthInput.from_payload(payload)
        return self.store.add(self.engine.evaluate(request)).to_dict()

    def decide_case(self, case_id: str, payload: dict[str, Any], token: str | None) -> dict[str, Any]:
        if not token or not self.approver_token or not _constant_time_equal(token, self.approver_token):
            raise PermissionError("A valid X-Approver-Token is required")
        required = {"decision", "reason", "approver"}
        if set(payload) != required:
            raise ValidationError("decision payload must contain exactly: approver, decision, reason")
        return self.store.decide(
            case_id,
            str(payload["decision"]),
            str(payload["reason"]),
            str(payload["approver"]),
        ).to_dict()

    def receive_webhook(self, raw_body: bytes, signature: str | None) -> dict[str, Any]:
        if not self.webhook_secret:
            raise RuntimeError("WEBHOOK_SECRET is not configured")
        verify_elevenlabs_signature(raw_body, signature, self.webhook_secret)
        event = json.loads(raw_body)
        if not isinstance(event, dict):
            raise ValidationError("webhook body must be a JSON object")
        # Store only operational metadata in this synthetic demo. A production
        # institution must apply its approved retention and redaction policy.
        self.webhook_events.append(
            {
                "type": event.get("type"),
                "conversation_id": (event.get("data") or {}).get("conversation_id"),
            }
        )
        return {"status": "received"}


def _constant_time_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def handler_factory(app: DemoApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AqionPreauthDemo/1.0"

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/api/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "mode": "synthetic-demo" if app.demo_mode else "configured",
                        "human_gate": True,
                        "real_patient_data_allowed": False,
                    },
                )
                return
            if path == "/api/config":
                self._json(
                    HTTPStatus.OK,
                    {
                        "demo_mode": app.demo_mode,
                        "languages": ["ar", "en", "ur"],
                        "human_gate": True,
                    },
                )
                return
            if path == "/api/cases":
                self._json(HTTPStatus.OK, {"cases": app.store.list()})
                return
            match = CASE_PATH.fullmatch(path)
            if match:
                case = app.store.get(match.group(1))
                if not case:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "case not found"})
                else:
                    self._json(HTTPStatus.OK, case.to_dict())
                return
            self._serve_static(path)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            try:
                raw = self._read_body()
                if path == "/api/cases":
                    self._json(HTTPStatus.CREATED, app.create_case(self._parse_json(raw)))
                    return
                decision_match = DECISION_PATH.fullmatch(path)
                if decision_match:
                    result = app.decide_case(
                        decision_match.group(1),
                        self._parse_json(raw),
                        self.headers.get("X-Approver-Token"),
                    )
                    self._json(HTTPStatus.OK, result)
                    return
                if path == "/webhooks/elevenlabs/post-call":
                    result = app.receive_webhook(raw, self.headers.get("ElevenLabs-Signature"))
                    self._json(HTTPStatus.OK, result)
                    return
                self._json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            except ValidationError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except json.JSONDecodeError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "body must be valid JSON"})
            except PermissionError as exc:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "case not found"})
            except SignatureError as exc:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
            except ValueError as exc:
                self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
            except RuntimeError as exc:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValidationError("request body is required")
            if length > MAX_BODY:
                raise ValidationError("request body exceeds 64 KiB")
            return self.rfile.read(length)

        @staticmethod
        def _parse_json(raw: bytes) -> dict[str, Any]:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValidationError("body must be a JSON object")
            return payload

        def _serve_static(self, path: str) -> None:
            requested = "index.html" if path in {"", "/"} else path.lstrip("/")
            candidate = (STATIC / requested).resolve()
            if STATIC.resolve() not in candidate.parents and candidate != STATIC.resolve():
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if not candidate.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            body = candidate.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[{self.log_date_time_string()}] {fmt % args}")

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the synthetic pre-authorisation demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8042)
    parser.add_argument("--demo", action="store_true", help="Use a synthetic local approver token")
    parser.add_argument("--audit-file", type=Path, default=ROOT / "working" / "audit.jsonl")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    approver_token = "demo-approver" if args.demo else os.environ.get("APPROVER_TOKEN", "")
    if not approver_token:
        raise SystemExit("Set APPROVER_TOKEN or run with --demo")
    app = DemoApplication(
        demo_mode=args.demo,
        approver_token=approver_token,
        webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
        audit_path=args.audit_file,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(app))
    print(f"Synthetic pre-authorisation demo: http://{args.host}:{args.port}/")
    print("No real patient data. Agent recommendations require a separate human decision.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping demo.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
