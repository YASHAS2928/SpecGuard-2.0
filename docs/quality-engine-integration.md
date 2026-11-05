# Quality-engine integration

## Status

The backend uses one quality-engine interface:

- `backend/app/engine/protocol.py` defines the `QualityEngine` contract.
- `backend/app/engine/quality_engine.py` provides the implementation.
- The implementation composes the oracle, validator, grounding checks, runner,
  failure clustering, and change-impact classification.

The backend depends on the interface rather than on individual engine
implementation details. This keeps the workflow testable and allows the
engine to be exercised independently.

## Engine responsibilities

| Component | Responsibility |
|---|---|
| Oracle | Calculates shift span, paid minutes, and overtime independently of AI and the mock service. |
| Test generator | Produces deterministic boundary, equivalence, overnight, deduction, decision-table, and negative cases. |
| Validator | Applies schema, grounding, policy, date, oracle, duplicate, coverage, safety, and target checks. |
| Runner | Executes only freshly validated and trusted approved cases against the loopback target. |
| Defect clustering | Groups observed failures by rule, partition, and test technique. |
| Impact classifier | Compares tests across requirement or policy versions. |

The engine supports specification-driven thresholds and qualifying meal
breaks. The default demonstration uses a 480-minute threshold and deducts the
approved unpaid meal once.

## Trust and execution boundaries

The AI layer may suggest rules, expected values, or edge cases, but it never
sets the authoritative expected result. The deterministic oracle calculates
expected values and flags disagreements with AI claims.

Before execution, the runner requires a server-side lookup of the canonical
reviewed case. The submitted case and findings must match the stored
snapshot, the approval must be bound to the case version, and warnings require
explicit reviewer acknowledgment. This lookup must come from trusted
persistence; browser-supplied approval flags are not accepted.

Execution is limited to the configured loopback mock target. Redirects are
disabled, timeouts and response sizes are bounded, retries are disabled, and
generated code is never executed. The supported assertions are
`PAID_EQUALS`, `OT_EQUALS`, and `REJECTS`.

## Validation and lifecycle

Validation findings use the following categories:

- `V01` schema
- `V02` grounding and source references
- `V03` policy references
- `V04` policy dates
- `V05` supported rules
- `V06` requirement and criterion references
- `V07` oracle expectations
- `V08` AI expected-value claims
- `V09` duplicates
- `V10` required coverage
- `V11` suspicious instructions
- `V12` execution target

Blocking findings prevent approval or execution. Warnings require explicit
reviewer acknowledgment. Editing a test creates a new version and invalidates
the previous approval.

The intended test lifecycle is:

```text
DRAFT -> VALID -> APPROVED -> EXECUTED
             \-> BLOCKED
```

Requirements and tests are versioned snapshots. Tests remain linked to the
exact requirement version, acceptance criterion, and policy versions used to
create them.

## Domain assumptions

The demonstration uses fictional policies and 24-hour local `HH:MM` times.
Time zones and daylight-saving transitions are outside scope. The meal input
represents an already-approved unpaid break; the narrow mock contract does not
model a separate break-approval event. Domain-invalid requests return HTTP
422. The mock returns `X-Mock-Version`, which the runner verifies.

For API payloads and endpoint contracts, see
[API_CONTRACTS.md](API_CONTRACTS.md).
