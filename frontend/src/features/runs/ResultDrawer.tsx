import { Link } from 'react-router-dom'
import type { DefectRecord, RunResult } from '../../api/runs'
import type { TestRecord } from '../../api/tests'
import { Drawer, Pill, ProvenanceBadge, StatusPill } from '../../components/ui'
import { derivedPriority, observedText, partitionChips } from '../../lib/runs'
import { ASSERTION_LABEL, expectedText, requestPreview } from '../../lib/tests'

export function ResultDrawer({
  result,
  test,
  defects,
  runVersion,
  onClose,
}: {
  result: RunResult | null
  test: TestRecord | undefined
  defects: DefectRecord[]
  runVersion: string
  onClose: () => void
}) {
  if (!result) return null
  const linked = defects.filter((defect) => defect.evidence_result_ids.includes(result.id))
  return (
    <Drawer open onClose={onClose} title={result.tc_code} description={test?.rationale}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill value={result.status} />
        <Pill tone="info">mock {runVersion}</Pill>
        {test && <Pill>{test.technique}</Pill>}
        {result.latency_ms !== null && <Pill>{result.latency_ms} ms</Pill>}
      </div>

      {result.failed_assertion && (
        <div role="alert" className="rounded-md border border-bad/40 bg-bad/10 p-3 text-sm">
          <p className="text-[10px] font-medium uppercase tracking-wider text-fg-3">Failed assertion</p>
          <p className="mt-1 font-mono text-xs">{result.failed_assertion}</p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-prov-oracle/40 bg-prov-oracle/10 p-3">
          <ProvenanceBadge source="oracle" label="Oracle · expected" />
          <p className="mt-2 font-mono text-sm">{test ? expectedText(test.assertion, result.expected) : '—'}</p>
          {test && <p className="mt-1 text-xs text-fg-3">{ASSERTION_LABEL[test.assertion]}</p>}
        </div>
        <div className={`rounded-md border p-3 ${result.status === 'PASS' ? 'border-ok/40 bg-ok/10' : 'border-bad/40 bg-bad/10'}`}>
          <p className="text-xs font-medium">Observed from the system under test</p>
          <p className="mt-2 font-mono text-sm">{observedText(test?.assertion, result)}</p>
        </div>
      </div>

      {test && (
        <section>
          <h3 className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-3">Request sent</h3>
          <pre className="overflow-x-auto rounded-md border border-line bg-well p-3 font-mono text-xs">
            {`POST /v1/pay/calculate\n${requestPreview(test.inputs)}`}
          </pre>
        </section>
      )}

      <section>
        <h3 className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-3">Where to look</h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-fg-3">Rules</dt>
          <dd className="font-mono text-xs">{test?.rule_keys.join(', ') || '—'}</dd>
          <dt className="text-fg-3">Criteria</dt>
          <dd className="font-mono text-xs">{test?.criterion_codes.join(', ') || '—'}</dd>
          <dt className="text-fg-3">Policies</dt>
          <dd className="font-mono text-xs">{test?.policy_refs.join(', ') || '—'}</dd>
        </dl>
        {test && (
          <Link to={`/tests/${test.spec_id}`} className="mt-2 inline-block text-sm text-accent underline">
            Open in Test review
          </Link>
        )}
      </section>

      {linked.length > 0 && (
        <section>
          <h3 className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-3">Part of a defect cluster</h3>
          {linked.map((defect) => (
            <div key={defect.id} className="rounded-md border border-line p-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill value={defect.status} />
                <Pill tone="warn">priority {derivedPriority(defect)} (derived)</Pill>
              </div>
              <p className="mt-1 font-medium">{defect.title}</p>
              <p className="mt-0.5 font-mono text-xs text-fg-3">{partitionChips(defect.partition).join(' · ')}</p>
            </div>
          ))}
        </section>
      )}
    </Drawer>
  )
}
