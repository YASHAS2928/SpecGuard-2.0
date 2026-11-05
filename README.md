# SpecGuard 2.0

SpecGuard is a quality-engineering prototype that turns a business
requirement into a traceable, reviewable, and executable test workflow.

The demonstration requirement, **RQ-014**, describes an overnight shift with
an unpaid meal break and overtime after **480 paid minutes**. SpecGuard
extracts testable rules, identifies ambiguities, generates boundary and
negative tests, validates expected results independently, executes approved
tests against a controlled service, clusters failures into defects, and
reports change impact, drift, metrics, and audit history.

All requirements, policies, identities, and calculations in this repository
are fictional. This is not a Dayforce integration or a production payroll
engine.

## Quick links

- [How the system works](#how-the-system-works)
- [Architecture](#architecture)
- [Run the complete demo](#run-the-complete-demo)
- [Verify the project](#verify-the-project)
- [API documentation](#api-documentation)
- [AI providers](#ai-providers)
- [Configuration](#configuration)
- [Scope and limitations](#scope-and-limitations)
- [API contracts](docs/API_CONTRACTS.md)
- [Integration decisions](docs/quality-engine-integration.md)
- [AI integration](docs/ai-integration.md)
- [Phase 2 verification](docs/phase2-verification.md)

## How the system works

1. A business analyst creates a requirement and associates approved policy
   versions.
2. The analysis layer produces a specification with grounded rules,
   acceptance criteria, and explicit ambiguities.
3. A reviewer resolves or defers ambiguities. Specifications cannot be
   approved while required blockers remain.
4. The quality engine generates deterministic engine tests and AI-assisted
   edge-case candidates.
5. Validation checks schemas, source references, policy links, expected
   values, duplicate cases, coverage, and suspicious instructions.
6. A QA engineer reviews the generated tests. Only trusted, approved cases
   can be executed.
7. The runner calculates expected results with an independent oracle, calls
   the local mock service, records pass/fail results, and clusters observed
   failures into defects.
8. A new requirement or policy version can be compared with the previous
   specification to classify stale, obsolete, new, and unaffected tests.
9. Metrics and a hash-chained audit trail provide visibility into the complete
   workflow.

## Architecture

```text
┌──────────────────────┐
│ React + TypeScript UI│  Requirements, specs, reviews, runs, audit
└──────────┬───────────┘
           │ JSON over HTTP
┌──────────▼───────────┐
│ FastAPI backend       │  Workflow, roles, persistence, API contracts
└──────┬─────────┬─────┘
       │         │
       │         └── AI adapter
       │             fake provider for deterministic local evaluation
       │
       ├── Quality engine
       │   oracle, generator, validator, runner, clustering, impact
       │
       ├── SQLite database
       │   requirements, versions, specs, tests, runs, defects, audit
       │
       └── Loopback mock Time-to-Pay API
           repeatable defective and corrected service versions
```

The frontend is a Vite application. The backend is a FastAPI application
using SQLAlchemy and SQLite for local evaluation. The mock API is deliberately
local and versioned as a **system under test**. It is not the product or a
replacement for Dayforce; it gives the quality workflow a safe, repeatable
target so the same approved test suite can demonstrate both defects and a
corrected run.

### Independent calculation model

The oracle accepts 24-hour local `HH:MM` times, calculates shift span,
deducts the supplied unpaid meal break once, and calculates overtime above the
synthetic 480-minute threshold. It does not use mock responses or AI output to
derive expected values. Invalid inputs, such as malformed times, invalid
overnight flags, negative meals, or unsupported shift lengths, are rejected.

## AI providers

The AI layer uses a shared structured-output contract and does not silently
fall back between providers. The selected provider is controlled by
`AI_PROVIDER`:

- `fake`: deterministic, offline RQ-014 evaluation; recommended for review.
- `ollama`: local model through a loopback URL.
- `groq`: hosted provider configured with `GROQ_API_KEY` and `GROQ_MODEL`.
- `hosted_open_weight`: OpenAI-compatible HTTPS endpoint.

AI output is schema-validated and retried according to configuration. The
deterministic oracle remains the source of truth for expected test results.
Provider errors and invalid output are surfaced explicitly. See
[AI integration](docs/ai-integration.md) for provider requirements and data
handling.

## Run the complete demo

### Prerequisites

- Python 3.12 or newer
- Node.js 22.12+ or 24 LTS
- Windows PowerShell

From the repository root, start the backend and mock API:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1
```

The script creates or reuses `.venv`, installs backend dependencies when
needed, starts the backend at `http://127.0.0.1:8000`, starts the mock at
`http://127.0.0.1:9000`, and seeds fictional RQ-014 data into a temporary
SQLite database under `.tmp\demo`.

In a second terminal, install and start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open the UI at `http://127.0.0.1:5173`. The backend's interactive API
documentation is available at `http://127.0.0.1:8000/docs`.

To run the full workflow over real loopback HTTP while the demo is running:

```powershell
.\.venv\Scripts\python.exe -m scripts.e2e_live `
  --backend http://127.0.0.1:8000 `
  --mock http://127.0.0.1:9000
```

To stop the demo and remove only its temporary database:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reset_demo.ps1
```

## Verify the project

Run backend tests from the repository root:

```powershell
$env:SPECGUARD_ENABLE_HTTP_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Run frontend checks from `frontend`:

```powershell
npm run build
npm test
npm run lint
```

For a concise offline quality-engine demonstration:

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_quality
```

## API documentation

With the backend running:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Health check: `http://127.0.0.1:8000/health`

The mock calculation endpoint is:

```text
POST http://127.0.0.1:9000/v1/pay/calculate
```

It accepts `start_time`, `end_time`, `overnight`, and
`meal_break_minutes`. Successful responses contain `paid_minutes` and
`overtime_minutes`; invalid requests return HTTP 422.

## Configuration

Copy `backend\.env.example` to `backend\.env` for local configuration. Never
commit that file or place secrets in frontend `VITE_*` variables.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy database URL; use `sqlite://` for in-memory runs. |
| `AI_PROVIDER` | Use `fake` for deterministic offline evaluation. |
| `MOCK_API_BASE_URL` | Loopback mock used by execution runs. |
| `CORS_ORIGINS` | Allowed frontend origins. |
| `VITE_API_BASE_URL` | Backend URL used by the frontend. |
| `MOCK_VERSION` | Mock implementation: `1.3.0`, `1.3.0-b`, `1.3.0-c`, `1.4.0`, or `1.5.0`. |

The default demo uses `AI_PROVIDER=fake`, a temporary database, and loopback
services. No external AI account or network service is required for evaluation.

## Scope and limitations

This prototype uses fictional data and local loopback services. Time zones,
daylight-saving transitions, production authentication, trusted human
approval persistence, external Dayforce connectivity, and production payroll
policy behavior are outside its scope. The UI's actor and role selector is a
workflow demonstration, not authentication.
