# AI layer integration

The AI layer is provider-independent and returns the shared
`RequirementExtraction` contract from `backend/app/core/contracts.py`. Every
provider implements the frozen `RequirementAI` protocol
(`app/ai/integration_interface.py`) and is selected by `AI_PROVIDER` through the
factory in `app/ai/adapter.py`.

| `AI_PROVIDER` | Implementation | Needs |
|---|---|---|
| `fake` | `app/ai/fake_provider.py` | nothing (offline, deterministic RQ-014 demo) |
| `ollama` | `app/ai/ollama_provider.py` | `OLLAMA_MODEL`; Ollama on a loopback URL |
| `hosted_open_weight` | `app/ai/hosted_provider.py` | `HOSTED_OPEN_WEIGHT_BASE_URL` (https), `_API_KEY`, `_MODEL` |
| `groq` | `app/ai/groq_provider.py` (thin configuration of the shared OpenAI-compatible client) | `GROQ_API_KEY`, `GROQ_MODEL` |
| `gemini` | none | **not implemented**: the API answers 503 saying so, before asking for any key |

An unconfigured or unimplemented provider returns **503
`AI_PROVIDER_NOT_CONFIGURED`**. There is **no silent fallback**: if a provider is
unreachable or keeps returning invalid output, the API returns **502
`AI_PROVIDER_ERROR` / `AI_OUTPUT_INVALID`**, the failed call is logged in
`llm_calls` with `fallback=false`, and no specification is stored.

## How a call works

1. `app/ai/prompts.py` builds a versioned prompt (`ext-1.1`). It embeds the JSON
   schema of the contract and delimits the requirement and policy text as
   untrusted data.
2. A `CompletionClient` (`app/ai/clients.py`) returns text.
3. `app/ai/structured.py` validates the text against the contract. Invalid output
   is retried up to `AI_MAX_RETRIES` times, sending back the validation errors
   (location and message only, never the model's output). Unreachable-provider
   failures are retried the same way.
4. The result is an `AIResult` with provider, model, prompt version, retries,
   latency and token counts for the `llm_calls` log.

Error messages never contain URLs, API keys, prompts or response bodies.

## Fake provider

Use the fake provider for local development and tests:

```powershell
$env:AI_PROVIDER = "fake"
```

It returns the RQ-014 sample extraction adapted to the attached policies and is
always labelled `mode: "fake"`. It does not read arbitrary requirements.

## Local Ollama

```powershell
$env:AI_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "your-json-capable-model"
```

`OLLAMA_BASE_URL` must be a **loopback** URL (`127.0.0.1`, `localhost`, `[::1]`),
so requirement text never leaves the machine. The client sends `temperature=0.1`,
requests JSON format, ignores proxy environment variables and does not follow
redirects.

## Hosted open-weight provider

The hosted adapter expects an OpenAI-compatible `/chat/completions` endpoint:

```text
AI_PROVIDER=hosted_open_weight
HOSTED_OPEN_WEIGHT_BASE_URL=https://provider.example/v1
HOSTED_OPEN_WEIGHT_API_KEY=<secret>
HOSTED_OPEN_WEIGHT_MODEL=<model>
```

The base URL must be `https://` without embedded credentials, and the key is
sent only as a bearer header. **Requirement text is sent to that host**, so enable
it only with synthetic data or when company policy permits external AI services.
Put real keys only in an untracked `backend/.env`, never in `VITE_*` variables.

## Edge-case suggestions

`suggest_edge_cases` is part of `RequirementAI` and returns
`app.ai.schemas.EdgeCaseSuggestion` items (inputs, assertion template, optional
`claimed_expected`). The model only suggests inputs; the deterministic oracle
computes the real expected values and a mismatch with `claimed_expected` is
flagged (V08).

## Database note

`ollama` and `hosted_open_weight` were added to the `AIProvider` enum, which is
enforced by CHECK constraints on `llm_calls.provider` and `eval_runs.provider`.
Databases created before this change must be migrated before those providers can
be logged. New and in-memory databases are unaffected.
