from __future__ import annotations

import hashlib
import hmac
import time


class SignatureError(ValueError):
    pass


def verify_elevenlabs_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
    *,
    now: int | None = None,
    tolerance_seconds: int = 30 * 60,
) -> None:
    """Verify ElevenLabs' documented t=...,v0=... HMAC-SHA256 signature."""
    if not signature_header:
        raise SignatureError("Missing ElevenLabs-Signature header")
    try:
        values = dict(part.split("=", 1) for part in signature_header.split(","))
        timestamp = values["t"]
        supplied = values["v0"]
        timestamp_int = int(timestamp)
    except (KeyError, ValueError) as exc:
        raise SignatureError("Malformed ElevenLabs-Signature header") from exc

    current = int(time.time()) if now is None else now
    if abs(current - timestamp_int) > tolerance_seconds:
        raise SignatureError("Stale ElevenLabs webhook signature")

    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise SignatureError("Invalid ElevenLabs webhook signature")
