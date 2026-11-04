# SpecGuard 2.0 quality-engine prototype

Synthetic educational prototype for requirement RQ-014: one overnight shift, one unpaid meal, and overtime above 480 paid minutes per shift. The PDF blueprint is a conceptual reference; this repository does not claim Dayforce integration or actual Dayforce policy behavior.

## What works

The independent oracle calculates local-wall-clock shift span, paid minutes and overtime. The deterministic generator creates 13 draft cases. The validator checks schema, source spans, policy references and dates, rule and requirement links, oracle values, AI claims, duplicates, required coverage, suspicious instructions, and execution targets. The controlled runner requires an authoritative reviewed-case lookup, verifies the stored case and approval record against the submitted snapshot, checks oracle expectations again, and calls one loopback mock endpoint with redirects disabled. The mock provides three deliberate defects and one corrected version. Failure clustering uses observed `FAIL` results only.

Backend milestones 1-5 now include UUID contracts, persistence, requirement
versioning, policy seeds, audit events, AI interfaces, and the specification
workflow. Frontend Part 1 provides Requirements and Specification/Clarification
screens. See [API contracts](docs/API_CONTRACTS.md),
[integration decisions](docs/quality-engine-integration.md), and
[Phase 2 verification](docs/phase2-verification.md). The runner is an internal
service: Member 1 must implement its review lookup against trusted storage.
Browser-supplied approval flags must never be passed through.

## Frontend Part 1

The React/TypeScript Vite frontend uses Tailwind, with no router or component
library. It supports creating requirements and immutable versions, choosing
policy versions, analysis, reading specs, resolving/defering ambiguities, and
approval with explicit blockers and trace IDs. Tests/Review, Run/Defects, Change
Impact, Overview, and Audit screens are not implemented yet.

All data is fictional. Actor/role selection is an MVP convenience, **not
authentication**. The actor is stored in this origin's browser local storage;
storage failures are displayed. Only the API base URL belongs in frontend
configuration; never put API keys in `VITE_*` variables.

With an approved Node.js 22.12+ or 24 LTS installation, from `frontend`:

```powershell
npm ci
npm run build
npm test
npm run lint
npm run dev
```

The UI is at `http://127.0.0.1:5173`. It connects to
`http://localhost:8000` by default; override `VITE_API_BASE_URL` when starting
Vite if needed (see [frontend/.env.example](frontend/.env.example)).
Vite binds to loopback only. No global packages are required.

For the optional project-local portable Node distribution under `.tools`, run
the tools directly without modifying PATH, from `frontend`:

```powershell
$nodeDir = (Get-ChildItem ..\.tools -Directory -Filter 'node-*-win-x64' | Select-Object -First 1).FullName
$node = Join-Path $nodeDir 'node.exe'
& $node node_modules\typescript\bin\tsc -b
& $node node_modules\vite\bin\vite.js build
& $node node_modules\vitest\vitest.mjs run
& $node node_modules\eslint\bin\eslint.js .
& $node node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173
```

Dependencies and build output are project-local; `.tools`, npm cache,
`node_modules`, and `dist` are ignored by Git. The lockfile records dependency
versions. Tests use synthetic fixtures and mocked API calls.

For an offline backend without touching any existing database, use the existing
project-local Python virtual environment, change to `backend`, and set the
following **process-local** variables before starting Uvicorn:

```powershell
$env:DATABASE_URL = 'sqlite://'
$env:AI_PROVIDER = 'fake'
$env:GROQ_API_KEY = ''
$env:GEMINI_API_KEY = ''
$env:CORS_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Invoke `python` via the existing virtual environment's full executable path if
it is not activated. In-memory data is lost when that process stops. The fake
provider is a deterministic RQ-014 demo, not general requirement understanding.
Until `app.engine.interface.check_spec` is present, rules stay unverified and
approval intentionally returns `409 SPEC_NOT_APPROVABLE`. It is now present:
analysis grounds every rule, so the full demo (create, analyse, resolve,
approve) works offline. `DEVELOPER` cannot analyze, resolve, or approve
and receives `403 FORBIDDEN`. No external AI calls are needed for Part 1.

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

Set `MOCK_VERSION` to `1.3.0-b`, `1.3.0-c`, `1.4.0` or `1.5.0` and restart the server to change implementation, or switch at runtime with the loopback-only development endpoint `POST /admin/version` (`{"version": "1.5.0"}`; `GET` reads it, `DELETE` returns to `MOCK_VERSION`). Member 1 agreed to this mechanism for the backend run flow; it is not a request header or browser parameter. The fixed API route is `POST http://127.0.0.1:9000/v1/pay/calculate` with `start_time`, `end_time`, `overnight`, and `meal_break_minutes`. Successful JSON contains `paid_minutes` and `overtime_minutes`; invalid inputs return HTTP 422. Successful responses include `X-Mock-Version`.

With the backend (`MOCK_API_BASE_URL` pointing at the mock) and the mock running on loopback ports, `python -m scripts.e2e_live --backend http://127.0.0.1:8000 --mock http://127.0.0.1:9000` runs the whole journey over real HTTP (requirement, specification, tests, runs on every mock version, defects, change impact, drift, metrics, audit) and exits non-zero if any step fails.

Example:

```powershell
$body = @{ start_time='22:00'; end_time='07:00'; overnight=$true; meal_break_minutes=30 } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:9000/v1/pay/calculate' -Method Post -ContentType 'application/json' -Body $body
```

With `MOCK_VERSION=1.4.0`, this returns `paid_minutes=510`, `overtime_minutes=30`. With `1.3.0`, it returns `0` and `0`; the same approved `PAID_EQUALS` case fails. Those values are verified by the local tests; they are synthetic demonstration data.

## One-command demo (Windows PowerShell, from the repository root)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1     # mock 1.3.0 on :9000, backend on :8000, RQ-014 seeded
cd frontend; npm run dev                                            # UI at http://127.0.0.1:5173
powershell -ExecutionPolicy Bypass -File scripts\reset_demo.ps1   # stop servers, delete only the temporary demo database
```

`run_demo.ps1` uses a project-local virtual environment (`.venv`, or `-Python <path>`), installs backend
requirements only if they are missing (`-SkipInstall` forbids that), and always uses a **temporary** SQLite file under
`.tmp\demo`: any `-DatabasePath` outside `.tmp` is refused before anything starts, and the development database is never
used. The AI provider is `fake` unless `AI_PROVIDER` is set in your environment or `backend\.env`. Ports are
configurable (`-BackendPort`, `-MockPort`); an occupied port stops the script instead of killing anything. `reset_demo.ps1`
stops only the uvicorn processes the demo recorded, deletes only `specguard-demo.db*` under `.tmp\demo`, resets the mock to
1.3.0, and supports `-WhatIf`. `scripts\seed_demo.py` is idempotent and creates RQ-014 without analysing or approving it.

## Configuration

Copy `backend\.env.example` to `backend\.env` (never commit it). Process environment variables override the file.

| Variable | Default | Meaning |
|---|---|---|
| `APP_NAME`, `APP_ENV`, `DEBUG` | `SpecGuard 2.0`, `development`, `true` | Application metadata; `DEBUG` never returns stack traces to clients. |
| `DATABASE_URL` | `sqlite:///./specguard.db` | SQLAlchemy URL. Use `sqlite://` for an in-memory database. |
| `AI_PROVIDER` | `groq` in the example file | `fake`, `groq`, `ollama`, `hosted_open_weight`. `gemini` is reserved: selecting it returns 503 "not implemented in this build". |
| `GROQ_API_KEY`, `GROQ_MODEL` | empty | Personal credentials, only where policy permits. Never logged or returned. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | empty | Reserved; no provider is implemented. |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `http://127.0.0.1:11434`, empty | Local model; the URL must be loopback. |
| `HOSTED_OPEN_WEIGHT_BASE_URL`, `_API_KEY`, `_MODEL` | empty | OpenAI-compatible endpoint; the URL must be `https`. |
| `AI_TIMEOUT_SECONDS`, `AI_MAX_RETRIES` | `30`, `1` | Per-call timeout and schema-repair retries. |
| `MOCK_API_BASE_URL` | `http://localhost:9000` | System under test for runs; loopback only, otherwise runs are refused with 503. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins. |
| `LOG_LEVEL` | `INFO` | Python logging level. |
| `MOCK_VERSION` | `1.4.0` | Mock implementation at start-up: `1.3.0`, `1.3.0-b`, `1.3.0-c`, `1.4.0`, `1.5.0`. |
| `MOCK_MEAL_MIN` | `30` | Shortest meal break (minutes) the mock deducts. |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend only (`frontend\.env`); never put secrets in `VITE_*`. |
| `SPECGUARD_ENABLE_HTTP_TESTS` | unset | `1` enables the loopback-socket tests. |

Check a provider without any network call, then (optionally, with your own credentials) make one live call:

```powershell
python -m scripts.check_ai_provider            # configuration only; exit 0 = configured, 2 = not
python -m scripts.check_ai_provider --live     # one RQ-014 extraction; prints schema validity, retries, latency
```

## Demo script (about 10 minutes)

Frontend Part 1 covers steps 1-4. Part 2 screens are not built yet, so steps 5-9 use the API docs at
`http://127.0.0.1:8000/docs` (or `python -m scripts.e2e_live`, which runs all of it and prints one line per step).
The numbers below were measured in live runs with the fake provider and mock 1.3.0 started by `run_demo.ps1`.

1. Open the UI as **Asha (Business Analyst)**; RQ-014 is already listed (version 1, three policy versions attached).
2. Click **Analyse**: the specification has 4 grounded rules (`SHIFT_SPAN`, `MEAL_DEDUCTION`, `OT_THRESHOLD`,
   `END_BEFORE_START`) and one ambiguity: "If the recorded meal break is shorter than 30 minutes, is it deducted?"
3. Resolve it (option 1: deduct only breaks of 30 minutes or more) and **Approve**. Approval is refused while any rule is
   ungrounded or any ambiguity is open.
4. As **Developer**, try to approve: `403 FORBIDDEN`.
5. `POST /specs/{spec_id}/design-tests`: 17 tests: 14 engine tests (`DRAFT`) and 3 AI edge cases (1 `DRAFT`, 2 `BLOCKED` by
   validation). Calling it again adds nothing (`added: 0`, `ai_edge_cases: "already_present"`).
6. `POST /tests/review` as **QA Engineer**: approving a blocked test is refused per test (`TEST_NOT_APPROVABLE`, naming the
   failed checks); approving the 14 engine tests succeeds. A Developer receives `403`.
7. `POST /runs` against the mock. Switching the mock with `POST :9000/admin/version` gives these failing tests:
   1.3.0 -> TC-005/007/008; 1.3.0-b -> TC-002/003/008; 1.3.0-c -> TC-005/006/008; 1.4.0 -> none (14/14). Each failure is
   clustered into a defect; defects become `FIXED` after the green run and `VERIFIED` after a second one.
8. Add RQ-014 version 2 (policy `POL-OT-01@v2`, threshold 450), analyse, resolve and approve it, then
   `POST /specs/{new_spec_id}/impact` with `from_spec_id`. Counts: 2 STALE_EXPECTED, 4 OBSOLETE, 3 NEW, 11 UNAFFECTED when
   `design-tests` was run on the new specification first. Calling impact first gives 2/5/3/10 plus two warnings. Run the new
   tests on 1.4.0 (drift: TC-003/008 fail) and on 1.5.0 (14/14 pass).
9. `GET /metrics/overview` and `GET /audit`: counts and the hash-chained trail of every step above.

If the UI or mock gets into an odd state, run `reset_demo.ps1` and start again.

## Domain rules and limitations

Only 24-hour `HH:MM` local wall-clock times are supported. DST and time zones are excluded. Equal start/end times, shifts longer than 960 minutes, malformed times, negative meals, meals longer than shift span, and earlier clock-out without `overnight=true` are invalid. `overnight=true` requires the end clock time to precede the start clock time. The mock returns 422 for invalid requests. The oracle accepts only a 480-minute per-shift threshold. A meal is deducted once.

Runner limit: 1–100 cases, 2048-byte input per case, 16 KiB response per case, and 3-second HTTP timeout. No retries. The endpoint is fixed to loopback. The fixed URL must resolve to the locally controlled mock; production network isolation and trusted approval persistence are integration responsibilities. Blocking findings stop execution. V11 warnings require acknowledgment in the trusted approval record. The `meal_break_minutes` input represents an already-approved unpaid break; no break-approval workflow exists here.

The sandbox blocks loopback sockets: even `asyncio.new_event_loop()` stalls in Python's Windows `socketpair` fallback. With permitted loopback access, the event loop, Uvicorn, real HTTP requests, the controlled runner, and all 18 tests worked. In the restricted shell, 17 tests pass and the one in-process HTTP test skips. Dependency installation from PyPI failed here because DNS access is unavailable; preinstalled FastAPI, Pydantic and HTTPX allowed `unittest` verification. Pytest and GitHub Actions have not run locally. Run the documented install and pytest commands on a networked developer machine.

No license has been chosen. The team must agree before licensing teammates' work.

**Licence and terms placeholder (to be completed by the team, not asserted here):** if a hosted AI provider such as Groq is used,
its model licence, service terms, data-use and data-retention terms apply and must be reviewed and accepted by the account
holder before any non-synthetic data is sent. This repository ships only synthetic data and a deterministic fake provider.

No private GitHub repository was created from the original workspace: local `gh auth status` reported an invalid token. From an authenticated account, after confirming the intended owner and that no repo with this name exists:

```powershell
gh auth login -h github.com
gh repo create SpecGuard-2.0 --private --source . --remote origin --push
```

The local default branch is `main`. Four collaborator usernames are still needed; no invitations have been sent. Use feature branches and reviewed pull requests for integration.
