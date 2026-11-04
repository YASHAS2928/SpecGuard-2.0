import { Bug } from 'lucide-react'
import type { DefectRecord } from '../../api/runs'
import { Button, EmptyState, Panel, Pill, ProvenanceBadge, StatusPill, Tooltip } from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { derivedPriority, partitionChips } from '../../lib/runs'

const PRIORITY_TONE = { High: 'bad', Medium: 'warn', Low: 'neutral' } as const

export function DefectList({
  defects,
  activeId,
  onShow,
}: {
  defects: DefectRecord[]
  activeId: string | null
  onShow: (defect: DefectRecord) => void
}) {
  return (
    <Panel
      title="Defect clusters"
      actions={
        <Tooltip text="Open until its tests all pass, then Fixed, then Verified on the next passing run. A new failure reopens it.">
          <span className="cursor-help text-xs text-fg-3">lifecycle ⓘ</span>
        </Tooltip>
      }
      bodyClassName="space-y-2 p-2"
    >
      {defects.length === 0 && (
        <EmptyState icon={Bug} title="No defects" description="Failing tests that share a cause are grouped here after a run." />
      )}
      {defects.map((defect) => {
        const priority = derivedPriority(defect)
        return (
          <article
            key={defect.id}
            className={`rounded-md border p-3 ${activeId === defect.id ? 'border-accent/60 bg-raised' : 'border-line'}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill value={defect.status} />
              <Tooltip text="The API has no severity field. Derived from the number of failing tests in the cluster.">
                <Pill tone={PRIORITY_TONE[priority]}>priority {priority} (derived)</Pill>
              </Tooltip>
              <span className="ml-auto font-mono text-xs text-fg-3">{defect.rule_key ?? 'unlinked'}</span>
            </div>
            <h3 className="mt-2 text-sm font-medium">{defect.title}</h3>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {partitionChips(defect.partition).map((chip) => (
                <span key={chip} className="rounded border border-line-strong bg-well px-1.5 py-0.5 font-mono text-[11px]">
                  {chip}
                </span>
              ))}
              {Object.keys(defect.partition).length === 0 && (
                <span className="text-xs text-fg-3">no shared input pattern found</span>
              )}
            </div>
            <p className="mt-2 text-xs text-fg-2">
              {defect.evidence_result_ids.length} failing result(s) · first seen {formatDateTime(defect.created_at)}
            </p>
            {defect.hypothesis && (
              <div className="mt-2 rounded-md border border-prov-ai/40 bg-prov-ai/10 p-2 text-xs">
                <ProvenanceBadge source="ai" label="AI hypothesis" />
                <p className="mt-1 text-fg-2">{defect.hypothesis.text}</p>
                <p className="mt-1 text-fg-3">A hypothesis, not a diagnosis.</p>
              </div>
            )}
            <div className="mt-2">
              <Button size="sm" onClick={() => onShow(defect)}>
                {activeId === defect.id ? 'Showing its tests' : 'Show failing tests'}
              </Button>
            </div>
          </article>
        )
      })}
    </Panel>
  )
}
