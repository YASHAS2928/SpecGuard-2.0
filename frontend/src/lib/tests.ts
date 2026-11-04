import type { Assertion, Expected, FixtureInputs, Technique, TestRecord } from '../api/tests'

export const TECHNIQUES: Technique[] = ['BOUNDARY', 'PARTITION', 'DECISION', 'NEGATIVE', 'EDGE']

export const ASSERTION_LABEL: Record<Assertion, string> = {
  PAID_EQUALS: 'Paid minutes equal',
  OT_EQUALS: 'Overtime minutes equal',
  REJECTS: 'Input is rejected',
}

export function expectedText(assertion: Assertion, expected: Expected): string {
  if (assertion === 'REJECTS') return 'Rejected (INVALID_INPUT)'
  if (assertion === 'PAID_EQUALS') return `${expected.paid_minutes ?? '?'} paid minutes`
  return `${expected.overtime_minutes ?? '?'} overtime minutes`
}

export function claimText(assertion: Assertion, claim: Expected): string {
  return expectedText(assertion, claim)
}

export function hasClaimMismatch(test: TestRecord): boolean {
  return test.issues.some((issue) => issue.code === 'V08_AI_CLAIM_MISMATCH')
}

export function isReviewable(test: TestRecord): boolean {
  return test.status === 'DRAFT' || test.status === 'STALE'
}

/** Engine tests may be approved in bulk. AI tests only one at a time. */
export function isBulkEligible(test: TestRecord): boolean {
  return test.origin === 'ENGINE' && isReviewable(test)
}

export function requestPreview(inputs: FixtureInputs): string {
  return JSON.stringify(
    {
      start_time: inputs.start_time,
      end_time: inputs.end_time,
      overnight: inputs.overnight,
      meal_break_minutes: inputs.meal_break_minutes,
    },
    null,
    2,
  )
}

const DEAD = new Set(['REJECTED', 'OBSOLETE'])

export interface MatrixCell {
  total: number
  approved: number
}

export function matrixCell(tests: TestRecord[], rule: string, technique: Technique): MatrixCell {
  const hits = tests.filter(
    (test) => test.technique === technique && test.rule_keys.includes(rule) && !DEAD.has(test.status),
  )
  return { total: hits.length, approved: hits.filter((test) => test.status === 'APPROVED').length }
}

export function countByStatus(tests: TestRecord[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const test of tests) counts[test.status] = (counts[test.status] ?? 0) + 1
  return counts
}
