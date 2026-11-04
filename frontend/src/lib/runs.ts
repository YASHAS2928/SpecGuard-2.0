import type { DefectRecord, RunRecord, RunResult, RunTotals } from '../api/runs'
import type { Assertion } from '../api/tests'

export function passRate(totals: RunTotals): number | null {
  return totals.total > 0 ? totals.passed / totals.total : null
}

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? 'n/a' : `${Math.round(value * 100)}%`
}

/** The API has no severity field, so priority is derived from how many tests fail together. */
export function derivedPriority(defect: DefectRecord): 'High' | 'Medium' | 'Low' {
  const count = defect.evidence_result_ids.length
  return count >= 3 ? 'High' : count === 2 ? 'Medium' : 'Low'
}

export function observedText(assertion: Assertion | undefined, result: RunResult): string {
  const observed = result.observed
  if (!observed) return result.status === 'ERROR' ? 'no response' : '—'
  if (typeof observed.error === 'string') return `error (${observed.error})`
  if (assertion === 'REJECTS') {
    if (result.status === 'PASS' && typeof observed.status_code === 'number') {
      return `rejected (HTTP ${observed.status_code})`
    }
    return 'accepted (no rejection)'
  }
  if (assertion === 'PAID_EQUALS') return `${String(observed.paid_minutes ?? '—')} paid minutes`
  if (assertion === 'OT_EQUALS') return `${String(observed.overtime_minutes ?? '—')} overtime minutes`
  return `paid ${String(observed.paid_minutes ?? '—')}, overtime ${String(observed.overtime_minutes ?? '—')}`
}

export function runLabel(run: RunRecord): string {
  return `${run.sut_version} · ${run.totals.passed}/${run.totals.total} passed`
}

export function partitionChips(partition: Record<string, unknown>): string[] {
  return Object.entries(partition).map(([key, value]) => `${key} = ${String(value)}`)
}
