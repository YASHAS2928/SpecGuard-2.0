import { listAuditEvents } from './audit'
import { request } from './client'
import type { Defect, Run, TestResult, RunTotals } from './types'
import type { Actor } from './types'

export type RunResult = TestResult
export type RunRecord = Run
export type DefectRecord = Defect
export type { RunTotals }

export function createRun(specId: string, testIds: string[] | null, actor: Actor): Promise<RunRecord> {
  return request<RunRecord>('POST', '/runs', {
    spec_id: specId,
    test_ids: testIds,
    trigger: 'MANUAL',
    ...actor,
  })
}

export const getRun = (runId: string): Promise<RunRecord> => request<RunRecord>('GET', `/runs/${runId}`)

export function listDefects(filters: { spec_id?: string; status?: string } = {}): Promise<DefectRecord[]> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value)
  }
  const suffix = params.toString()
  return request<DefectRecord[]>('GET', `/defects${suffix ? `?${suffix}` : ''}`)
}

/** Rebuild history from RUN_EXECUTED audit events because no run-list endpoint exists. */
export async function loadRunHistory(limit: number, specId?: string): Promise<RunRecord[]> {
  const events = await listAuditEvents({ action: 'RUN_EXECUTED', limit: 50 })
  const ids = Array.from(new Set(events.items.map((event) => event.entity_id)))
  const runs = await Promise.all(ids.map((id) => getRun(id)))
  return runs
    .filter((run) => !specId || run.spec_id === specId)
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .slice(0, limit)
}
