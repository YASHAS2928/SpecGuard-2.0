// Hand-written types matching backend/app/core/contracts.py (all IDs are UUID strings).

export type Role = 'BUSINESS_ANALYST' | 'QA_ENGINEER' | 'DEVELOPER' | 'ADMIN'

export interface Actor {
  actor: string
  actor_role: Role
}

export interface ApiErrorBody {
  code: string
  message: string
  details: unknown
  trace_id: string | null
}

export interface Policy {
  id: string
  policy_code: string
  version: number
  ref: string
  title: string
  rule_text: string
  effective_from: string
  effective_to: string | null
  fictional: boolean
}

export interface RequirementVersion {
  id: string
  requirement_id: string
  version: number
  text: string
  policy_ids: string[]
  author: string
  change_note: string | null
  created_at: string
}

export interface Requirement {
  id: string
  code: string
  title: string
  status: 'DRAFT' | 'ANALYZED' | 'SPEC_APPROVED' | 'CHANGED'
  latest_version: number
  versions: RequirementVersion[]
  created_at: string
  updated_at: string
}

export interface SpecRule {
  id: string
  rule_key: string
  type: string
  params: Record<string, unknown>
  origin: string
  policy_ref: string | null
  source_span: string
  description: string | null
  grounded: boolean | null
  unresolved_params: string[]
}

export interface PatchOp {
  op: 'replace'
  path: string
  value: string | number | boolean | null
}

export interface ClarificationOption {
  label: string
  patch: PatchOp[]
}

export interface Ambiguity {
  id: string
  spec_id: string
  amb_code: string
  question: string
  why: string
  affects_rules: string[]
  options: ClarificationOption[]
  status: 'OPEN' | 'RESOLVED' | 'DEFERRED'
  chosen_option_index: number | null
  resolved_by: string | null
  resolved_at: string | null
}

export interface Issue {
  code: string
  severity: 'BLOCK' | 'WARN'
  entity_type: string | null
  entity_id: string | null
  message: string
  field_path: string | null
  detail: Record<string, unknown> | null
}

export interface Assumption {
  text: string
  origin: string
}

export interface Spec {
  id: string
  requirement_version_id: string
  version: number
  status: 'DRAFT' | 'APPROVED' | 'SUPERSEDED'
  inputs: { name: string; type: string }[]
  outputs: string[]
  rules: SpecRule[]
  ambiguities: Ambiguity[]
  assumptions: Assumption[]
  issues: Issue[]
  open_ambiguities: number
  blocking_issue_count: number
  parent_spec_id: string | null
  approved_by: string | null
  approved_at: string | null
  created_at: string
}

export interface AnalysisMetadata {
  mode: 'llm' | 'fake' | 'manual_required'
  provider: string
  model: string | null
  prompt_version: string
  valid_first_try: boolean
  retries: number
  fallback_used: boolean
  latency_ms: number | null
  llm_call_id: string | null
  message: string | null
}

export interface AnalyzeResponse {
  spec: Spec
  analysis: AnalysisMetadata
}

// ---------------------------------------------------------------------------
// Part 2 types (Tests & Review, Run & Defects, Change Impact, Overview, Audit).
// Mirror backend/app/core/contracts.py; dates are ISO 8601 UTC strings.
// ---------------------------------------------------------------------------

export type TestStatus = 'DRAFT' | 'BLOCKED' | 'APPROVED' | 'REJECTED' | 'STALE' | 'OBSOLETE'
export type TestOrigin = 'ENGINE' | 'AI'
export type TestTechnique = 'BOUNDARY' | 'PARTITION' | 'DECISION' | 'NEGATIVE' | 'EDGE'
export type Assertion = 'PAID_EQUALS' | 'OT_EQUALS' | 'REJECTS'

export interface ExpectedResult {
  paid_minutes: number | null
  overtime_minutes: number | null
  rejects: boolean
}

/** Lenient on purpose: negative tests send deliberately invalid values such as "9am" or -1. */
export interface TestFixtureInputs {
  start_time: string
  end_time: string
  overnight: boolean
  meal_break_minutes: number | null
}

export interface TestCase {
  id: string
  spec_id: string
  tc_code: string
  origin: TestOrigin
  technique: TestTechnique
  inputs: TestFixtureInputs
  assertion: Assertion
  expected: ExpectedResult
  ai_claimed_expected: ExpectedResult | null
  rationale: string
  risk_score: number | null
  status: TestStatus
  rule_keys: string[]
  criterion_codes: string[]
  policy_refs: string[]
  issues: Issue[]
  supersedes_id: string | null
  created_at: string
}

export interface Criterion {
  id: string
  spec_id: string
  crit_code: string
  rule_key: string
  given: string
  when: string
  then: string
}

export interface DesignTestsResponse {
  spec_id: string
  criteria: Criterion[]
  tests: TestCase[]
  counts_by_technique: Partial<Record<TestTechnique, number>>
  blocked_count: number
  ai_edge_cases: 'generated' | 'unavailable' | 'disabled' | 'already_present'
  ai_message: string | null
  /** Tests stored by this call; designing again never duplicates or changes existing tests. */
  added: number
  /** Designed tests that already existed (same origin and fixture) and were left untouched. */
  already_present: number
}

export interface TestReviewItem {
  test_id: string
  tc_code: string
  previous_status: TestStatus
  new_status: TestStatus
}

export interface TestReviewRefusal {
  test_id: string
  code: string
  message: string
}

export interface TestReviewResponse {
  decision: 'APPROVE' | 'REJECT'
  reviewed: TestReviewItem[]
  refused: TestReviewRefusal[]
}

export interface RunTotals {
  total: number
  passed: number
  failed: number
  errors: number
}

export interface TestResult {
  id: string
  run_id: string
  test_case_id: string
  tc_code: string
  status: 'PASS' | 'FAIL' | 'ERROR'
  expected: ExpectedResult
  observed: Record<string, unknown> | null
  failed_assertion: string | null
  latency_ms: number | null
}

export interface Run {
  id: string
  spec_id: string
  sut_version: string
  trigger: 'MANUAL' | 'IMPACT_RERUN'
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  started_at: string
  finished_at: string | null
  totals: RunTotals
  results: TestResult[]
}

export interface Defect {
  id: string
  cluster_key: string
  title: string
  rule_key: string | null
  partition: Record<string, string | number | boolean | null>
  status: 'OPEN' | 'FIXED' | 'VERIFIED'
  first_run_id: string
  evidence_result_ids: string[]
  hypothesis: { label: 'HYPOTHESIS'; text: string; cited_result_ids: string[]; provider: string; model: string | null } | null
  created_at: string
}

export type ImpactClass = 'STALE_EXPECTED' | 'OBSOLETE' | 'NEW' | 'UNAFFECTED'

export interface RuleChange {
  rule_key: string
  kind: 'ADDED' | 'REMOVED' | 'PARAM_CHANGED' | 'POLICY_VERSION_CHANGED'
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  changed_fields: string[]
}

export interface ImpactedTest {
  test_id: string
  tc_code: string
  impact_class: ImpactClass
  reason: string
  old_expected: ExpectedResult | null
  new_expected: ExpectedResult | null
  replacement_test_id: string | null
}

export interface ChangeImpact {
  id: string
  from_spec_id: string
  to_spec_id: string
  rule_changes: RuleChange[]
  impacted_criteria: string[]
  impacted_tests: ImpactedTest[]
  counts: Record<ImpactClass, number>
  rerun_test_ids: string[]
  created_at: string
  /** Advice, for example to design tests on the new specification before impact analysis. */
  warnings: string[]
}

export interface RunSummary {
  run_id: string
  sut_version: string
  finished_at: string | null
  totals: RunTotals
}

export interface MetricsOverview {
  requirements_total: number
  specs_approved: number
  ambiguities_total: number
  ambiguities_resolved: number
  requirement_completeness: number | null
  rules_total: number
  rules_with_passing_test: number
  rule_coverage: number | null
  tests_by_status: Record<TestStatus, number>
  validation_blocks_by_code: Record<string, number>
  last_run: RunSummary | null
  open_defects: number
  tests_impacted_pending: number
  ai_calls_total: number
  ai_fallbacks_total: number
  generated_at: string
}

export interface AuditEvent {
  id: string
  ts: string
  actor: string
  actor_role: Role | 'SYSTEM'
  action: string
  entity_type: string
  entity_id: string
  before_hash: string | null
  after_hash: string | null
  trace_id: string | null
  detail: Record<string, unknown> | null
}

export interface AuditPage {
  items: AuditEvent[]
  total: number
  limit: number
  offset: number
}
