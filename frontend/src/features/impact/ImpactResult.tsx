import { Link } from 'react-router-dom'
import type { ImpactClass, ImpactReport, RuleChange } from '../../api/impact'
import { Notice, Panel, Pill, StatusPill } from '../../components/ui'
import { expectedBrief } from '../../lib/diff'

const CLASSES: { id: ImpactClass; label: string; hint: string }[] = [
  { id: 'STALE_EXPECTED', label: 'Stale', hint: 'Expected value changed. Needs re-approval.' },
  { id: 'OBSOLETE', label: 'Obsolete', hint: 'No longer valid. Replaced or retired.' },
  { id: 'NEW', label: 'New', hint: 'Created for the changed rules. Needs approval.' },
  { id: 'UNAFFECTED', label: 'Unaffected', hint: 'Not touched by the change.' },
]

function show(value: unknown): string {
  return value === null || value === undefined ? '—' : String(value)
}

function RuleChangeRow({ change }: { change: RuleChange }) {
  const fields = change.changed_fields.length > 0 ? change.changed_fields : Object.keys({ ...change.before, ...change.after })
  return (
    <tr className="border-b border-line align-top last:border-0">
      <td className="px-3 py-2 font-mono text-xs font-medium">{change.rule_key}</td>
      <td className="px-3 py-2">
        <StatusPill value={change.kind} />
      </td>
      <td className="px-3 py-2 font-mono text-xs">
        {fields.map((field) => (
          <p key={field}>
            <span className="text-fg-3">{field}</span>{' '}
            <span className="text-bad">{show(change.before?.[field])}</span> →{' '}
            <span className="text-ok">{show(change.after?.[field])}</span>
          </p>
        ))}
      </td>
    </tr>
  )
}

export function RuleChanges({ report }: { report: ImpactReport }) {
  if (report.rule_changes.length === 0) {
    return <p className="px-3 py-6 text-center text-sm text-fg-3">No rule changed between these specifications.</p>
  }
  return (
    <div className="min-w-0 max-w-full overflow-x-auto">
      <table className="w-full min-w-[32rem] text-sm">
        <thead className="border-b border-line text-left text-[10px] uppercase tracking-wider text-fg-3">
          <tr>
            <th className="px-3 py-2 font-medium">Rule</th>
            <th className="px-3 py-2 font-medium">Change</th>
            <th className="px-3 py-2 font-medium">Before → after</th>
          </tr>
        </thead>
        <tbody>
          {report.rule_changes.map((change) => (
            <RuleChangeRow key={`${change.rule_key}-${change.kind}`} change={change} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ImpactTests({
  report,
  filter,
  onFilter,
  toSpecId,
}: {
  report: ImpactReport
  filter: ImpactClass | ''
  onFilter: (value: ImpactClass | '') => void
  toSpecId: string
}) {
  const shown = filter ? report.impacted_tests.filter((test) => test.impact_class === filter) : report.impacted_tests
  const codeById = new Map(report.impacted_tests.map((test) => [test.test_id, test.tc_code]))
  return (
    <div>
      <div className="flex flex-wrap gap-2 border-b border-line p-3">
        {CLASSES.map((item) => (
          <button
            key={item.id}
            type="button"
            title={item.hint}
            aria-pressed={filter === item.id}
            onClick={() => onFilter(filter === item.id ? '' : item.id)}
            className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${
              filter === item.id ? 'border-accent bg-accent/10' : 'border-line bg-surface hover:bg-raised'
            }`}
          >
            <StatusPill value={item.id} />
            <span className="tabular-nums">{report.counts[item.id] ?? 0}</span>
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="px-3 py-6 text-center text-sm text-fg-3">No tests in this group.</p>
      ) : (
        <div className="min-w-0 max-w-full overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="border-b border-line text-left text-[10px] uppercase tracking-wider text-fg-3">
              <tr>
                <th className="px-3 py-2 font-medium">Test</th>
                <th className="px-3 py-2 font-medium">Impact</th>
                <th className="px-3 py-2 font-medium">Expected before → after</th>
                <th className="px-3 py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((test) => (
                <tr key={test.test_id} className="border-b border-line align-top last:border-0">
                  <td className="px-3 py-2 font-mono text-xs font-medium">{test.tc_code}</td>
                  <td className="px-3 py-2">
                    <StatusPill value={test.impact_class} />
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    <span className="text-fg-2">{expectedBrief(test.old_expected)}</span>
                    {test.new_expected && (
                      <>
                        {' → '}
                        <span className="text-prov-oracle">{expectedBrief(test.new_expected)}</span>
                      </>
                    )}
                  </td>
                  <td className="px-3 py-2 text-fg-2">
                    {test.reason}
                    {test.replacement_test_id && (
                      <span className="block text-xs text-fg-3">
                        replaced by {codeById.get(test.replacement_test_id) ?? test.replacement_test_id}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="border-t border-line px-3 py-2 text-xs text-fg-3">
        Stale and new tests start unapproved. Approve them in{' '}
        <Link to={`/tests/${toSpecId}`} className="text-accent underline">
          Test review
        </Link>{' '}
        before they can run.
      </p>
    </div>
  )
}

export function ImpactWarnings({ warnings }: { warnings: string[] | undefined }) {
  if (!warnings || warnings.length === 0) return null
  return (
    <Notice tone="warn" title="Check before trusting this report">
      <ul className="list-disc pl-4">
        {warnings.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Notice>
  )
}

export function ImpactSummary({ report }: { report: ImpactReport }) {
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">{report.rule_changes.length} rule change(s)</span>
        <span className="text-fg-3">·</span>
        <span>{report.impacted_criteria.length} criteria affected</span>
        <span className="text-fg-3">·</span>
        <span>{report.rerun_test_ids.length} test(s) recommended for rerun</span>
        {report.impacted_criteria.length > 0 && (
          <span className="font-mono text-xs text-fg-3">{report.impacted_criteria.join(', ')}</span>
        )}
        <Pill tone="info">report saved</Pill>
      </div>
    </Panel>
  )
}
