import { useState } from 'react'
import { toApiError } from '../../api/client'
import type { ApiError } from '../../api/client'
import type { DesignResult } from '../../api/tests'
import { designSpecTests } from '../../api/tests'
import { useSession } from '../../app/session'
import { Button, Dialog, ErrorState, Field, Notice, inputClass, useToast } from '../../components/ui'

export function GenerateDialog({
  open,
  onClose,
  specId,
  onDone,
}: {
  open: boolean
  onClose: () => void
  specId: string
  onDone: (result: DesignResult) => void
}) {
  const { actor } = useSession()
  const toast = useToast()
  const [withAi, setWithAi] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [result, setResult] = useState<DesignResult | null>(null)

  function close() {
    setError(null)
    setResult(null)
    onClose()
  }

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const done = await designSpecTests(specId, withAi, actor)
      setResult(done)
      onDone(done)
      toast.push({
        tone: 'ok',
        title: `${done.added} test(s) added`,
        description: `${done.already_present} already present`,
      })
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
      title="Generate tests"
      description="Engine tests are derived from the approved specification and their expected values come from the oracle. Running this again never duplicates tests or changes approvals."
      footer={
        <>
          <Button onClick={close}>{result ? 'Close' : 'Cancel'}</Button>
          {!result && (
            <Button variant="primary" onClick={run} disabled={busy}>
              {busy ? 'Generating…' : 'Generate'}
            </Button>
          )}
        </>
      }
    >
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={withAi} onChange={(event) => setWithAi(event.target.checked)} disabled={busy || result !== null} />
        <span>
          Also ask the AI for edge-case suggestions. They arrive as drafts, need individual approval, and the oracle
          still computes their expected values.
        </span>
      </label>
      {result && (
        <div className="space-y-2">
          <Notice tone="ok" title={`${result.added} added · ${result.already_present} already present`}>
            {Object.entries(result.counts_by_technique)
              .map(([name, count]) => `${name} ${count}`)
              .join(' · ')}
            {result.blocked_count > 0 ? ` · ${result.blocked_count} blocked by validation` : ''}
          </Notice>
          {result.ai_edge_cases !== 'generated' && (
            <Notice tone={result.ai_edge_cases === 'unavailable' ? 'warn' : 'info'} title={`AI edge cases: ${result.ai_edge_cases.replace('_', ' ')}`}>
              {result.ai_message}
            </Notice>
          )}
        </div>
      )}
      {error && <ErrorState error={error} compact />}
    </Dialog>
  )
}

export function ReviewDialog({
  open,
  mode,
  count,
  label,
  onClose,
  onConfirm,
}: {
  open: boolean
  mode: 'approve' | 'reject'
  count: number
  label: string
  onClose: () => void
  onConfirm: (reason: string) => Promise<void>
}) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const reject = mode === 'reject'

  function close() {
    setError(null)
    setReason('')
    onClose()
  }

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await onConfirm(reason.trim())
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
      size="sm"
      title={reject ? `Reject ${label}?` : `Approve ${label}?`}
      description={
        reject
          ? 'Rejected tests are never run. A reason is required and recorded in the audit log.'
          : `Approved tests can be executed. ${count} test(s) will be approved in your name.`
      }
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant={reject ? 'danger' : 'primary'} disabled={busy || (reject && reason.trim().length === 0)} onClick={confirm}>
            {busy ? 'Saving…' : reject ? 'Reject' : 'Approve'}
          </Button>
        </>
      }
    >
      {reject && (
        <Field label="Reason (required)">
          <input data-autofocus className={inputClass} value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
      )}
      {error && <ErrorState error={error} compact />}
    </Dialog>
  )
}
