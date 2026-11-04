import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { api, toApiError } from '../../api/client'
import type { ApiError } from '../../api/client'
import type { Spec } from '../../api/types'
import { useSession } from '../../app/session'
import { Button, Dialog, ErrorState, Field, inputClass, useToast } from '../ui'
import { Blockers } from './SpecParts'

export function ApproveSpecDialog({
  open,
  onClose,
  spec,
  onApproved,
}: {
  open: boolean
  onClose: () => void
  spec: Spec
  onApproved: (spec: Spec) => void
}) {
  const { actor } = useSession()
  const toast = useToast()
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const checks = [
    { label: 'Every question is resolved', ok: spec.open_ambiguities === 0 },
    { label: 'No unresolved parameters', ok: spec.rules.every((rule) => rule.unresolved_params.length === 0) },
    { label: 'No blocking validation issues', ok: spec.blocking_issue_count === 0 },
    { label: 'Every rule\'s source text is verified', ok: spec.rules.every((rule) => rule.grounded === true) },
  ]
  const ready = checks.every((check) => check.ok)

  function close() {
    setError(null)
    setComment('')
    onClose()
  }

  async function approve() {
    setBusy(true)
    setError(null)
    try {
      const result = await api.approveSpec(spec.id, comment, actor)
      onApproved(result)
      toast.push({ tone: 'ok', title: `Specification v${result.version} approved`, description: `by ${actor.actor}` })
      close()
    } catch (caught) {
      setError(toApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title={`Approve specification v${spec.version}`}
      description="Approval is a human decision. Tests can only be designed from an approved specification."
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" onClick={approve} disabled={busy || !ready}>
            {busy ? 'Approving…' : 'Approve specification'}
          </Button>
        </>
      }
    >
      <ul className="space-y-1.5 text-sm">
        {checks.map((check) => (
          <li key={check.label} className="flex items-center gap-2">
            {check.ok ? (
              <Check size={14} className="text-ok" aria-hidden="true" />
            ) : (
              <X size={14} className="text-bad" aria-hidden="true" />
            )}
            <span className={check.ok ? 'text-fg-2' : 'text-fg'}>{check.label}</span>
          </li>
        ))}
      </ul>
      {!ready && <p className="text-xs text-fg-3">Resolve the items marked ✕ before approving.</p>}
      <Field label="Comment (optional)">
        <input
          data-autofocus
          className={inputClass}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      </Field>
      {error &&
        (error.code === 'SPEC_NOT_APPROVABLE' ? (
          <>
            <Blockers details={error.details} />
            {error.traceId && (
              <p className="font-mono text-xs text-fg-2">
                {error.code} · trace {error.traceId}
              </p>
            )}
          </>
        ) : (
          <ErrorState error={error} compact />
        ))}
    </Dialog>
  )
}
