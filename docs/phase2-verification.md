# Phase 2 source audit and verification

Verified locally on 4 November 2026. This is a synthetic engineering fixture, not a Dayforce system or policy. Each live result below came from `python -m scripts.verify_live` using the runner's default HTTPX client against Uvicorn at `127.0.0.1:9000`, after restarting the server with the listed `MOCK_VERSION`. The command-line probe uses a labeled in-memory approval stand-in; production review storage is not implemented.

## Source audit

All implemented files under `backend/app/engine`, `backend/app/runner`, `mock_api`, `backend/tests`, `policies`, and `scripts` were reviewed. The oracle and mock calculator have separate implementations and imports. Both use local 24-hour wall-clock time, reject ambiguous or excessive spans, and deduct an already-approved meal duration. The corrected mock matches the oracle on the tested boundary, overnight, and meal cases. The three buggy versions are deliberately different. No engine or runner code executes generated Python or shell commands.

Confirmed issues corrected in Phase 2:

1. The runner formerly trusted `approval_state` and `validation_state` strings in caller-supplied dictionaries. It now requires a trusted `load_reviewed_case` callback, compares the submitted case and findings with the canonical stored snapshot, requires an approval bound to test ID and case version, and requires reviewer acknowledgment for warnings. The callback must be wired to Member 1's authenticated persistence layer.
2. The validator formerly accepted a case that cited none of the three required synthetic policies. It now emits V03 BLOCK for each missing required policy.
3. Malformed source IDs and malformed criterion records could raise exceptions during validation. They now fail closed as V02 or V06 findings. Unexpected input fields now yield V01 rather than passing schema checks.
4. The runner could accept a 200 response containing negative paid minutes or overtime greater than paid minutes as valid schema. These are now ERROR. The default HTTP client also ignores proxy environment variables and keeps redirects disabled.
5. The previous README described live FastAPI execution as unverified. The event-loop hang was traced to Python's Windows `socketpair` fallback waiting in `accept()` when the sandbox denied loopback sockets. With permitted loopback access, event-loop creation, FastAPI TestClient, Uvicorn, and real HTTP execution all completed.

Known assumptions and remaining contract limits: `meal_break_minutes` means an already-approved unpaid meal; no break-approval event is modeled. Time zones and DST are excluded. The validator trusts the supplied policy registry's semantics after checking IDs and dates; Member 1 must freeze policy version and parameter contracts. The engine has no route, user authentication, database, or durable audit store. The CLI probes simulate review approval and do not prove a real reviewer workflow.

## Real HTTP version evidence

| Mock version | Test ID | Inputs (`start`,`end`,`overnight`,`meal`) | Oracle expected (`paid`,`OT`) | HTTP actual (`paid`,`OT`) | Assertion | Status | Explanation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `1.3.0` | `RQ-014-overnight_with_break` | `22:00`,`07:00`,true,30 | 510,30 | 0,0 | `PAID_EQUALS` | FAIL | Midnight wrap omitted and negative span clamped. |
| `1.3.0-b` | `RQ-014-threshold_exact` | `08:00`,`16:00`,false,0 | 480,0 | 480,1 | `OT_EQUALS` | FAIL | Overtime begins at minute 480 instead of 481. |
| `1.3.0-c` | `RQ-014-daytime_with_break` | `08:00`,`17:00`,false,30 | 510,30 | 480,0 | `PAID_EQUALS` | FAIL | Meal deducted twice. |
| `1.4.0` | `RQ-014-overnight_with_break` | `22:00`,`07:00`,true,30 | 510,30 | 510,30 | `PAID_EQUALS` | PASS | Correct overnight calculation. |
| `1.4.0` | `RQ-014-threshold_exact` | `08:00`,`16:00`,false,0 | 480,0 | 480,0 | `OT_EQUALS` | PASS | Correct threshold boundary. |
| `1.4.0` | `RQ-014-daytime_with_break` | `08:00`,`17:00`,false,30 | 510,30 | 510,30 | `PAID_EQUALS` | PASS | Meal deducted once. |

All six requests returned HTTP 200 and a matching `X-Mock-Version` response header. In-process TestClient also exercised each implementation plus 422 invalid input and 503 unsupported server configuration.

## Validator and runner evidence

`test_each_validator_code_is_triggered_independently` starts with a valid generated plan and mutates one scenario at a time. It verified all twelve identifiers and severities: V01 schema BLOCK; V02 grounding BLOCK; V03 unknown/missing policy BLOCK; V04 ineffective date BLOCK; V05 unsupported rule BLOCK; V06 broken reference BLOCK; V07 oracle mismatch BLOCK; V08 AI claim mismatch BLOCK; V09 duplicate BLOCK; V10 coverage gap BLOCK; V11 suspicious instruction WARNING; V12 forbidden target BLOCK. A separate test proves missing source text yields V02. The warning-only test proves execution blocks without explicit reviewer acknowledgment and proceeds with a trusted acknowledgment.

Runner tests verified unapproved cases never reach the HTTP transport, modified cases cannot reuse an approval, blocking findings stop execution, only the three assertion types are accepted, external URLs are rejected, redirects yield ERROR, timeouts yield ERROR, malformed or impossible 200 responses yield ERROR, 400 yields FAIL for a positive assertion, 500 yields ERROR, and `REJECTS` passes only on 422. The fixed target is loopback, with redirects disabled, explicit timeouts, response and payload size limits, and no retry or generated-code execution.

## Test and repository status

With permitted loopback socket access, `SPECGUARD_ENABLE_HTTP_TESTS=1 python -m unittest discover -s backend/tests -v` ran 18 tests: **18 passed, 0 failed, 0 skipped**. In the restricted shell, 17 passed and the one socket-dependent in-process test skipped. Pytest is not installed in this host and PyPI DNS is unavailable; the GitHub Actions workflow is configured to install dependencies and run pytest with HTTP tests enabled, but no remote or CI run exists yet.

The local branch is `main`. `gh auth status` reports an invalid login, so the private remote was not created or pushed. No GitHub Actions success is claimed. No collaborator invitations have been sent. See README for the interactive login and remote-creation commands. The repository has no chosen license pending team agreement.

## Files changed in Phase 2

`.github/workflows/python-tests.yml`; `README.md`; `backend/app/engine/grounding.py`; `backend/app/engine/test_generator.py`; `backend/app/engine/validator.py`; `backend/app/runner/executor.py`; `backend/tests/test_http_api.py`; `backend/tests/test_quality_engine.py`; `docs/phase2-verification.md`; `docs/quality-engine-integration.md`; `scripts/demo_quality.py`; `scripts/verify_live.py`.
