import { useState } from 'react'
import { api, toApiError } from '../../api/client'
import type { ApiError } from '../../api/client'
import type { AnalyzeResponse, Policy, Requirement, RequirementVersion } from '../../api/types'
import { DEFAULT_POLICY_REFS, PolicyPicker } from '../../components/domain/PolicyPicker'
import { Button, Dialog, ErrorState, Field, inputClass, useToast } from '../../components/ui'
import { useSession } from '../../app/session'

const SAMPLE_TITLE = 'Overnight overtime with unpaid meal break'
const SAMPLE_TEXT =
  'For an overnight shift, calculate overtime correctly after the employee has worked the configured number of paid hours, excluding the unpaid meal break.'

export function NewRequirementDialog({
  open,
  onClose,
  policies,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  policies: Policy[]
  onCreated: (requirement: Requirement) => void
}) {
  const { actor } = useSession()
  const toast = useToast()
  const [code, setCode] = useState('')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [refs, setRefs] = useState<string[]>(DEFAULT_POLICY_REFS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  function close() {
    setError(null)
    onClose()
  }

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const created = await api.createRequirement({ code, title, text, policy_ids: refs }, actor)
      toast.push({ tone: 'ok', title: `Requirement ${created.code} created` })
      onCreated(created)
      setCode('')
      setTitle('')
      setText('')
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
      size="lg"
      title="New requirement"
      description="Describe the requirement and attach the policies it must follow."
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={busy || !code || !title || !text}>
            {busy ? 'Creating…' : 'Create requirement'}
          </Button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Code" hint="Format RQ-014">
          <input data-autofocus className={inputClass} value={code} placeholder="RQ-015" onChange={(e) => setCode(e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Title">
            <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
        </div>
      </div>
      <Field label="Requirement text" hint="At least 10 characters.">
        <textarea className={inputClass} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          setTitle(SAMPLE_TITLE)
          setText(SAMPLE_TEXT)
        }}
      >
        Fill with the RQ-014 sample text
      </Button>
      <PolicyPicker policies={policies} value={refs} onChange={setRefs} />
      {error && <ErrorState error={error} compact />}
    </Dialog>
  )
}

export function NewVersionDialog({
  open,
  onClose,
  requirement,
  policies,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  requirement: Requirement
  policies: Policy[]
  onCreated: () => void
}) {
  const { actor } = useSession()
  const toast = useToast()
  const latest = requirement.versions[requirement.versions.length - 1]
  const [text, setText] = useState(latest?.text ?? '')
  const [refs, setRefs] = useState<string[]>(latest?.policy_ids ?? DEFAULT_POLICY_REFS)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  function close() {
    setError(null)
    onClose()
  }

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const created: RequirementVersion = await api.createVersion(
        requirement.id,
        { text, policy_ids: refs, change_note: note.trim() || null },
        actor,
      )
      toast.push({ tone: 'ok', title: `Version ${created.version} created`, description: requirement.code })
      onCreated()
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
      size="lg"
      title={`New version of ${requirement.code}`}
      description="Versions are immutable. For a policy change, attach the new policy version (for example POL-OT-01@v2)."
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={busy || !text}>
            {busy ? 'Saving…' : 'Create version'}
          </Button>
        </>
      }
    >
      <Field label="Text">
        <textarea data-autofocus className={inputClass} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <PolicyPicker policies={policies} value={refs} onChange={setRefs} />
      <Field label="Change note">
        <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {error && <ErrorState error={error} compact />}
    </Dialog>
  )
}

export function AnalyseDialog({
  open,
  onClose,
  version,
  hasApprovedSpec,
  onDone,
}: {
  open: boolean
  onClose: () => void
  version: RequirementVersion
  hasApprovedSpec: boolean
  onDone: (result: AnalyzeResponse) => void
}) {
  const { actor } = useSession()
  const toast = useToast()
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  function close() {
    setError(null)
    onClose()
  }

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const result = await api.analyze(version.id, force, actor)
      toast.push({
        tone: 'ok',
        title: `Analysis complete: spec v${result.spec.version} drafted`,
        description: `${result.analysis.provider}${result.analysis.model ? ` · ${result.analysis.model}` : ''}`,
      })
      onDone(result)
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
      title={`Analyse version ${version.version}`}
      description="The AI drafts rules and questions. Nothing is approved automatically."
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" onClick={run} disabled={busy}>
            {busy ? 'Analysing…' : 'Run analysis'}
          </Button>
        </>
      }
    >
      <p className="text-sm text-fg-2">
        Attached policies: <span className="font-mono">{version.policy_ids.join(', ')}</span>
      </p>
      {hasApprovedSpec && (
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={force} onChange={(e) => setForce(e.target.checked)} />
          <span>
            A specification is already approved for this version. Draft a new one anyway (the approved one stays
            approved until the new one is).
          </span>
        </label>
      )}
      {error && <ErrorState error={error} compact />}
    </Dialog>
  )
}
