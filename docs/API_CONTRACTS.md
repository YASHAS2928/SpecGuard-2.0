# SpecGuard 2.0 — API Contracts

All policies, requirements and data in this document are **fictional** and used for demonstration only.

Source of truth for every model: `backend/app/core/contracts.py`. The live OpenAPI spec is at `http://localhost:8000/openapi.json` and the interactive docs are at `/docs`.

## Conventions

| Topic | Rule |
|---|---|
| Base URL | `http://localhost:8000` |
| Format | JSON, UTF-8. Unknown fields are rejected (`extra="forbid"`). |
| IDs | UUID strings (version 4, e.g. `3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01`) in paths and bodies; integers are rejected. Human-readable codes (`RQ-014`, `AMB-1`, `AC-3`, `TC-012`) are for display. |
| Policy references | `POL-<AREA>-<NN>@v<version>`, e.g. `POL-OT-01@v1` |
| Trace ID | Optional `X-Trace-ID` request header (letters, digits, `.`, `_`, `-`, max 64). Always returned in the response header and in error bodies. |
| Actor | Every state-changing request carries `actor` and `actor_role`. The `SYSTEM` role is rejected for human actions. The MVP has no authentication; this is a documented limitation. |
| Roles | `BUSINESS_ANALYST`, `QA_ENGINEER`, `DEVELOPER`, `ADMIN` (`SYSTEM` appears only in audit records) |
| Times | `HH:MM`, 24-hour clock, single local timezone (daylight saving is out of scope) |
| Timestamps | ISO 8601 UTC with `Z` or `+00:00`, consistent before and after database reload. SQLite stores naive UTC; the shared `UTCDateTime` type restores `timezone.utc` on read and converts offset-aware inputs to UTC on write. Naive inputs and existing naive timestamps are treated as UTC. |

### Standard error envelope

```json
{
  "error": {
    "code": "SPEC_NOT_APPROVABLE",
    "message": "Specification 3 cannot be approved yet.",
    "details": {"open_ambiguities": ["AMB-1"], "unresolved_params": []},
    "trace_id": "demo-trace-001"
  }
}
```

| HTTP | `error.code` values |
|---|---|
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` |
| 409 | `CONFLICT`, `STATE_TRANSITION_NOT_ALLOWED`, `SPEC_NOT_APPROVABLE`, `TEST_NOT_APPROVABLE` |
| 422 | `VALIDATION_ERROR` (`details` lists `loc`, `msg`, `type`; submitted values are never echoed) |
| 502 | `AI_PROVIDER_ERROR`, `AI_OUTPUT_INVALID` |
| 503 | `AI_PROVIDER_NOT_CONFIGURED`, `INTEGRATION_UNAVAILABLE` |
| 500 | `INTERNAL_ERROR` |

### Ownership

- **M1:** Tech lead / backend
- **M2:** Quality Engine (oracle, test design, validator, runner, clustering, change-impact classification)
- **M3:** AI module (providers, prompts, extraction, edge cases, hypotheses)
- **M4:** Frontend

---

## System

### GET /health — M1 (Milestone 1)
Reports database reachability and AI provider configuration. No request body.

**200**
```json
{"status": "ok", "app": "SpecGuard 2.0", "environment": "development", "database": "ok",
 "ai": {"provider": "groq", "model": "<GROQ_MODEL>", "configured": true, "issues": []}}
```
`status` is `degraded` when the AI provider is misconfigured (with `issues` listed) or the database is unavailable. If the database is unavailable the response is **503** with the same body shape.

### GET /version — M1 (Milestone 1)
**200**
```json
{"name": "SpecGuard 2.0", "version": "2.0.0", "api_version": "v1", "environment": "development",
 "ai_provider": "groq", "ai_model": "<GROQ_MODEL>"}
```

---

## Requirements and policies

### POST /requirements — M1 (Milestone 4)
Creates a requirement and its version 1. The status starts as `DRAFT`.

**Request** (`RequirementCreate`)
```json
{
  "code": "RQ-014",
  "title": "Overnight overtime with unpaid meal break",
  "text": "For an overnight shift, calculate overtime correctly after the employee has worked the configured number of paid hours, excluding the unpaid meal break.",
  "policy_ids": ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
  "actor": "asha.ba",
  "actor_role": "BUSINESS_ANALYST"
}
```
Validation: `code` matches `^RQ-\d{3,6}$`; `title` 3–200 characters; `text` 10–4,000 characters; `policy_ids` 1–10 unique refs, each of which must exist in the registry.

**201** (`RequirementResponse`)
```json
{
  "id": "0d3f5a7c-1e2b-4c9d-8a60-4b7e9f1c2d01", "code": "RQ-014", "title": "Overnight overtime with unpaid meal break",
  "status": "DRAFT", "latest_version": 1,
  "versions": [{"id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c02", "requirement_id": "0d3f5a7c-1e2b-4c9d-8a60-4b7e9f1c2d01", "version": 1, "text": "For an overnight shift, ...",
                "policy_ids": ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
                "author": "asha.ba", "change_note": null, "created_at": "2026-11-04T10:00:00Z"}],
  "created_at": "2026-11-04T10:00:00Z", "updated_at": "2026-11-04T10:00:00Z"
}
```
**Errors:** 409 `CONFLICT` (code already exists) · 422 `VALIDATION_ERROR` (invalid fields or unknown policy ref).

### POST /requirements/{id}/versions — M1 (Milestone 4)
Creates the next immutable version. If the requirement already had an approved spec, its status becomes `CHANGED`.

**Request** (`RequirementVersionCreate`)
```json
{"text": "For an overnight shift, ...", "policy_ids": ["POL-OT-01@v2", "POL-MEAL-02@v1", "POL-DATE-03@v1"],
 "change_note": "POL-OT-01 v2 lowers the overtime threshold to 450 minutes.",
 "actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}
```
**201** `RequirementVersionResponse` (`version` = previous + 1).
**Errors:** 404 `NOT_FOUND` · 409 `CONFLICT` (identical text and policies to the latest version) · 422.

### GET /requirements/{id} — M1 (Milestone 4)
**200** `RequirementResponse` with all versions, newest last. **404** if not found.

### GET /requirements — M1 (Milestone 4)
**200** `RequirementResponse[]`, ordered by requirement code, with all versions
in ascending version order. The MVP returns the complete list without pagination.

### GET /policies — M1 (Milestone 4)
Query parameters: `effective_on` (date, optional, defaults to today), `code` (e.g. `POL-OT-01`, optional), `include_all_versions` (bool, default `false`).

**200** `PolicyResponse[]`
```json
[{"id": "8a7b6c5d-4e3f-4a21-9b0c-1d2e3f4a5b01", "policy_code": "POL-OT-01", "version": 1, "ref": "POL-OT-01@v1",
  "title": "Overtime threshold (fictional)",
  "rule_text": "For this mock business only: paid minutes above 480 in a single shift are overtime.",
  "effective_from": "2026-01-01", "effective_to": "2026-12-31", "fictional": true}]
```

### Milestone 4 reference data and audit behavior

Startup seeds missing fictional policies and mock SUT versions transactionally.
Repeating startup does not duplicate or overwrite existing rows. If an existing
seeded policy's rule text, SHA-256, or effective dates differ, startup fails
explicitly rather than replacing that policy version.

- `POL-OT-01@v1`: 480-minute threshold, effective 2026-01-01 through 2026-12-31.
- `POL-OT-01@v2`: 450-minute threshold, effective from 2027-01-01.
- `POL-MEAL-02@v1` and `POL-DATE-03@v1`: effective from 2026-01-01.
- Mock SUT `mock-time-to-pay`: versions `1.3.0` and `1.4.0`.

Policy listing uses inclusive effective-date boundaries. Requirement creation
and versioning require existing policy references and reject citing multiple
versions of one policy code. They allow announced future versions; effective-date
validation during analysis belongs to the later validation milestone.

Creating a requirement writes both requirement-created and version-created audit
events in the same transaction. Appending a version writes a version-created
event, preserving earlier versions. A new version resets `ANALYZED` to `DRAFT`;
`SPEC_APPROVED` or `CHANGED` becomes/remains `CHANGED`. Audit events include the
actor, trace ID, deterministic SHA-256 snapshot hash, and status-transition details.
Shared helpers are `app.core.audit.canonical_json`, `sha256_hex`, and
`record_audit_event`; callers commit the transaction.

These endpoints use the unprefixed paths shown above. No existing development
database is migrated by this milestone. Historical requirement deletion
protection still depends on the existing database having the current `RESTRICT`
foreign key schema. Audit immutability remains enforced by ORM listeners, not
database triggers; raw SQL or bulk operations can bypass those listeners.

---

## Analysis and specification

Analyze, resolve, and approve require `BUSINESS_ANALYST`, `QA_ENGINEER`, or
`ADMIN`. Other roles receive **403** `FORBIDDEN` (the MVP still has no
authentication).

The frozen AI protocol is `app.ai.integration_interface.RequirementAI`.
`AIResult` carries validated output and call metadata. The provider factory loads
Groq/Gemini implementations lazily and returns **503** until the selected
provider is configured and delivered. No provider silently falls back to fake.
The fake provider is a deterministic RQ-014 demonstration, not an LLM: it adapts
the threshold to the cited policy but does not interpret arbitrary requirements.
Its edge-case suggestions include one deliberately incorrect claimed expectation
for the later deterministic validator to detect.

The Quality Engine integration point is `app.engine.interface.check_spec`.
Until that interface is delivered, analysis leaves `grounded: null`, includes a
clear message, and approval is blocked. Automated workflow tests use a test-only
reference checker; this is not a production grounding implementation.

### POST /requirement-versions/{id}/analyze — M1 route, M3 AI (Milestone 5)
Runs AI extraction, then deterministic checks, and stores a `DRAFT` spec with its rules, ambiguities and assumptions.

**Request** (`AnalyzeRequirementRequest`)
```json
{"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST", "force": false}
```
**200** (`AnalyzeRequirementResponse`)
```json
{
  "spec": {
    "id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "requirement_version_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c02", "version": 1, "status": "DRAFT",
    "inputs": [{"name": "start_time", "type": "time_hhmm"}, {"name": "end_time", "type": "time_hhmm"},
               {"name": "overnight", "type": "bool"}, {"name": "meal_break_minutes", "type": "int_or_null"}],
    "outputs": ["paid_minutes", "overtime_minutes"],
    "rules": [
      {"id": "4c2a7f19-8d3e-4b5a-a601-9e8d7c6b5a07", "rule_key": "OT_THRESHOLD", "type": "THRESHOLD",
       "params": {"metric": "paid_minutes", "threshold": 480, "comparison": "gt", "scope": "per_shift", "output": "overtime_minutes"},
       "origin": "POLICY", "policy_ref": "POL-OT-01@v1",
       "source_span": "paid minutes above 480 in a single shift are overtime",
       "description": null, "grounded": true, "unresolved_params": []},
      {"id": "4c2a7f19-8d3e-4b5a-a601-9e8d7c6b5a08", "rule_key": "MEAL_DEDUCTION", "type": "DEDUCTION",
       "params": {"field": "meal_break_minutes", "deduct_if": "recorded", "min_qualifying": null},
       "origin": "NEEDS_CLARIFICATION", "policy_ref": "POL-MEAL-02@v1",
       "source_span": "Subtract a 30-minute unpaid meal break when an approved break event is present",
       "description": null, "grounded": true, "unresolved_params": ["min_qualifying"]}
    ],
    "ambiguities": [
      {"id": "6e5d4c3b-2a19-4f8e-b7d6-c5a4b3e2d104", "spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "amb_code": "AMB-1",
       "question": "If the recorded meal break is shorter than 30 minutes, is it deducted?",
       "why": "POL-MEAL-02 names a 30-minute break but does not cover partial breaks.",
       "affects_rules": ["MEAL_DEDUCTION"],
       "options": [
         {"label": "Deduct only breaks of 30 minutes or more",
          "patch": [{"op": "replace", "path": "/rules/MEAL_DEDUCTION/params/min_qualifying", "value": 30},
                    {"op": "replace", "path": "/rules/MEAL_DEDUCTION/origin", "value": "CLARIFIED"}]},
         {"label": "Deduct whatever break length was recorded",
          "patch": [{"op": "replace", "path": "/rules/MEAL_DEDUCTION/params/min_qualifying", "value": 0},
                    {"op": "replace", "path": "/rules/MEAL_DEDUCTION/origin", "value": "CLARIFIED"}]}],
       "status": "OPEN", "chosen_option_index": null, "resolved_by": null, "resolved_at": null}
    ],
    "assumptions": [{"text": "All times are in one local timezone; daylight-saving changes are out of scope.", "origin": "ASSUMED"}],
    "issues": [{"code": "V13_UNRESOLVED_PARAMETER", "severity": "BLOCK", "entity_type": "RULE", "entity_id": "4c2a7f19-8d3e-4b5a-a601-9e8d7c6b5a08",
                "message": "MEAL_DEDUCTION.min_qualifying is unresolved.", "field_path": "rules.MEAL_DEDUCTION.params.min_qualifying", "detail": null}],
    "open_ambiguities": 1, "blocking_issue_count": 1, "parent_spec_id": null,
    "approved_by": null, "approved_at": null, "created_at": "2026-11-04T10:05:00Z"
  },
  "analysis": {"mode": "llm", "provider": "groq", "model": "<GROQ_MODEL>", "prompt_version": "ext-1.0",
               "valid_first_try": true, "retries": 0, "fallback_used": false, "latency_ms": 2140,
               "llm_call_id": "b7c8d9e0-f1a2-4b3c-8d4e-5f6a7b8c9d01", "message": null}
}
```
Validation: the provider output must parse as `RequirementExtraction` (closed rule types, typed parameters, restricted patches, no URLs or code in AI text). A rule whose `source_span` isn't found in the requirement or its cited policy is stored with `grounded: false` and a `V02_UNGROUNDED_SPAN` block issue.

`open_ambiguities` counts every non-`RESOLVED` ambiguity, including `DEFERRED`.
Re-analysis supersedes earlier drafts. An approved spec remains approved until
another spec of the same requirement is approved.

**Errors:**
- 404 · 409 `CONFLICT` (an approved spec already exists for this version and `force` is false)
- 503 `AI_PROVIDER_NOT_CONFIGURED`
- 502 `AI_PROVIDER_ERROR` / `AI_OUTPUT_INVALID` (provider retry policy uses `ai_max_retries`). Failed provider calls are persisted in `llm_calls` with `fallback=false`, and no spec is stored. The response is never presented as a successful analysis. `mode: "fake"` appears only when `AI_PROVIDER=fake`.
- 503 `INTEGRATION_UNAVAILABLE` if the grounding checker fails; no draft is committed.

Analysis rejects missing cited policies rather than silently omitting them.
Malformed provider result envelopes are logged as `AI_OUTPUT_INVALID`.
A V02 grounding issue must identify a known rule via `detail.rule_key`; an
invalid checker result returns `INTEGRATION_UNAVAILABLE` and rolls back draft
creation and supersession changes.

### GET /specs/{id} — M1 (Milestone 5)
**200** `SpecResponse` with rules, ambiguities, and active validation issues.
**404** if not found; invalid UUIDs receive **422**.

### GET /requirement-versions/{id}/specs — M1 (Milestone 5)
**200** `SpecResponse[]`, ordered by spec version, oldest first.
**404** if the requirement version does not exist.

### POST /ambiguities/{id}/resolve — M1 (Milestone 5)
Applies the chosen option's patch to the `DRAFT` spec, or defers the ambiguity.

**Request** (`ResolveAmbiguityRequest`): `{"option_index": 0, "actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}` or `{"defer": true, "comment": "Waiting for payroll owner.", "actor": "asha.ba", "actor_role": "BUSINESS_ANALYST"}`. Exactly one of `option_index` / `defer` is required.

**200** `SpecResponse` (the updated spec; the ambiguity's `status` is `RESOLVED` or `DEFERRED`).
Deferred ambiguities can be resolved later. Patches are validated against the
typed rule parameters before any changes are applied.

**Errors:** 404 · 409 `STATE_TRANSITION_NOT_ALLOWED` (spec not `DRAFT`, ambiguity already `RESOLVED`, or attempting to defer it again) · 422 (`option_index` out of range or invalid patch).

### POST /specs/{id}/approve — M1 (Milestone 5)
**Request** (`ApproveSpecRequest`): `{"actor": "asha.ba", "actor_role": "BUSINESS_ANALYST", "comment": "Rules confirmed with payroll."}`

**200** `SpecResponse` with `status: "APPROVED"`, `approved_by` and `approved_at` set. A previously approved spec for the same requirement becomes `SUPERSEDED`.

**Errors:** 404 · 409 `SPEC_NOT_APPROVABLE`, e.g.
```json
{"error": {"code": "SPEC_NOT_APPROVABLE", "message": "Specification 3 cannot be approved yet.",
 "details": {"open_ambiguities": ["AMB-1"], "deferred_ambiguities": [], "unresolved_params": ["MEAL_DEDUCTION.min_qualifying"], "blocking_issues": ["V13_UNRESOLVED_PARAMETER"], "ungrounded_rules": []},
 "trace_id": "..."}}
```
· 409 `STATE_TRANSITION_NOT_ALLOWED` (spec is not `DRAFT`).

`ungrounded_rules` lists rules whose grounding check failed or did not run.
Successful approval records a review and an audit event in the same transaction.

---

## Tests

### POST /specs/{id}/design-tests — M1 route, M2 engine, M3 edge cases (Milestone 6)
Generates criteria and engine tests (boundary, partition, decision table, negative) plus optional AI edge cases. The oracle computes every `expected` value, and every test is validated.

**Request** (`DesignTestsRequest`): `{"actor": "ravi.qa", "actor_role": "QA_ENGINEER", "include_ai_edge_cases": true}`

**200** (`DesignTestsResponse`)
```json
{"spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01",
 "criteria": [{"id": "2f8e1d4c-7b3a-4a59-8e60-1c9d2b3a4e01", "spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "crit_code": "AC-1", "rule_key": "OT_THRESHOLD",
               "given": "an approved shift with paid minutes above 480",
               "when": "overtime is calculated", "then": "overtime equals paid minutes minus 480"}],
 "tests": ["<TestCaseResponse>"],
 "counts_by_technique": {"BOUNDARY": 6, "PARTITION": 4, "DECISION": 8, "NEGATIVE": 4, "EDGE": 3},
 "blocked_count": 1, "ai_edge_cases": "generated", "ai_message": null}
```
Counts in this example are illustrative; real counts depend on the spec. If the AI provider fails, engine tests are still returned, with `ai_edge_cases: "unavailable"` and an explanatory `ai_message`.

**Errors:** 404 · 409 `STATE_TRANSITION_NOT_ALLOWED` (spec not `APPROVED`) · 503 `INTEGRATION_UNAVAILABLE` (Quality Engine not integrated).

### GET /specs/{id}/tests — M1 (Milestone 6)
Query parameters: `status`, `technique`, `origin` (optional enums).

**200** `TestCaseResponse[]`
```json
[{"id": "9c4e1d7b-2a63-4f08-b5e9-1a7d3c6f8e12", "spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "tc_code": "TC-012", "origin": "ENGINE", "technique": "BOUNDARY",
  "inputs": {"start_time": "22:00", "end_time": "07:01", "overnight": true, "meal_break_minutes": 60},
  "assertion": "OT_EQUALS", "expected": {"paid_minutes": null, "overtime_minutes": 1, "rejects": false},
  "ai_claimed_expected": null, "rationale": "Paid minutes = 481: just above the threshold.",
  "risk_score": 7, "status": "DRAFT", "rule_keys": ["OT_THRESHOLD", "SHIFT_SPAN", "MEAL_DEDUCTION"],
  "criterion_codes": ["AC-1"], "policy_refs": ["POL-OT-01@v1"], "issues": [], "supersedes_id": null,
  "created_at": "2026-11-04T10:15:00Z"}]
```

### POST /tests/review — M1 (Milestone 6)
**Request** (`TestReviewRequest`): `{"test_ids": ["5e2a8c13-9b47-4d60-a1f2-6c3e0d9b7a10", "7d9b3f25-1e84-4c7a-8b06-2f5a9e1c4d11", "9c4e1d7b-2a63-4f08-b5e9-1a7d3c6f8e12"], "decision": "APPROVE", "actor": "ravi.qa", "actor_role": "QA_ENGINEER"}`. `REJECT` requires `reason`.

**Rules:**
- `BLOCKED` tests are refused.
- `AI`-origin tests are refused when more than one ID is submitted with `APPROVE` (they need individual approval).
- Only `DRAFT` or `STALE` tests can be reviewed.

**200** (`TestReviewResponse`; partial success is allowed and every refusal is explained)
```json
{"decision": "APPROVE",
 "reviewed": [{"test_id": "5e2a8c13-9b47-4d60-a1f2-6c3e0d9b7a10", "tc_code": "TC-010", "previous_status": "DRAFT", "new_status": "APPROVED"}],
 "refused": [{"test_id": "c8a1e5f3-6d92-4b17-9e40-3b7c5a2d8f27", "code": "TEST_NOT_APPROVABLE", "message": "TC-027 is BLOCKED (V05_UNSUPPORTED_RULE)."}]}
```
**Errors:** 404 (unknown test IDs) · 422.

---

## Execution and defects

### POST /runs — M1 route, M2 runner (Milestone 6)
Runs **approved** tests only, against the mock Time-to-Pay API at `MOCK_API_BASE_URL`, using the allowlisted assertion templates `PAID_EQUALS`, `OT_EQUALS` and `REJECTS`.

**Request** (`RunCreateRequest`): `{"spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "test_ids": null, "trigger": "MANUAL", "actor": "ravi.qa", "actor_role": "QA_ENGINEER"}` (`test_ids: null` means all approved tests for the spec).

**201** (`RunResponse`)
```json
{"id": "e5f6a7b8-9c0d-4e1f-a2b3-c4d5e6f7a805", "spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "sut_version": "1.3.0", "trigger": "MANUAL", "status": "COMPLETED",
 "started_at": "2026-11-04T10:20:00Z", "finished_at": "2026-11-04T10:20:02Z",
 "totals": {"total": 24, "passed": 20, "failed": 4, "errors": 0},
 "results": [{"id": "f1e2d3c4-b5a6-4978-8a9b-0c1d2e3f4a91", "run_id": "e5f6a7b8-9c0d-4e1f-a2b3-c4d5e6f7a805", "test_case_id": "9c4e1d7b-2a63-4f08-b5e9-1a7d3c6f8e12", "tc_code": "TC-012", "status": "FAIL",
              "expected": {"paid_minutes": null, "overtime_minutes": 1, "rejects": false},
              "observed": {"paid_minutes": 0, "overtime_minutes": 0},
              "failed_assertion": "overtime_minutes expected 1, observed 0", "latency_ms": 12}]}
```
An unreachable mock API produces `ERROR` results, never passes.

**Errors:** 404 · 409 `CONFLICT` (no approved tests, or listed tests aren't `APPROVED`) · 503 `INTEGRATION_UNAVAILABLE` (runner not integrated).

### GET /runs/{id} — M1 (Milestone 6)
**200** `RunResponse`. **404** if not found.

### GET /defects — M1 route, M2 clustering (Milestone 6)
Query parameters: `status`, `spec_id` (optional).

**200** `DefectResponse[]`
```json
[{"id": "d2c3b4a5-6978-4e1f-8a0b-9c8d7e6f5a02", "cluster_key": "OT_THRESHOLD|overnight=true", "title": "OT_THRESHOLD fails whenever overnight=true",
  "rule_key": "OT_THRESHOLD", "partition": {"overnight": true}, "status": "OPEN", "first_run_id": "e5f6a7b8-9c0d-4e1f-a2b3-c4d5e6f7a805",
  "evidence_result_ids": ["f1e2d3c4-b5a6-4978-8a9b-0c1d2e3f4a91", "f1e2d3c4-b5a6-4978-8a9b-0c1d2e3f4a92"], "hypothesis": null, "created_at": "2026-11-04T10:20:02Z"}]
```
`hypothesis` (P1) is always labelled `"HYPOTHESIS"` and cites result IDs.

---

## Change impact

### POST /specs/{new_id}/impact — M1 route, M2 classification (Milestone 7)
Compares an **approved** newer spec with an earlier `APPROVED` or `SUPERSEDED`
spec of the same requirement. Approving a newer spec supersedes the older one.
Impacted tests are classified, `STALE` tests leave the runnable set until
re-approved, and a rerun plan is produced.

**Request** (`ChangeImpactRequest`): `{"from_spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "actor": "ravi.qa", "actor_role": "QA_ENGINEER"}`

**201** (`ChangeImpactResponse`)
```json
{"id": "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c01", "from_spec_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01", "to_spec_id": "5d4c3b2a-1f0e-4d9c-8b7a-6f5e4d3c2b06",
 "rule_changes": [{"rule_key": "OT_THRESHOLD", "kind": "PARAM_CHANGED",
                   "before": {"threshold": 480}, "after": {"threshold": 450}, "changed_fields": ["threshold"]}],
 "impacted_criteria": ["AC-1"],
 "impacted_tests": [{"test_id": "a3b4c5d6-e7f8-4a9b-8c0d-1e2f3a4b5c14", "tc_code": "TC-014", "impact_class": "STALE_EXPECTED",
                     "reason": "Expected overtime changes under OT_THRESHOLD threshold 450.",
                     "old_expected": {"paid_minutes": null, "overtime_minutes": 30, "rejects": false},
                     "new_expected": {"paid_minutes": null, "overtime_minutes": 60, "rejects": false},
                     "replacement_test_id": null}],
 "counts": {"STALE_EXPECTED": 6, "OBSOLETE": 3, "NEW": 3, "UNAFFECTED": 12},
 "rerun_test_ids": ["a3b4c5d6-e7f8-4a9b-8c0d-1e2f3a4b5c14", "a3b4c5d6-e7f8-4a9b-8c0d-1e2f3a4b5c15"], "created_at": "2026-11-04T10:40:00Z"}
```
Counts are illustrative.

**Errors:** 404 · 409 `STATE_TRANSITION_NOT_ALLOWED` (either spec not approved, or the specs belong to different requirements) · 503 `INTEGRATION_UNAVAILABLE`.

---

## Dashboard and audit

### GET /metrics/overview — M1 (Milestone 7)
**200** (`MetricsOverviewResponse`). Every value is computed from database rows. Ratios are `null` when the denominator is 0.
```json
{"requirements_total": 1, "specs_approved": 2, "ambiguities_total": 3, "ambiguities_resolved": 3,
 "requirement_completeness": 1.0, "rules_total": 4, "rules_with_passing_test": 3, "rule_coverage": 0.75,
 "tests_by_status": {"APPROVED": 21, "BLOCKED": 1, "STALE": 0},
 "validation_blocks_by_code": {"V05_UNSUPPORTED_RULE": 1},
 "last_run": {"run_id": "e5f6a7b8-9c0d-4e1f-a2b3-c4d5e6f7a807", "sut_version": "1.4.0", "finished_at": "2026-11-04T10:45:00Z",
              "totals": {"total": 24, "passed": 21, "failed": 3, "errors": 0}},
 "open_defects": 1, "tests_impacted_pending": 0, "ai_calls_total": 3, "ai_fallbacks_total": 0,
 "generated_at": "2026-11-04T10:46:00Z"}
```

### GET /audit — M1 (Milestone 7)
Query parameters: `entity_type`, `entity_id` (UUID), `action`, `limit` (1–500, default 100), `offset` (default 0).

**200** (`AuditPage`)
```json
{"items": [{"id": "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e12", "ts": "2026-11-04T10:08:00Z", "actor": "asha.ba", "actor_role": "BUSINESS_ANALYST",
            "action": "SPEC_APPROVED", "entity_type": "SPEC", "entity_id": "3b1f6e0a-7c2d-4a9e-9f31-5d8c2e4a6b01",
            "before_hash": "<64 hex>", "after_hash": "<64 hex>", "trace_id": "demo-trace-001",
            "detail": {"comment": "Rules confirmed with payroll."}}],
 "total": 1, "limit": 100, "offset": 0}
```
Hashes are SHA-256 of canonical JSON (sorted keys, no extra whitespace).
