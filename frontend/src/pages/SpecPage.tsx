import { useState } from 'react'
import { api, toApiError } from '../api/client'
import type { ApiError } from '../api/client'
import type { Actor, AnalysisMetadata, Ambiguity, PatchOp, Spec } from '../api/types'
import { Badge, Button, Card, ErrorBox, Loading, inputClass } from '../components/ui'
import { useLoad } from '../hooks'

const BLOCKER_LABELS: Record<string, string> = {
  open_ambiguities: 'Open questions',
  deferred_ambiguities: 'Deferred questions (must be resolved)',
  unresolved_params: 'Unresolved parameters',
  blocking_issues: 'Blocking validation issues',
  ungrounded_rules: 'Rules whose source text has not been verified',
}

function describePatch(op: PatchOp): string | null {
  const parts = op.path.split('/') // ['', 'rules', KEY, 'params', name] or [..., 'origin']
  if (parts[3] === 'origin') return null
  return `${parts[2]}.${parts[4]} → ${op.value === null ? 'null' : String(op.value)}`
}

function Blockers({ details }: { details: unknown }) {
  if (typeof details !== 'object' || details === null) return null
  const entries = Object.entries(details as Record<string, unknown>).filter(
    ([, value]) => Array.isArray(value) && value.length > 0,
  )
  return (
    <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">
      <p className="font-medium">This specification cannot be approved yet:</p>
      <ul className="mt-2 space-y-1">
        {entries.map(([key, value]) => (
          <li key={key}>
            <span className="font-medium">{BLOCKER_LABELS[key] ?? key}:</span>{' '}
            {(value as string[]).join(', ')}
          </li>
        ))}
      </ul>
      {entries.some(([key]) => key === 'ungrounded_rules') && (
        <p className="mt-2 text-xs text-red-700">
          The grounding check runs in the Quality Engine. If it is not integrated yet, no
          specification can be approved.
        </p>
      )}
    </div>
  )
}

function GroundedMark({ value }: { value: boolean | null }) {
  if (value === true) return <span className="text-green-700">✓ verified</span>
  if (value === false) return <span className="text-red-700">✕ not found in sources</span>
  return <span className="text-slate-500">? not checked</span>
}

function AmbiguityCard({
  ambiguity,
  editable,
  busy,
  onChoose,
  onDefer,
}: {
  ambiguity: Ambiguity
  editable: boolean
  busy: boolean
  onChoose: (index: number) => void
  onDefer: () => void
}) {
  const open = ambiguity.status !== 'RESOLVED'
  return (
    <div className="rounded border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{ambiguity.amb_code}</span>
        <Badge value={ambiguity.status} />
        <span className="text-xs text-slate-500">affects {ambiguity.affects_rules.join(', ')}</span>
      </div>
      <p className="mt-2 text-sm font-medium">{ambiguity.question}</p>
      <p className="text-sm text-slate-600">{ambiguity.why}</p>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {ambiguity.options.map((option, index) => {
          const chosen = ambiguity.chosen_option_index === index
          return (
            <div
              key={option.label}
              className={`rounded border p-2 text-sm ${chosen ? 'border-green-500 bg-green-50' : 'border-slate-200'}`}
            >
              <p className="font-medium">{option.label}</p>
              <ul className="mt-1 text-xs text-slate-600">
                {option.patch.map((op) => describePatch(op)).filter(Boolean).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              {open && editable && (
                <div className="mt-2">
                  <Button onClick={() => onChoose(index)} disabled={busy}>
                    Choose this
                  </Button>
                </div>
              )}
              {chosen && <p className="mt-2 text-xs text-green-700">Chosen by {ambiguity.resolved_by}</p>}
            </div>
          )
        })}
      </div>
      {ambiguity.status === 'OPEN' && editable && (
        <div className="mt-2">
          <Button variant="secondary" onClick={onDefer} disabled={busy}>
            Defer (blocks approval until resolved)
          </Button>
        </div>
      )}
    </div>
  )
}

export default function SpecPage({
  specId,
  analysis,
  actor,
}: {
  specId: string | null
  analysis: AnalysisMetadata | null
  actor: Actor
}) {
  const spec = useLoad<Spec | null>(
    () => (specId ? api.getSpec(specId) : Promise.resolve(null)),
    specId ?? 'none',
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [comment, setComment] = useState('')

  if (!specId) {
    return (
      <Card>
        <p className="text-sm text-slate-600">
          No specification selected. Open the Requirements tab, analyse a version or open an existing
          specification.
        </p>
      </Card>
    )
  }
  if (spec.loading && !spec.data) return <Loading />
  if (spec.error) return <ErrorBox error={spec.error} />
  const data = spec.data
  if (!data) return null

  const draft = data.status === 'DRAFT'

  async function run(action: () => Promise<Spec>) {
    setBusy(true)
    setError(null)
    try {
      spec.setData(await action())
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {analysis && (
        <div
          className={`rounded border p-3 text-sm ${
            analysis.mode === 'fake'
              ? 'border-amber-300 bg-amber-50 text-amber-900'
              : 'border-blue-200 bg-blue-50 text-blue-900'
          }`}
        >
          <p className="font-medium">
            {analysis.mode === 'fake'
              ? 'Generated by the offline fake provider (no language model was used).'
              : `Generated by ${analysis.provider}${analysis.model ? ` (${analysis.model})` : ''}.`}
          </p>
          <p className="text-xs">
            Prompt {analysis.prompt_version} · {analysis.retries} retr
            {analysis.retries === 1 ? 'y' : 'ies'} · first-try valid:{' '}
            {analysis.valid_first_try ? 'yes' : 'no'}
            {analysis.latency_ms !== null ? ` · ${analysis.latency_ms} ms` : ''}
          </p>
          {analysis.message && <p className="mt-1 text-xs">{analysis.message}</p>}
        </div>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-base font-semibold">Specification v{data.version}</h2>
          <Badge value={data.status} />
          <span className="text-sm text-slate-600">
            {data.open_ambiguities} open question(s) · {data.blocking_issue_count} blocking issue(s)
          </span>
          {data.approved_by && (
            <span className="text-sm text-green-700">
              Approved by {data.approved_by} ({new Date(data.approved_at ?? '').toLocaleString()})
            </span>
          )}
        </div>
      </Card>

      <Card title="Extracted rules">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-3">Rule</th>
                <th className="py-1 pr-3">Parameters</th>
                <th className="py-1 pr-3">Origin</th>
                <th className="py-1 pr-3">Source text</th>
                <th className="py-1">Grounding</th>
              </tr>
            </thead>
            <tbody>
              {data.rules.map((rule) => (
                <tr key={rule.id} className="border-t border-slate-100 align-top">
                  <td className="py-2 pr-3">
                    <p className="font-medium">{rule.rule_key}</p>
                    <p className="text-xs text-slate-500">
                      {rule.type}
                      {rule.policy_ref ? ` · ${rule.policy_ref}` : ''}
                    </p>
                  </td>
                  <td className="py-2 pr-3 text-xs">
                    {Object.entries(rule.params).map(([name, value]) => (
                      <p key={name} className={value === null ? 'font-medium text-red-700' : ''}>
                        {name}: {value === null ? 'UNRESOLVED' : String(value)}
                      </p>
                    ))}
                  </td>
                  <td className="py-2 pr-3">
                    <Badge value={rule.origin} />
                  </td>
                  <td className="py-2 pr-3 text-xs italic text-slate-600">“{rule.source_span}”</td>
                  <td className="py-2 text-xs">
                    <GroundedMark value={rule.grounded} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Clarification questions">
        {data.ambiguities.length === 0 && (
          <p className="text-sm text-slate-500">The AI found no ambiguities.</p>
        )}
        <div className="space-y-3">
          {data.ambiguities.map((ambiguity) => (
            <AmbiguityCard
              key={ambiguity.id}
              ambiguity={ambiguity}
              editable={draft}
              busy={busy}
              onChoose={(index) =>
                run(() => api.resolveAmbiguity(ambiguity.id, { option_index: index }, actor))
              }
              onDefer={() =>
                run(() => api.resolveAmbiguity(ambiguity.id, { defer: true }, actor))
              }
            />
          ))}
        </div>
      </Card>

      {data.assumptions.length > 0 && (
        <Card title="Assumptions made by the AI">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
            {data.assumptions.map((assumption) => (
              <li key={assumption.text}>{assumption.text}</li>
            ))}
          </ul>
        </Card>
      )}

      {data.issues.length > 0 && (
        <Card title="Validation issues">
          <ul className="space-y-1 text-sm">
            {data.issues.map((issue) => (
              <li key={`${issue.code}-${issue.field_path}`} className="flex flex-wrap gap-2">
                <Badge value={issue.severity} />
                <span className="font-medium">{issue.code}</span>
                <span className="text-slate-600">{issue.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {draft && (
        <Card title="Approve specification">
          <div className="space-y-3">
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Comment (optional)</span>
              <input
                className={inputClass}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </label>
            <ErrorBox error={error} />
            {error?.code === 'SPEC_NOT_APPROVABLE' && <Blockers details={error.details} />}
            <Button onClick={() => run(() => api.approveSpec(data.id, comment, actor))} disabled={busy}>
              {busy ? 'Working…' : 'Approve specification'}
            </Button>
            <p className="text-xs text-slate-500">
              Humans approve the meaning. Approval is blocked while questions, unresolved parameters or
              unverified rules remain.
            </p>
          </div>
        </Card>
      )}
    </div>
  )
}
