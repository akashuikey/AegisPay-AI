"""Demo smoke test for AegisPay AI (P2-A9).

Validates service health and the essential demo endpoints against a RUNNING
backend. It logs in as the bootstrap operator, lists the scenario catalogue, and
runs one fraud scenario (expected protective hold) and one legitimate scenario
(expected simulated settlement) in deterministic mode.

Uses only the standard library. Never prints secrets, tokens, or OTP values.

Usage (backend must be running and migrated):
    uv run python -I scripts/smoke_test.py

Environment:
    SMOKE_BASE_URL                (default http://127.0.0.1:8000)
    SMOKE_OPERATOR_USERNAME       (falls back to AUTH_BOOTSTRAP_OPERATOR_USERNAME)
    SMOKE_OPERATOR_PASSWORD       (falls back to AUTH_BOOTSTRAP_OPERATOR_PASSWORD)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("SMOKE_OPERATOR_USERNAME") or os.environ.get(
    "AUTH_BOOTSTRAP_OPERATOR_USERNAME", "operator"
)
PASSWORD = os.environ.get("SMOKE_OPERATOR_PASSWORD") or os.environ.get(
    "AUTH_BOOTSTRAP_OPERATOR_PASSWORD", ""
)

_failures = 0


def _request(method: str, path: str, *, token: str | None = None, body: dict | None = None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc.reason)}


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    mark = "PASS" if ok else "FAIL"
    if not ok:
        _failures += 1
    print(f"[{mark}] {label}{(' - ' + detail) if detail else ''}")


def main() -> int:
    print(f"AegisPay AI smoke test against {BASE}\n")

    status, _ = _request("GET", "/health/live")
    check("health/live", status == 200, f"status={status}")

    status, _ = _request("GET", "/health/ready")
    check("health/ready (database)", status == 200, f"status={status}")

    status, info = _request("GET", "/api/v1/info")
    check("api/v1/info", status == 200, info.get("name", ""))

    if not PASSWORD:
        check(
            "operator login",
            False,
            "no operator password in env (set AUTH_BOOTSTRAP_OPERATOR_PASSWORD)",
        )
        return 1

    status, login = _request(
        "POST", "/api/v1/auth/login", body={"username": USERNAME, "password": PASSWORD}
    )
    token = login.get("access_token") if status == 200 else None
    check("operator login", token is not None, f"status={status}")
    if not token:
        return 1

    status, catalog = _request("GET", "/api/v1/scenarios", token=token)
    count = catalog.get("total", 0) if status == 200 else 0
    check("scenario catalogue", status == 200 and count >= 8, f"{count} scenarios")

    status, run = _request(
        "POST",
        "/api/v1/scenarios/digital_arrest/runs",
        token=token,
        body={"execution_mode": "DETERMINISTIC"},
    )
    held = run.get("final_state") == "HELD_FOR_VERIFICATION"
    check(
        "fraud scenario (digital_arrest) -> protective hold",
        status in (200, 201) and run.get("status") == "COMPLETED" and held,
        f"state={run.get('final_state')}",
    )

    status, run2 = _request(
        "POST",
        "/api/v1/scenarios/legitimate_high_value/runs",
        token=token,
        body={"execution_mode": "DETERMINISTIC"},
    )
    settled = run2.get("final_state") == "SETTLED_SIMULATED"
    check(
        "legitimate scenario -> simulated settlement",
        status in (200, 201) and run2.get("status") == "COMPLETED" and settled,
        f"state={run2.get('final_state')}",
    )

    print()
    if _failures:
        print(f"SMOKE TEST FAILED: {_failures} check(s) failed.")
        return 1
    print("SMOKE TEST PASSED: all checks green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
