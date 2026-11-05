# Foundation implementation reference

This document summarizes the foundation that supports the SpecGuard
application. It is intentionally concise; executable behavior is defined by
the source code, tests, and [API_CONTRACTS.md](API_CONTRACTS.md).

## Foundation components

| Area | Implementation |
|---|---|
| API | FastAPI application in `backend/app/main.py` |
| Configuration | Typed settings with environment overrides in `backend/app/core/config.py` |
| Persistence | SQLAlchemy models and SQLite session management |
| Contracts | Shared request and response models in `backend/app/core/contracts.py` |
| Errors | Structured error responses with trace IDs |
| AI | Provider adapter with structured-output validation |
| Quality engine | Oracle, generation, validation, execution, clustering, and impact analysis |
| Frontend | React, TypeScript, Vite, and Tailwind |
| System under test | Versioned loopback Time-to-Pay mock |

## Runtime configuration

Copy the example configuration before using a non-default setup:

```powershell
Copy-Item backend\.env.example backend\.env
```

For deterministic local evaluation:

```powershell
$env:AI_PROVIDER = 'fake'
$env:DATABASE_URL = 'sqlite://'
$env:CORS_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173'
```

The demo script sets safe temporary database and loopback service values
automatically. Secrets belong only in the untracked `backend\.env`; they must
never be committed or placed in frontend `VITE_*` variables.

## Install and run

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

The frontend is available at `http://127.0.0.1:5173`. The backend API and
interactive documentation are available at
`http://127.0.0.1:8000` and `/docs`.

## Verification commands

```powershell
$env:SPECGUARD_ENABLE_HTTP_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

From `frontend`:

```powershell
npm run build
npm test
npm run lint
```

For a complete local workflow:

```powershell
.\.venv\Scripts\python.exe -m scripts.e2e_live `
  --backend http://127.0.0.1:8000 `
  --mock http://127.0.0.1:9000
```

## Design guarantees

- Unknown contract fields are rejected.
- State-changing requests carry an actor and role.
- Trace IDs are returned in responses and structured errors.
- AI output is validated against shared schemas and never silently replaced
  by another provider.
- Expected execution values come from the deterministic oracle, not the AI or
  the mock response.
- Execution uses only trusted reviewed cases and a loopback target.
- Audit events record state-changing workflow actions.

For provider-specific behavior, see [ai-integration.md](ai-integration.md).
