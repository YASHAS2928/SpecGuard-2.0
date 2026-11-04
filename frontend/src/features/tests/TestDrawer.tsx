import { Check, X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { CriterionRecord, TestRecord } from '../../api/tests'
import { Button, Drawer, Pill, ProvenanceBadge, StatusPill } from '../../components/ui'
import { ASSERTION_LABEL, claimText, expectedText, hasClaimMismatch, isReviewable, requestPreview } from '../../lib/tests'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-3">{title}</h3>
      {children}
    </section>
  )
}

export function TestDrawer({
  test,
  criteria,
  canReview,
  onClose,
  onApprove,
  onReject,
  onLoadCriteria,
}: {
  test: TestRecord | null
  criteria: Record<string, CriterionRecord>
  canReview: boolean
  onClose: () => void
  onApprove: (test: TestRecord) => void
  onReject: (test: TestRecord) => void
  onLoadCriteria: () => void
}) {
  if (!test) return null
  const reviewable = isReviewable(test)
  const blocked = test.status === 'BLOCKED'
  const linked = test.criterion_codes.map((code) => criteria[code]).filter((item): item is CriterionRecord => item !== undefined)
  const missingText = test.criterion_codes.length > 0 && linked.length < test.criterion_codes.length

  return (
    <Drawer
      open
      onClose={onClose}
      title={test.tc_code}
      description={test.rationale}
      footer={
        reviewable || blocked ? (
          <>
            <Button variant="danger" disabled={!canReview || blocked} onClick={() => onReject(test)}>
              <X size={13} aria-hidden="true" />
              Reject…
            </Button>
            <Button
              variant="primary"
              disabled={!canReview || blocked}
              title={blocked ? 'Blocked tests cannot be approved' : canReview ? undefined : 'Your role cannot review tests'}
              onClick={() => onApprove(test)}
            >
              <Check size={13} aria-hidden="true" />
              Approve
            </Button>
          </>
        ) : undefined
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill value={test.status} />
        <Pill>{test.technique}</Pill>
        {test.origin === 'AI' ? <ProvenanceBadge source="ai" label="AI-suggested" /> : <Pill>Engine-designed</Pill>}
        {test.risk_score !== null && <Pill tone="info">risk {test.risk_score}</Pill>}
      </div>

      <Section title="Precondition">
        {linked.length > 0 ? (
          <ul className="space-y-2">
            {linked.map((item) => (
              <li key={item.id} className="rounded-md border border-line p-2 text-sm">
                <span className="font-mono text-xs text-fg-3">{item.crit_code} · {item.rule_key}</span>
                <p><span className="text-fg-3">Given</span> {item.given}</p>
                <p><span className="text-fg-3">When</span> {item.when}</p>
                <p><span className="text-fg-3">Then</span> {item.then}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-fg-2">
            Criteria: <span className="font-mono">{test.criterion_codes.join(', ') || 'none linked'}</span>
          </p>
        )}
        {missingText && (
          <Button size="sm" variant="ghost" className="mt-1" onClick={onLoadCriteria}>
            Load criterion text
          </Button>
        )}
      </Section>

      <Section title="Step: request sent to the mock API">
        <pre className="overflow-x-auto rounded-md border border-line bg-well p-3 font-mono text-xs">
          {`POST /v1/pay/calculate\n${requestPreview(test.inputs)}`}
        </pre>
      </Section>

      <Section title="Expected result">
        <div className="rounded-md border border-prov-oracle/40 bg-prov-oracle/10 p-3">
          <div className="flex items-center justify-between gap-2">
            <ProvenanceBadge source="oracle" label="Oracle · expected" />
            <span className="text-xs text-fg-3">{ASSERTION_LABEL[test.assertion]}</span>
          </div>
          <p className="mt-2 font-mono text-lg">{expectedText(test.assertion, test.expected)}</p>
          <p className="mt-1 text-xs text-fg-2">
            Computed by the deterministic oracle from the approved specification. The AI cannot set it and there is no way to edit it here.
          </p>
        </div>
        {test.ai_claimed_expected && (
          <div className="mt-2 rounded-md border border-prov-ai/40 bg-prov-ai/10 p-3">
            <ProvenanceBadge source="ai" label="AI · claimed" />
            <p className="mt-2 font-mono text-sm">{claimText(test.assertion, test.ai_claimed_expected)}</p>
            <p className="mt-1 text-xs text-fg-2">
              {hasClaimMismatch(test)
                ? 'The claim differs from the oracle. The oracle value above is the one used.'
                : 'The claim matches the oracle.'}
            </p>
          </div>
        )}
      </Section>

      <Section title={`Validation issues (${test.issues.length})`}>
        {test.issues.length === 0 ? (
          <p className="text-sm text-ok">No issues.</p>
        ) : (
          <ul className="space-y-1.5">
            {test.issues.map((issue, position) => (
              <li key={`${issue.code}-${position}`} className="rounded-md border border-line p-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={issue.severity === 'BLOCK' ? 'bad' : 'warn'}>{issue.severity}</Pill>
                  <span className="font-mono text-xs">{issue.code}</span>
                </div>
                <p className="mt-1 text-fg-2">{issue.message}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Traceability">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-fg-3">Rules</dt>
          <dd className="font-mono text-xs">{test.rule_keys.join(', ') || '—'}</dd>
          <dt className="text-fg-3">Criteria</dt>
          <dd className="font-mono text-xs">{test.criterion_codes.join(', ') || '—'}</dd>
          <dt className="text-fg-3">Policies</dt>
          <dd className="font-mono text-xs">{test.policy_refs.join(', ') || '—'}</dd>
        </dl>
      </Section>
    </Drawer>
  )
}
