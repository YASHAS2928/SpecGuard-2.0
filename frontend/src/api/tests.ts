import { request } from './client'
import type { Actor } from './types'

export type TestStatus = 'DRAFT' | 'BLOCKED' | 'APPROVED' | 'REJECTED' | 'STALE' | 'OBSOLETE'
export type TestOrigin = 'ENGINE' | 'AI'
export type Technique = 'BOUNDARY' | 'PARTITION' | 'DECISION' | 'NEGATIVE' | 'EDGE'
export type Assertion = 'PAID_EQUALS' | 'OT_EQUALS' | 'REJECTS'

export interface Expected {
  paid_minutes: number | null
  overtime_minutes: number | null
  rejects: boolean
}

/** Lenient on purpose: negative tests deliberately carry malformed values. */
export interface FixtureInputs {
  start_time: string
  end_time: string
  overnight: boolean
  meal_break_minutes: number | null
}

export interface TestIssue {
  code: string
  severity: 'BLOCK' | 'WARN'
  entity_type: string | null
  entity_id: string | null
  message: string
  field_path: string | null
  detail: Record<string, unknown> | null
}

export interface TestRecord {
  id: string
  spec_id: string
  tc_code: string
  origin: TestOrigin
  technique: Technique
  inputs: FixtureInputs
  assertion: Assertion
  expected: Expected
  ai_claimed_expected: Expected | null
  rationale: string
  risk_score: number | null
  status: TestStatus
  rule_keys: string[]
  criterion_codes: string[]
  policy_refs: string[]
  issues: TestIssue[]
  supersedes_id: string | null
  created_at: string
}

export interface CriterionRecord {
  id: string
  spec_id: string
  crit_code: string
  rule_key: string
  given: string
  when: string
  then: string
}

export interface DesignResult {
  spec_id: string
  criteria: CriterionRecord[]
  tests: TestRecord[]
  counts_by_technique: Partial<Record<Technique, number>>
  blocked_count: number
  ai_edge_cases: 'generated' | 'unavailable' | 'disabled' | 'already_present'
  ai_message: string | null
  added: number
  already_present: number
}

export interface ReviewResult {
  decision: 'APPROVE' | 'REJECT'
  reviewed: { test_id: string; tc_code: string; previous_status: TestStatus; new_status: TestStatus }[]
  refused: { test_id: string; code: string; message: string }[]
}

export function designSpecTests(
  specId: string,
  includeAiEdgeCases: boolean,
  actor: Actor,
): Promise<DesignResult> {
  return request<DesignResult>('POST', `/specs/${specId}/design-tests`, {
    include_ai_edge_cases: includeAiEdgeCases,
    ...actor,
  })
}

export function listSpecTests(specId: string): Promise<TestRecord[]> {
  return request<TestRecord[]>('GET', `/specs/${specId}/tests`)
}

export function reviewSpecTests(
  testIds: string[],
  decision: 'APPROVE' | 'REJECT',
  reason: string | null,
  actor: Actor,
): Promise<ReviewResult> {
  return request<ReviewResult>('POST', '/tests/review', {
    test_ids: testIds,
    decision,
    reason,
    ...actor,
  })
}
