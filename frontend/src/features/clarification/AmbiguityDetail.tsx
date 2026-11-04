import { Check } from 'lucide-react'
import { useState } from 'react'
import { api, toApiError } from '../../api/client'
import type { ApiError } from '../../api/client'
import { listAuditEvents } from '../../api/audit'
import type { Ambiguity, Spec } from '../../api/types'
import { useSession } from '../../app/session'
import { canEditSpec, describeChange, ParamList } from '../../components/domain/SpecParts'
import {
  Button,
  Dialog,
  ErrorState,
  Field,
  Panel,
  ProvenanceBadge,
  SkeletonRows,
  StatusPill,
  Tooltip,
  inputClass,
  useToast,
} from '../../components/ui'
import { useLoad } from '../../hooks'
import { formatDateTime, humanize } from '../../lib/format'

export function AmbiguityDetail({
  spec,
  ambiguity,
  onSpecChanged,
}: {
  spec: Spec
  ambiguity: Ambiguity
  onSpecChanged: (spec: Spec) => void
}) {
  const { actor } = useSession()
  const toast = useToast()
  const [confirmIndex, setConfirmIndex] = useState<number | null>(null)
  const [deferOpen, setDeferOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const history = useLoad(
    () => listAuditEvents({ entity_id: ambiguity.id, limit: 20 }),
    `audit:${ambiguity.id}:${ambiguity.status}`,
  )

  const decidable = ambiguity.status !== 'RESOLVED' && spec.status === 'DRAFT'
  const allowed = canEditSpec(actor.actor_role)
  const rules = spec.rules.filter((rule) => ambiguity.affects_rules.includes(rule.rule_key))

  function closeDialogs() {
    setConfirmIndex(null)
    setDeferOpen(false)
    setComment('')
    setError(null)
  }

  async function submit(choice: { option_index: number } | { defer: true; comment?: string }) {
    setBusy(true)
    setError(null)
    try {
      const updated = await api.resolveAmbiguity(ambiguity.id, choice, actor)
      onSpecChanged(updated)
      toast.push({
        tone: 'ok',
        title: 'option_index' in choice ? `${ambiguity.amb_code} resolved` : `${ambiguity.amb_code} deferred`,
        description: `by ${actor.actor}`,
      })
      closeDialogs()
      history.reload()
    } catch (caught) {
      setError(toApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  const pending = confirmIndex === null ? null : ambiguity.options[confirmIndex]

  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-medium">{ambiguity.amb_code}</span>
          <StatusPill value={ambiguity.status} />
          <ProvenanceBadge source="ai" label="AI-suggested question" />
        </div>
        <h2 className="mt-2 text-lg font-semibold">{ambiguity.question}</h2>
        <p className="mt-1 text-sm text-fg-2">{ambiguity.why}</p>
      </Panel>

      <Panel title="Source evidence">
        <div className="space-y-3">
          {rules.map((rule) => (
            <div key={rule.id} className="rounded-md border border-line p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-medium">{rule.rule_key}</span>
                {rule.policy_ref && <span className="font-mono text-xs text-fg-3">{rule.policy_ref}</span>}
              </div>
              <blockquote className="my-2 border-l-2 border-prov-ai/60 pl-2 text-sm italic text-fg-2">
                “{rule.source_span}”
              </blockquote>
              <ParamList params={rule.params} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Possible interpretations"
        actions={
          decidable && (
            <Tooltip text={allowed ? 'Postpone this decision' : `Role ${humanize(actor.actor_role)} cannot decide`}>
              <Button size="sm" disabled={!allowed || ambiguity.status === 'DEFERRED'} onClick={() => setDeferOpen(true)}>
                {ambiguity.status === 'DEFERRED' ? 'Deferred' : 'Defer'}
              </Button>
            </Tooltip>
          )
        }
      >
        <div className="grid gap-3 md:grid-cols-2">
          {ambiguity.options.map((option, index) => {
            const chosen = ambiguity.chosen_option_index === index
            return (
              <div
                key={option.label}
                className={`flex flex-col rounded-md border p-3 ${
                  chosen ? 'border-prov-human/60 bg-prov-human/10' : 'border-line'
                }`}
              >
                <p className="text-sm font-medium">
                  <span className="mr-1.5 font-mono text-fg-3">{String.fromCharCode(65 + index)}</span>
                  {option.label}
                </p>
                <ul className="mt-2 flex-1 space-y-1 font-mono text-xs">
                  {option.patch.map((op) => {
                    const change = describeChange(spec, op)
                    return (
                      <li key={op.path} className="flex flex-wrap gap-x-1.5">
                        <span className="text-fg-3">{change.target}</span>
                        <span className="text-bad line-through decoration-1">{change.before}</span>
                        <span aria-hidden="true">→</span>
                        <span className="text-ok">{change.after}</span>
                      </li>
                    )
                  })}
                </ul>
                {chosen && (
                  <p className="mt-2 flex items-center gap-1.5 text-xs">
                    <ProvenanceBadge source="human" label="Chosen" />
                    {ambiguity.resolved_by} · {formatDateTime(ambiguity.resolved_at)}
                  </p>
                )}
                {decidable && !chosen && (
                  <div className="mt-3">
                    <Tooltip text={allowed ? 'Apply this interpretation' : `Role ${humanize(actor.actor_role)} cannot decide`}>
                      <Button size="sm" variant="primary" disabled={!allowed} onClick={() => setConfirmIndex(index)}>
                        <Check size={12} aria-hidden="true" />
                        Choose
                      </Button>
                    </Tooltip>
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <p className="mt-3 text-xs text-fg-3">
          The AI suggests interpretations. A person decides, and only the listed parameter changes are applied.
        </p>
      </Panel>

      <Panel title="Decision history">
        {history.loading && !history.data && <SkeletonRows rows={2} />}
        {history.error && <ErrorState error={history.error} onRetry={history.reload} compact />}
        {history.data && history.data.items.length === 0 && (
          <p className="text-sm text-fg-3">No decisions recorded yet.</p>
        )}
        <ol className="space-y-2">
          {history.data?.items.map((event) => (
            <li key={event.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
              <ProvenanceBadge source="human" label={humanize(event.action)} />
              <span>
                {event.actor} <span className="text-fg-3">({humanize(event.actor_role)})</span>
              </span>
              <span className="text-xs text-fg-3">{formatDateTime(event.ts)}</span>
              {typeof event.detail?.option_label === 'string' && (
                <span className="basis-full text-xs text-fg-2">“{event.detail.option_label}”</span>
              )}
              {event.trace_id && <span className="font-mono text-[11px] text-fg-3">trace {event.trace_id}</span>}
            </li>
          ))}
        </ol>
      </Panel>

      <Dialog
        open={pending !== null}
        onClose={closeDialogs}
        title={`Apply interpretation for ${ambiguity.amb_code}?`}
        description="This changes the specification. You can still defer or approve afterwards."
        footer={
          <>
            <Button onClick={closeDialogs}>Cancel</Button>
            <Button
              variant="primary"
              disabled={busy || confirmIndex === null}
              onClick={() => confirmIndex !== null && submit({ option_index: confirmIndex })}
            >
              {busy ? 'Applying…' : 'Apply'}
            </Button>
          </>
        }
      >
        {pending && (
          <>
            <p className="text-sm font-medium">{pending.label}</p>
            <ul className="space-y-1 font-mono text-xs">
              {pending.patch.map((op) => {
                const change = describeChange(spec, op)
                return (
                  <li key={op.path}>
                    {change.target}: <span className="text-bad">{change.before}</span> →{' '}
                    <span className="text-ok">{change.after}</span>
                  </li>
                )
              })}
            </ul>
          </>
        )}
        {error && <ErrorState error={error} compact />}
      </Dialog>

      <Dialog
        open={deferOpen}
        onClose={closeDialogs}
        title={`Defer ${ambiguity.amb_code}`}
        description="A deferred question still blocks approval until it is resolved."
        footer={
          <>
            <Button onClick={closeDialogs}>Cancel</Button>
            <Button
              variant="primary"
              disabled={busy}
              onClick={() => submit({ defer: true, comment: comment.trim() || undefined })}
            >
              {busy ? 'Saving…' : 'Defer'}
            </Button>
          </>
        }
      >
        <Field label="Reason (optional)">
          <input data-autofocus className={inputClass} value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
        {error && <ErrorState error={error} compact />}
      </Dialog>
    </div>
  )
}
