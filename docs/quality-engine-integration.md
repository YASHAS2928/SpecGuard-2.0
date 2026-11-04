# Quality-engine integration proposal for Member 1

## Status: integrated behind one protocol (backend Milestones 6-7)

There is **one** Quality Engine. The backend depends only on `app/engine/protocol.py` (`QualityEngine`); `QualityEngineImpl` in `app/engine/quality_engine.py` is the single implementation and **wraps Member 2's modules instead of duplicating them**: `oracle.calculate_span` / `deduct_meal` (reused), `validator.validate_cases` (all of V01-V12), `defect_clustering.cluster_failures`, `grounding.grounded` (through `interface.check_spec`) and the allowlisted `runner.executor.execute_cases`. Two things Member 2's modules could not do were added as backward-compatible options, not rewrites:

* **Spec-driven oracle.** `oracle.calculate` accepts only a 480-minute threshold (and always deducts the whole meal). `make_oracle(threshold, min_qualifying)` computes the same values for 480/0 (cross-checked over a grid, including rejections, in `test_quality_engine_impl.py`) and supports the threshold and meal minimum of the approved spec (450 gives 60 overtime minutes for 22:00-07:00 with a 30-minute meal).
* **Smallest teammate-file changes:** `validator.validate_cases(..., oracle=calculate)` and `executor.execute_cases(..., allowed_target=TARGET, oracle=calculate)` take the oracle and allowlisted target from the caller; `executor` imports the oracle relatively (the absolute `backend.app...` import failed when the API ran from `backend/`) and accepts mock version `1.5.0`. Defaults keep the previous behaviour.

Decisions: the AI never sets expected values; test designs for threshold 480 equal Member 2's `generate_cases` (cross-check test); policy dates for tests are evaluated on or after the latest `effective_from` of the attached policies; V04 at spec level blocks only expired policies. The test-case validator keeps its own stricter V04 and takes the evaluation date from the caller.

## Original proposal (historical)

These are proposed shapes, **not finalized shared Pydantic contracts or routes**. The engine deliberately returns plain dictionaries and does not define shared models. The PDF lists similar MVP entities but leaves field names and ownership open. Keep `backend/app/core/contracts.py`, database models and backend routes under Member 1's ownership.

## Exact callable functions

```python
oracle.calculate(start_time: str, end_time: str, overnight: bool,
                 meal_break_minutes: int, threshold_minutes: int = 480) -> PayResult
test_generator.generate_cases(requirement_id: str, criterion_id: str | None = None,
                              policy_ids: list[str] | None = None) -> list[dict]
validator.validate_cases(cases: list[dict], *, requirements: dict, criteria: dict,
                         policies: dict, sources: dict[str, str] | None,
                         on_date: date, target: str = TARGET,
                         required_partitions: set[str] | None = None) -> list[dict]
executor.execute_cases(cases: list[dict], *, selected_version: str, issues: list[dict],
                       load_reviewed_case: Callable[[str], dict | None],
                       target: str = TARGET, client: httpx.Client | None = None) -> list[dict]
defect_clustering.cluster_failures(results: list[dict], cases: list[dict]) -> list[dict]
```

The caller must supply authoritative requirement, criterion, policy and source registries. Unknown or unavailable source text produces V02 BLOCK. Requirement/criterion IDs must be real. `load_reviewed_case(test_id)` must be a server-side adapter over authoritative persistence and return `{case,issues,approval}`. The runner requires the submitted case and findings to equal the stored snapshot, an approval bound to the case ID and version, a nonempty reviewer ID, and explicit acknowledgment for warnings. Missing or stale evidence blocks before HTTP. This callback must never be supplied by a browser client; Member 1's route and persistence layer must authenticate the reviewer.

## Proposed entity shapes and decisions

| Entity | Proposed fields | Decision needed |
| --- | --- | --- |
| Requirement | `id,title,text,policy_ids,status,version,created_at` | Immutable version ID vs mutable record; text source ID |
| PolicySource | `id,version,effective_from,effective_to,rule_text,source_type` | Effective dates inclusive; version lookup |
| ExtractedRule | `key,requirement_id,policy_ids,parameters,source_spans,status` | Allowed rule key registry; review state |
| AcceptanceCriterion | `id,requirement_id,given,when,then,source_ids,review_status` | Criterion version and approval binding |
| GeneratedTestCase | `id,version,requirement_id,criterion_id,policy_ids,rule_key,technique,partition,inputs,assertion_type,expected,ai_claimed_expected,source_spans,validation_state,approval_state` | Stable ID and immutable revision strategy |
| ValidationIssue | `code,severity,message,test_id,field_path,details` | Whether warnings permit review; issue storage |
| TestApproval | `test_id,case_version,reviewer_id,decision,timestamp` | Authenticated reviewer and stale-approval invalidation |
| ExecutionRequest | `test_ids,selected_version,actor_id` | Version selector source and run authorization |
| ExecutionResult | `run_id,test_id,selected_version,assertion_type,expected,actual,status,error,duration_ms,timestamp,requirement_id,criterion_id,policy_ids,rule_key,partition,technique` | Result persistence and trace ID |
| DefectCluster | `cluster_id,rule_key,partition,technique,failure_count,test_ids` | Run scope and aggregation lifetime |
| AuditEvent | `entity_id,entity_version,actor_id,actor_role,action,timestamp,before_hash,after_hash` | Immutable append-only store and actor identity |

Test lifecycle proposal: `DRAFT -> VALID -> APPROVED -> EXECUTED`; validation BLOCK leaves `BLOCKED`; editing a case makes a new version and invalidates prior approval. `REJECTED` is a reviewer decision, not an executable state. Requirement versions should be immutable snapshots; tests bind to the exact requirement version and policy version. Policy effective dates should be inclusive in the agreed local date domain; an absent `effective_to` means unbounded. Existing code currently looks up by policy ID and date, and requires an adapter once versioned policies exist. The mock selector is the server-side `MOCK_VERSION` environment variable and requires server restart; it is not request-controlled. The runner supports `PAID_EQUALS`, `OT_EQUALS`, `REJECTS`. Errors should use an agreed `{code,message,details,trace_id}` envelope at Member 1's API boundary; the mock currently uses FastAPI's native 422 `detail` shape. `meal_break_minutes` assumes an already-approved unpaid break; no approval event is represented by this narrow mock contract.

The synthetic policies in `policies/sample_policies.json` are fictional. Domain-invalid requests should return 422. `REJECTS` passes only on 422; a timeout or 5xx is ERROR. Successful mock responses have the version header `X-Mock-Version`, which the runner checks. The runner must be called only after fresh validation of the full plan and trusted approval lookup.

## Proposed JSON adapters

```json
{
  "id": "RQ-014-overnight_with_break",
  "version": 1,
  "requirement_id": "RQ-014",
  "criterion_id": "AC-01",
  "policy_ids": ["POL-OT-01", "POL-MEAL-02", "POL-DATE-03"],
  "rule_key": "RQ-014:TIME_TO_PAY",
  "technique": "OVERNIGHT",
  "partition": "overnight",
  "inputs": {"start_time": "22:00", "end_time": "07:00", "overnight": true, "meal_break_minutes": 30},
  "assertion_type": "PAID_EQUALS",
  "expected": {"paid_minutes": 510, "overtime_minutes": 30},
  "ai_claimed_expected": null,
  "source_spans": [{"source_id": "RQ-014", "start": 0, "end": 18, "text": "For overnight work"}],
  "validation_state": "VALID",
  "approval_state": "APPROVED"
}
```

Provisional validation finding:

```json
{"code": "V03", "severity": "BLOCK", "message": "unknown policy", "test_id": "RQ-014-overnight_with_break", "details": {"policy_id": "POL-OT-99"}}
```

Provisional trusted lookup response (the `case` must be the complete canonical test object shown above; this excerpt illustrates the wrapper):

```json
{"case": {"id": "RQ-014-overnight_with_break", "version": 1, "requirement_id": "RQ-014", "criterion_id": "AC-01", "policy_ids": ["POL-OT-01", "POL-MEAL-02", "POL-DATE-03"], "rule_key": "RQ-014:TIME_TO_PAY", "technique": "OVERNIGHT", "partition": "overnight", "inputs": {"start_time": "22:00", "end_time": "07:00", "overnight": true, "meal_break_minutes": 30}, "assertion_type": "PAID_EQUALS", "expected": {"paid_minutes": 510, "overtime_minutes": 30}, "ai_claimed_expected": null, "source_spans": [{"source_id": "RQ-014", "start": 0, "end": 18, "text": "For overnight work"}], "validation_state": "VALID", "approval_state": "APPROVED"}, "issues": [], "approval": {"test_id": "RQ-014-overnight_with_break", "case_version": 1, "decision": "APPROVED", "reviewer_id": "qa-reviewer", "warnings_acknowledged": false}}
```

Provisional execution result; runtime IDs, timestamps and durations vary:

```json
{"run_id": "<runtime UUID>", "test_id": "RQ-014-overnight_with_break", "selected_version": "1.3.0", "assertion_type": "PAID_EQUALS", "expected": {"paid_minutes": 510, "overtime_minutes": 30}, "actual": {"paid_minutes": 0, "overtime_minutes": 0}, "status": "FAIL", "error": null, "duration_ms": "<runtime number>", "requirement_id": "RQ-014", "criterion_id": "AC-01", "policy_ids": ["POL-OT-01", "POL-MEAL-02", "POL-DATE-03"], "rule_key": "RQ-014:TIME_TO_PAY", "partition": "overnight", "technique": "OVERNIGHT", "timestamp": "<runtime ISO timestamp>"}
```

A generated draft uses `validation_state=DRAFT` and `approval_state=PENDING`; its final approval must be a persisted human decision. The same case against `1.4.0` yields PASS and `actual={"paid_minutes":510,"overtime_minutes":30}`. A cluster of the one failing overnight test has `rule_key=RQ-014:TIME_TO_PAY`, `partition=overnight`, `technique=OVERNIGHT`, `failure_count=1`, and its test ID in `test_ids`.

## Validation behavior

V01 schema BLOCK; V02 ungrounded source span BLOCK; V03 unknown or missing required policy BLOCK; V04 policy not effective BLOCK; V05 unsupported rule BLOCK; V06 broken trace BLOCK; V07 oracle error or expected mismatch BLOCK; V08 AI claim mismatch BLOCK; V09 duplicate BLOCK; V10 coverage gap BLOCK; V11 suspicious instruction WARNING with explicit reviewer acknowledgment required; V12 forbidden target BLOCK. V11 is a review signal only and is not a complete prompt-injection defense. Source spans use Python string character offsets, so Member 1 must freeze normalization and offset semantics before generating spans in the AI layer.

## Outstanding integration questions

1. What are the finalized shared Pydantic names, required fields, and serialization aliases?
2. Which persisted record is authoritative for each requirement, criterion, policy version, case revision, validation finding, and approval event?
3. How does the reviewer identity and case version reach the runner through a trusted backend path?
4. Is the server-side `MOCK_VERSION` restart workflow acceptable for the demo, or should Member 1 choose a different **server-side** selector before UI integration?
5. Which Member 1 routes will expose generation, validation, review, run and result records? No routes are defined here.
6. What exact source text normalization and policy version/date semantics will the AI and frontend use?
7. How will Member 1 persist and audit the explicit reviewer acknowledgment for V11 warnings?

No actual Dayforce systems or records are used. The Python engine remains callable if the AI provider is unavailable.
