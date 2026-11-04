# AI layer integration

The AI layer is provider-independent and returns the shared
`RequirementExtraction` contract from `backend/app/core/contracts.py`.

## Fake provider

Use the fake provider for local development and tests:

```powershell
$env:AI_PROVIDER = "fake"
```

```python
from app.ai.extractor import extract_requirement
from app.ai.fake_provider import FakeProvider

result = extract_requirement(
    "For an overnight shift, deduct an unpaid meal and apply overtime above 480 paid minutes.",
    [
        {"ref": "POL-OT-01@v1", "rule_text": "Paid minutes above 480 in one shift are overtime."},
        {"ref": "POL-MEAL-02@v1", "rule_text": "Deduct an approved unpaid meal once from shift span."},
        {"ref": "POL-DATE-03@v1", "rule_text": "A valid midnight crossing remains one shift."},
    ],
    FakeProvider(),
)
print(result.extraction.model_dump_json(indent=2))
```

The result contains typed rules, policy references, exact source spans, ambiguities,
and assumptions. It never contains oracle-calculated expected test results.

## Local Ollama

Set these variables after installing and running Ollama locally:

```powershell
$env:AI_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "your-json-capable-model"
```

The adapter sends `temperature=0.1`, requests JSON format, and disables proxy
environment variables. A provider failure is retried once and then falls back to
the fake provider.

## Hosted open-weight provider

The hosted adapter expects an OpenAI-compatible `/chat/completions` endpoint:

```text
AI_PROVIDER=hosted_open_weight
HOSTED_OPEN_WEIGHT_BASE_URL=https://provider.example/v1
HOSTED_OPEN_WEIGHT_API_KEY=<secret>
HOSTED_OPEN_WEIGHT_MODEL=<model>
```

Do not pass requirement text as system instructions. The prompt delimits it as
untrusted data, and the shared Pydantic contracts reject executable content.

## Edge-case suggestions

`app.ai.edge_cases.suggest_edge_cases()` returns additional inputs only.
Member 2's deterministic oracle must calculate expected values and decide whether
each input is accepted or rejected.
