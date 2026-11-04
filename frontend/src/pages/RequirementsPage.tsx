import { useState } from 'react'
import { api, toApiError } from '../api/client'
import type { ApiError } from '../api/client'
import type {
  Actor,
  AnalysisMetadata,
  Policy,
  Requirement,
  RequirementVersion,
  Spec,
} from '../api/types'
import { Badge, Button, Card, ErrorBox, Loading, inputClass } from '../components/ui'
import { useLoad } from '../hooks'

const DEFAULT_REFS = ['POL-OT-01@v1', 'POL-MEAL-02@v1', 'POL-DATE-03@v1']
const RQ014_TEXT =
  'For an overnight shift, calculate overtime correctly after the employee has worked the configured number of paid hours, excluding the unpaid meal break.'

function PolicyPicker({
  policies,
  value,
  onChange,
}: {
  policies: Policy[]
  value: string[]
  onChange: (refs: string[]) => void
}) {
  const codes = Array.from(new Set(policies.map((p) => p.policy_code))).sort()
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {codes.map((code) => {
        const selected = value.find((ref) => ref.startsWith(`${code}@`)) ?? ''
        return (
          <label key={code} className="text-sm">
            <span className="mb-1 block font-medium">{code}</span>
            <select
              className={inputClass}
              value={selected}
              onChange={(e) =>
                onChange([
                  ...value.filter((ref) => !ref.startsWith(`${code}@`)),
                  ...(e.target.value ? [e.target.value] : []),
                ])
              }
            >
              <option value="">not attached</option>
              {policies
                .filter((p) => p.policy_code === code)
                .map((p) => (
                  <option key={p.ref} value={p.ref}>
                    {p.ref} (from {p.effective_from}
                    {p.effective_to ? ` to ${p.effective_to}` : ''})
                  </option>
                ))}
            </select>
          </label>
        )
      })}
    </div>
  )
}

function CreateRequirementForm({
  policies,
  actor,
  onCreated,
}: {
  policies: Policy[]
  actor: Actor
  onCreated: (requirement: Requirement) => void
}) {
  const [code, setCode] = useState('RQ-014')
  const [title, setTitle] = useState('Overnight overtime with unpaid meal break')
  const [text, setText] = useState(RQ014_TEXT)
  const [refs, setRefs] = useState<string[]>(DEFAULT_REFS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      onCreated(await api.createRequirement({ code, title, text, policy_ids: refs }, actor))
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="New requirement">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block font-medium">Code</span>
            <input className={inputClass} value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          <label className="text-sm sm:col-span-2">
            <span className="mb-1 block font-medium">Title</span>
            <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
        </div>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Requirement text</span>
          <textarea
            className={inputClass}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <PolicyPicker policies={policies} value={refs} onChange={setRefs} />
        <ErrorBox error={error} />
        <Button onClick={submit} disabled={busy}>
          {busy ? 'Creating…' : 'Create requirement'}
        </Button>
      </div>
    </Card>
  )
}

function NewVersionForm({
  requirement,
  policies,
  actor,
  onCreated,
}: {
  requirement: Requirement
  policies: Policy[]
  actor: Actor
  onCreated: () => void
}) {
  const latest = requirement.versions[requirement.versions.length - 1]
  const [text, setText] = useState(latest?.text ?? '')
  const [refs, setRefs] = useState<string[]>(latest?.policy_ids ?? DEFAULT_REFS)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await api.createVersion(
        requirement.id,
        { text, policy_ids: refs, change_note: note.trim() || null },
        actor,
      )
      setNote('')
      onCreated()
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="New version (for example: attach POL-OT-01@v2)">
      <div className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Text</span>
          <textarea
            className={inputClass}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <PolicyPicker policies={policies} value={refs} onChange={setRefs} />
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Change note</span>
          <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <ErrorBox error={error} />
        <Button onClick={submit} disabled={busy}>
          {busy ? 'Saving…' : 'Create version'}
        </Button>
      </div>
    </Card>
  )
}

function VersionRow({
  version,
  actor,
  onOpenSpec,
}: {
  version: RequirementVersion
  actor: Actor
  onOpenSpec: (specId: string, analysis: AnalysisMetadata | null) => void
}) {
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [specs, setSpecs] = useState<Spec[] | null>(null)

  async function analyze() {
    setBusy(true)
    setError(null)
    try {
      const result = await api.analyze(version.id, force, actor)
      onOpenSpec(result.spec.id, result.analysis)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  async function showSpecs() {
    setError(null)
    try {
      setSpecs(await api.listSpecs(version.id))
    } catch (e) {
      setError(toApiError(e))
    }
  }

  return (
    <li className="rounded border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Version {version.version}</span>
        <span className="text-xs text-slate-500">
          by {version.author} · {new Date(version.created_at).toLocaleString()}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-700">{version.text}</p>
      <p className="mt-1 text-xs text-slate-500">Policies: {version.policy_ids.join(', ')}</p>
      {version.change_note && (
        <p className="mt-1 text-xs italic text-slate-500">Note: {version.change_note}</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button onClick={analyze} disabled={busy}>
          {busy ? 'Analysing…' : 'Analyse'}
        </Button>
        <label className="flex items-center gap-1 text-xs text-slate-600">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
          Force a new draft (if a spec is already approved)
        </label>
        <Button variant="secondary" onClick={showSpecs}>
          Show specifications
        </Button>
      </div>
      <div className="mt-2">
        <ErrorBox error={error} />
      </div>
      {specs && (
        <ul className="mt-2 space-y-1 text-sm">
          {specs.length === 0 && <li className="text-slate-500">No specifications yet.</li>}
          {specs.map((spec) => (
            <li key={spec.id} className="flex items-center gap-2">
              <span>Spec v{spec.version}</span>
              <Badge value={spec.status} />
              <Button variant="secondary" onClick={() => onOpenSpec(spec.id, null)}>
                Open
              </Button>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

export default function RequirementsPage({
  actor,
  onOpenSpec,
}: {
  actor: Actor
  onOpenSpec: (specId: string, analysis: AnalysisMetadata | null) => void
}) {
  const requirements = useLoad(() => api.listRequirements(), 'requirements')
  const policies = useLoad(() => api.listPolicies(), 'policies')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const selected = requirements.data?.find((r) => r.id === selectedId) ?? null

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-1">
        <Card title="Requirements">
          {requirements.loading && <Loading />}
          <ErrorBox error={requirements.error} />
          {requirements.data && requirements.data.length === 0 && (
            <p className="text-sm text-slate-500">No requirements yet. Create one.</p>
          )}
          <ul className="space-y-2">
            {requirements.data?.map((requirement) => (
              <li key={requirement.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(requirement.id)}
                  className={`w-full rounded border p-2 text-left text-sm hover:bg-slate-50 ${
                    requirement.id === selectedId ? 'border-indigo-500' : 'border-slate-200'
                  }`}
                >
                  <span className="font-medium">{requirement.code}</span>{' '}
                  <Badge value={requirement.status} />
                  <span className="block text-xs text-slate-500">
                    {requirement.title} · {requirement.latest_version} version(s)
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="space-y-4 lg:col-span-2">
        {policies.error && <ErrorBox error={policies.error} />}
        {policies.data && (
          <CreateRequirementForm
            policies={policies.data}
            actor={actor}
            onCreated={(requirement) => {
              setSelectedId(requirement.id)
              requirements.reload()
            }}
          />
        )}

        {selected && (
          <Card title={`${selected.code}: ${selected.title}`}>
            <ul className="space-y-3">
              {selected.versions.map((version) => (
                <VersionRow
                  key={version.id}
                  version={version}
                  actor={actor}
                  onOpenSpec={(specId, analysis) => {
                    requirements.reload()
                    onOpenSpec(specId, analysis)
                  }}
                />
              ))}
            </ul>
          </Card>
        )}

        {selected && policies.data && (
          <NewVersionForm
            key={`${selected.id}:${selected.latest_version}`}
            requirement={selected}
            policies={policies.data}
            actor={actor}
            onCreated={requirements.reload}
          />
        )}
      </div>
    </div>
  )
}
