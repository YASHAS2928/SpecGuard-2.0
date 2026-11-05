# Verification evidence

This document records verification evidence for the deterministic quality
engine and its loopback system-under-test. Requirements, policies, and results
are fictional.

## Source audit

The oracle and mock calculator use separate implementations. Both support
24-hour local wall-clock times, reject ambiguous or excessive spans, and
deduct an already-approved meal duration. The corrected mock matches the
oracle for boundary, overnight, and meal cases. No engine or runner code
executes generated Python or shell commands.

The runner:

- Requires a trusted canonical case and approval lookup.
- Compares submitted cases and findings with the stored snapshot.
- Rejects stale approvals and unacknowledged warnings.
- Rejects external execution targets.
- Disables redirects and proxy use.
- Enforces timeouts, response limits, and valid result ranges.
- Treats only HTTP 422 as success for `REJECTS` assertions.

## Controlled service evidence

The versioned mock intentionally exposes three defects:

| Version | Demonstrated defect |
|---|---|
| `1.3.0` | Does not correctly handle the overnight boundary. |
| `1.3.0-b` | Starts overtime at the exact threshold instead of after it. |
| `1.3.0-c` | Deducts the meal break twice. |
| `1.4.0` | Corrected behavior for the demonstrated cases. |

The live probe verifies the oracle result against the HTTP response and checks
the `X-Mock-Version` header. Invalid inputs return HTTP 422, and unsupported
mock configuration returns an explicit error.

## Validator evidence

The test suite independently exercises all twelve validation identifiers:

`V01` schema, `V02` grounding, `V03` policy, `V04` dates, `V05` rule,
`V06` references, `V07` oracle, `V08` AI claims, `V09` duplicates,
`V10` coverage, `V11` suspicious instructions, and `V12` target safety.

The runner tests cover unapproved cases, modified cases, stale approvals,
blocking findings, supported assertions, external URLs, redirects, timeouts,
malformed responses, impossible values, HTTP 400/500 responses, and HTTP 422
rejection cases.

## Reproduce the evidence

Start the local demo from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1
```

Run backend tests:

```powershell
$env:SPECGUARD_ENABLE_HTTP_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Run the end-to-end loopback journey:

```powershell
.\.venv\Scripts\python.exe -m scripts.e2e_live `
  --backend http://127.0.0.1:8000 `
  --mock http://127.0.0.1:9000
```

The journey covers requirement creation, specification analysis,
clarification, approval, test design and review, execution, defects, change
impact, drift, metrics, and audit.
