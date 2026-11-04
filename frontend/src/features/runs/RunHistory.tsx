import type { RunRecord } from '../../api/runs'
import { Panel, Pill, SkeletonRows } from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { percent, passRate } from '../../lib/runs'

export function RunHistory({
  runs,
  loading,
  activeId,
  onSelect,
}: {
  runs: RunRecord[] | null
  loading: boolean
  activeId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <Panel title="Run history" bodyClassName="p-2">
      {loading && !runs && <SkeletonRows rows={3} />}
      {runs && runs.length === 0 && <p className="px-2 py-4 text-center text-sm text-fg-3">No runs yet.</p>}
      <ul className="space-y-1">
        {runs?.map((run) => (
          <li key={run.id}>
            <button
              type="button"
              onClick={() => onSelect(run.id)}
              aria-current={run.id === activeId}
              className={`w-full rounded-md border px-2.5 py-2 text-left hover:bg-raised ${
                run.id === activeId ? 'border-accent/60 bg-raised' : 'border-transparent'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs font-medium">mock {run.sut_version}</span>
                <Pill tone={run.totals.failed + run.totals.errors === 0 ? 'ok' : 'bad'}>
                  {percent(passRate(run.totals))}
                </Pill>
              </div>
              <p className="text-xs text-fg-3">
                {run.totals.passed} passed · {run.totals.failed} failed · {run.totals.errors} errors ·{' '}
                {formatDateTime(run.started_at)}
              </p>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
