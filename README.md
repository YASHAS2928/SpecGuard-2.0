# SpecGuard 2.0 quality-engine prototype

Synthetic educational prototype for requirement RQ-014: one overnight shift, one unpaid meal, and overtime above 480 paid minutes per shift. The PDF blueprint is a conceptual reference; this repository does not claim Dayforce integration or actual Dayforce policy behavior.

## What works

The independent oracle calculates local-wall-clock shift span, paid minutes and overtime. The deterministic generator creates 13 draft cases. The validator checks schema, source spans, policy references and dates, rule and requirement links, oracle values, AI claims, duplicates, required coverage, suspicious instructions, and execution targets. The controlled runner requires an authoritative reviewed-case lookup, verifies the stored case and approval record against the submitted snapshot, checks oracle expectations again, and calls one loopback mock endpoint with redirects disabled. The mock provides three deliberate defects and one corrected version. Failure clustering uses observed `FAIL` results only.

The shared contracts, backend routes, persistence, AI adapter and frontend remain teammate-owned scaffolds. See [integration decisions](docs/quality-engine-integration.md) and [Phase 2 verification](docs/phase2-verification.md). The runner is an internal service: Member 1 must implement its review lookup against trusted storage. Browser-supplied approval flags must never be passed through.

## Install and run (PowerShell, from repository root)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:MOCK_VERSION = '1.3.0'
.\.venv\Scripts\python.exe -m uvicorn mock_api.main:app --host 127.0.0.1 --port 9000
```

In another terminal, from the repository root:

```powershell
$env:SPECGUARD_ENABLE_HTTP_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

The tests also run with the standard library when pytest is unavailable. Set `SPECGUARD_ENABLE_HTTP_TESTS=1` on hosts with loopback socket access to include the in-process FastAPI test; otherwise that one test skips:

```powershell
python -m unittest discover -s backend/tests -v
```

For a concise offline demonstration of generation, validation, simulated review, execution, and clustering:

```powershell
python -m scripts.demo_quality
```

The script prints actual result JSON. Its in-memory approval is a labeled demo simulation; Member 1 must wire persisted human approval for the product flow.

With a live mock server running, this command uses the real HTTP runner. Its `--version` must match the server's `MOCK_VERSION`; `--case` can select `overnight_with_break`, `threshold_exact`, or `daytime_with_break`:

```powershell
python -m scripts.verify_live --version 1.4.0 --case threshold_exact
```

Set `MOCK_VERSION` to `1.3.0-b`, `1.3.0-c`, or `1.4.0` and restart the server to change implementation. This environment variable is a development-only selector, not a request header or browser parameter. Member 1 must agree to this selection mechanism before relying on it in UI flows. The fixed API route is `POST http://127.0.0.1:9000/v1/pay/calculate` with `start_time`, `end_time`, `overnight`, and `meal_break_minutes`. Successful JSON contains `paid_minutes` and `overtime_minutes`; invalid inputs return HTTP 422. Successful responses include `X-Mock-Version`.

Example:

```powershell
$body = @{ start_time='22:00'; end_time='07:00'; overnight=$true; meal_break_minutes=30 } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:9000/v1/pay/calculate' -Method Post -ContentType 'application/json' -Body $body
```

With `MOCK_VERSION=1.4.0`, this returns `paid_minutes=510`, `overtime_minutes=30`. With `1.3.0`, it returns `0` and `0`; the same approved `PAID_EQUALS` case fails. Those values are verified by the local tests; they are synthetic demonstration data.

## Domain rules and limitations

Only 24-hour `HH:MM` local wall-clock times are supported. DST and time zones are excluded. Equal start/end times, shifts longer than 960 minutes, malformed times, negative meals, meals longer than shift span, and earlier clock-out without `overnight=true` are invalid. `overnight=true` requires the end clock time to precede the start clock time. The mock returns 422 for invalid requests. The oracle accepts only a 480-minute per-shift threshold. A meal is deducted once.

Runner limit: 1–100 cases, 2048-byte input per case, 16 KiB response per case, and 3-second HTTP timeout. No retries. The endpoint is fixed to loopback. The fixed URL must resolve to the locally controlled mock; production network isolation and trusted approval persistence are integration responsibilities. Blocking findings stop execution. V11 warnings require acknowledgment in the trusted approval record. The `meal_break_minutes` input represents an already-approved unpaid break; no break-approval workflow exists here.

The sandbox blocks loopback sockets: even `asyncio.new_event_loop()` stalls in Python's Windows `socketpair` fallback. With permitted loopback access, the event loop, Uvicorn, real HTTP requests, the controlled runner, and all 18 tests worked. In the restricted shell, 17 tests pass and the one in-process HTTP test skips. Dependency installation from PyPI failed here because DNS access is unavailable; preinstalled FastAPI, Pydantic and HTTPX allowed `unittest` verification. Pytest and GitHub Actions have not run locally. Run the documented install and pytest commands on a networked developer machine.

No license has been chosen. The team must agree before licensing teammates' work. No private GitHub repository was created: local `gh auth status` reports an invalid token. From an authenticated account, after confirming the intended owner and that no repo with this name exists:

```powershell
gh auth login -h github.com
gh repo create SpecGuard-2.0 --private --source . --remote origin --push
```

The local default branch is `main`. Four collaborator usernames are still needed; no invitations have been sent. Use feature branches and reviewed pull requests for integration.
