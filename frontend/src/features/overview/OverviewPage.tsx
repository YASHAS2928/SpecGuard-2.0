import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { listAuditEvents } from '../../api/audit'
import { getMetrics } from '../../api/metrics'
import { loadRunHistory } from '../../api/runs'
import { SegmentedBar, Sparkline } from '../../components/domain/Charts'
import { EmptyState, ErrorState, Panel, Pill, ProvenanceBadge, Skeleton, SkeletonRows } from '../../components/ui'
import { useLoad } from '../../hooks'
import { formatDateTime, humanize } from '../../lib/format'
import { passRate, percent } from '../../lib/runs'

function Tile({
  label,
  value,
  sub,
  tone,
  to,
}: {
  label: string
  value: string
  sub?: string
  tone?: 'ok' | 'warn' | 'bad'
  to?: string
}) {
  const color = tone === 'ok' ? 'text-ok' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-bad' : 'text-fg'
  const body = (
    <div className="h-full rounded-lg border border-line bg-surface p-3 hover:bg-raised">
      <p className="text-[10px] font-medium uppercase tracking-wider text-fg-3">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-fg-3">{sub}</p>}
    </div>
  )
  return to ? <Link to={to}>{body}</Link> : body
}

const STATUS_BAR: Record<string, string> = {
  APPROVED: 'bg-ok',
  DRAFT: 'bg-info',
  BLOCKED: 'bg-bad',
  STALE: 'bg-warn',
  REJECTED: 'bg-fg-3',
  OBSOLETE: 'bg-line-strong',
}

export default function OverviewPage() {
  const metrics = useLoad(() => getMetrics(), 'metrics')
  const activity = useLoad(() => listAuditEvents({ limit: 8 }), 'activity')
  const runs = useLoad(() => loadRunHistory(8), 'recent-runs')

  if (metrics.error) return <ErrorState error={metrics.error} onRetry={metrics.reload} />
  if (!metrics.data) return <Skeleton className="h-64 w-full" />
  const m = metrics.data

  if (m.requirements_total === 0) {
    return (
      <Panel>
        <EmptyState
          title="Nothing to measure yet"
          description="Create a requirement to start. Every number on this page is computed from stored data."
          action={
            <Link to="/requirements?new=1" className="text-accent underline">
              New requirement
            </Link>
          }
        />
      </Panel>
    )
  }

  const last = m.last_run
  const lastRate = last ? passRate(last.totals) : null
  const trend = [...(runs.data ?? [])].reverse().map((run) => passRate(run.totals) ?? 0)
  const blocks = Object.entries(m.validation_blocks_by_code).sort((a, b) => b[1] - a[1])
  const statusSegments = Object.entries(m.tests_by_status).map(([name, value]) => ({
    label: humanize(name),
    value,
    className: STATUS_BAR[name] ?? 'bg-line-strong',
  }))
  const totalTests = statusSegments.reduce((sum, item) => sum + item.value, 0)

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-xl font-semibold">Engineering quality</h2>
        <span className="text-xs text-fg-3">Computed from stored data at {formatDateTime(m.generated_at)}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Requirements" value={String(m.requirements_total)} sub={`${m.specs_approved} approved spec(s)`} to="/requirements" />
        <Tile
          label="Ambiguities resolved"
          value={`${m.ambiguities_resolved}/${m.ambiguities_total}`}
          sub={`completeness ${percent(m.requirement_completeness)}`}
          tone={m.ambiguities_total > 0 && m.ambiguities_resolved === m.ambiguities_total ? 'ok' : 'warn'}
          to="/clarification"
        />
        <Tile
          label="Rule coverage"
          value={percent(m.rule_coverage)}
          sub={`${m.rules_with_passing_test}/${m.rules_total} rules with a passing test`}
          tone={m.rule_coverage === 1 ? 'ok' : 'warn'}
          to="/tests"
        />
        <Tile
          label="Last run pass rate"
          value={last ? percent(lastRate) : 'n/a'}
          sub={last ? `${last.totals.passed}/${last.totals.total} on mock ${last.sut_version}` : 'no run yet'}
          tone={!last ? undefined : lastRate === 1 ? 'ok' : 'bad'}
          to="/runs"
        />
        <Tile label="Tests" value={String(totalTests)} sub={`${m.tests_by_status.APPROVED ?? 0} approved`} to="/tests" />
        <Tile label="Open defects" value={String(m.open_defects)} tone={m.open_defects === 0 ? 'ok' : 'bad'} to="/runs" />
        <Tile
          label="Impacted tests pending"
          value={String(m.tests_impacted_pending)}
          sub="waiting for re-approval"
          tone={m.tests_impacted_pending === 0 ? 'ok' : 'warn'}
          to="/impact"
        />
        <Tile label="AI calls" value={String(m.ai_calls_total)} sub={`${m.ai_fallbacks_total} fallback(s)`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Tests by status">
          {totalTests === 0 ? (
            <p className="text-sm text-fg-3">No tests generated yet.</p>
          ) : (
            <SegmentedBar label="Tests by status" segments={statusSegments} />
          )}
        </Panel>

        <Panel title="Pass rate of recent runs">
          {runs.loading && !runs.data && <SkeletonRows rows={1} />}
          {runs.error && <ErrorState error={runs.error} onRetry={runs.reload} compact />}
          {runs.data && (
            <div className="flex flex-wrap items-center gap-4">
              <Sparkline points={trend} label="Pass rate of the latest runs, oldest to newest" />
              <p className="text-xs text-fg-3">
                {runs.data.length} run(s). Each point is one run: bottom is 0%, top is 100%.
              </p>
            </div>
          )}
        </Panel>

        <Panel title="Validation blocks">
          {blocks.length === 0 ? (
            <p className="text-sm text-fg-3">No test has been blocked by validation.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {blocks.map(([code, count]) => (
                <li key={code} className="flex items-center justify-between">
                  <span className="font-mono text-xs">{code}</span>
                  <Pill tone="bad">{count}</Pill>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Recent activity" actions={<Link to="/audit" className="text-xs text-accent underline">Audit history</Link>}>
          {activity.loading && !activity.data && <SkeletonRows rows={3} />}
          {activity.error && <ErrorState error={activity.error} onRetry={activity.reload} compact />}
          {activity.data && activity.data.items.length === 0 && <p className="text-sm text-fg-3">No activity yet.</p>}
          <ol className="space-y-2">
            {activity.data?.items.map((event) => (
              <li key={event.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <ProvenanceBadge source={event.actor_role === 'SYSTEM' ? 'oracle' : 'human'} label={humanize(event.action)} />
                <span>{event.actor}</span>
                <span className="text-xs text-fg-3">{formatDateTime(event.ts)}</span>
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      <Panel title="Quick actions">
        <div className="flex flex-wrap gap-2">
          {[
            ['/requirements?new=1', 'New requirement'],
            ['/clarification', 'Resolve questions'],
            ['/tests', 'Review tests'],
            ['/runs', 'Run tests'],
          ].map(([to, label]) => (
            <Link
              key={to}
              to={to ?? '/'}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-raised px-3 text-sm hover:bg-well"
            >
              {label}
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  )
}
