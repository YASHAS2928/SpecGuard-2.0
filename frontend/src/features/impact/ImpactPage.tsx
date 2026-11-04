import { GitCompare } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { analyzeImpact, loadRequirementSpecs, rerunImpacted } from '../../api/impact'
import type { ImpactClass, ImpactReport } from '../../api/impact'
import { loadSpecIndex } from '../../api/adapters'
import { api, toApiError } from '../../api/client'
import type { ApiError } from '../../api/client'
import { listSpecTests } from '../../api/tests'
import { useSession } from '../../app/session'
import { useWorkspace } from '../../app/workspace'
import { canEditSpec } from '../../components/domain/SpecParts'
import {
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Notice,
  Panel,
  Skeleton,
  SkeletonRows,
  StatusPill,
  Tabs,
  inputClass,
  useToast,
} from '../../components/ui'
import { useLoad } from '../../hooks'
import { useSyncWorkspace } from '../shared/useSyncWorkspace'
import { ImpactSummary, ImpactTests, ImpactWarnings, RuleChanges } from './ImpactResult'
import { VersionDiff } from './VersionDiff'

function SpecPicker() {
  const index = useLoad(() => loadSpecIndex(), 'spec-index')
  const candidates = index.data?.filter((item) => item.spec.status === 'APPROVED') ?? []
  return (
    <div className="mx-auto max-w-2xl">
      <Panel title="Choose the new (approved) specification">
        {index.loading && !index.data && <SkeletonRows rows={3} />}
        {index.error && <ErrorState error={index.error} onRetry={index.reload} />}
        {index.data && candidates.length === 0 && (
          <EmptyState
            icon={GitCompare}
            title="No approved specification to compare"
            description="Change impact compares an approved specification with an earlier one. Create a new requirement version, analyse and approve it first."
            action={
              <Link to="/requirements">
                <Button variant="primary">Go to Requirements</Button>
              </Link>
            }
          />
        )}
        <ul className="space-y-1">
          {candidates.map((item) => (
            <li key={item.spec.id}>
              <Link
                to={`/impact/${item.spec.id}`}
                className="flex items-center gap-2 rounded-md border border-line px-3 py-2 hover:bg-raised"
              >
                <span className="font-mono text-xs font-medium">{item.requirement.code}</span>
                <span className="text-sm text-fg-2">spec v{item.spec.version}</span>
                <span className="ml-auto">
                  <StatusPill value={item.spec.status} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}

function ImpactBoard({ specId }: { specId: string }) {
  const { actor } = useSession()
  const toast = useToast()
  const navigate = useNavigate()
  const spec = useLoad(() => api.getSpec(specId), `spec:${specId}`)
  const owner = useSyncWorkspace(specId, spec.data?.version)
  const requirementId = owner?.requirement.id
  const family = useLoad(
    () => (requirementId ? loadRequirementSpecs(requirementId) : Promise.resolve([])),
    `family:${requirementId ?? 'none'}`,
  )

  const [fromId, setFromId] = useState('')
  const [report, setReport] = useState<ImpactReport | null>(null)
  const [tab, setTab] = useState('diff')
  const [classFilter, setClassFilter] = useState<ImpactClass | ''>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [approvedRerun, setApprovedRerun] = useState<string[] | null>(null)

  const items = family.data ?? []
  const toItem = items.find((item) => item.spec.id === specId)
  const options = items.filter(
    (item) => item.spec.id !== specId && (item.spec.status === 'APPROVED' || item.spec.status === 'SUPERSEDED'),
  )
  const preferred =
    spec.data?.parent_spec_id && options.some((item) => item.spec.id === spec.data?.parent_spec_id)
      ? spec.data.parent_spec_id
      : options[options.length - 1]?.spec.id
  const effectiveFrom = fromId || preferred || ''
  const fromItem = items.find((item) => item.spec.id === effectiveFrom)
  const canRun = canEditSpec(actor.actor_role)

  useEffect(() => {
    if (!report) return
    let cancelled = false
    listSpecTests(specId)
      .then((tests) => {
        if (cancelled) return
        const approved = new Set(tests.filter((test) => test.status === 'APPROVED').map((test) => test.id))
        setApprovedRerun(report.rerun_test_ids.filter((id) => approved.has(id)))
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(toApiError(caught))
      })
    return () => {
      cancelled = true
    }
  }, [report, specId])

  async function analyse() {
    setBusy(true)
    setError(null)
    try {
      const result = await analyzeImpact(specId, effectiveFrom, actor)
      setReport(result)
      setApprovedRerun(null)
      setClassFilter('')
      setTab('rules')
      toast.push({ tone: 'ok', title: 'Impact analysed', description: `${result.rerun_test_ids.length} test(s) to rerun` })
    } catch (caught) {
      setError(toApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  async function rerun() {
    if (!approvedRerun || approvedRerun.length === 0) return
    setBusy(true)
    setError(null)
    try {
      const run = await rerunImpacted(specId, approvedRerun, actor)
      toast.push({
        tone: run.totals.failed + run.totals.errors === 0 ? 'ok' : 'warn',
        title: `Rerun finished: ${run.totals.passed}/${run.totals.total} passed`,
        description: `mock ${run.sut_version}`,
      })
      setConfirm(false)
      navigate(`/runs/${specId}`)
    } catch (caught) {
      setError(toApiError(caught))
      setConfirm(false)
    } finally {
      setBusy(false)
    }
  }

  if (spec.error) return <ErrorState error={spec.error} onRetry={spec.reload} />
  if (!spec.data) return <Skeleton className="h-64 w-full" />

  const waiting = report && report.rerun_test_ids.length > 0 && approvedRerun !== null && approvedRerun.length === 0

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">
          <span className="font-mono">{owner?.requirement.code ?? 'Specification'}</span>
          <span className="ml-2 text-fg-2">change impact</span>
        </h2>
        <StatusPill value={spec.data.status} />
      </div>

      <Panel>
        <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr_auto] md:items-end">
          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-fg-2">Previous specification</span>
            <select
              className={inputClass}
              value={effectiveFrom}
              onChange={(event) => {
                setFromId(event.target.value)
                setReport(null)
                setApprovedRerun(null)
                setError(null)
              }}
              disabled={options.length === 0}
            >
              {options.length === 0 && <option value="">none available</option>}
              {options.map((item) => (
                <option key={item.spec.id} value={item.spec.id}>
                  v{item.spec.version} · requirement version {item.version.version} · {item.spec.status.toLowerCase()}
                </option>
              ))}
            </select>
          </label>
          <span className="hidden pb-2 text-fg-3 md:block" aria-hidden="true">
            →
          </span>
          <div className="text-sm">
            <span className="mb-1 block text-xs font-medium text-fg-2">New specification</span>
            <p className="rounded-md border border-line-strong bg-well px-2 py-1.5">
              v{spec.data.version} · requirement version {toItem?.version.version ?? '…'}
            </p>
          </div>
          <Button
            variant="primary"
            disabled={busy || !!report || !canRun || !effectiveFrom || spec.data.status !== 'APPROVED'}
            title={
              !canRun
                ? 'Your role cannot run impact analysis'
                : spec.data.status !== 'APPROVED'
                  ? 'The new specification must be approved'
                  : report
                    ? 'This specification pair has already been analysed'
                    : undefined
            }
            onClick={analyse}
          >
            {busy && !confirm ? 'Analysing…' : report ? 'Analysis saved' : 'Analyse impact'}
          </Button>
        </div>
        {options.length === 0 && !family.loading && (
          <p className="mt-2 text-sm text-fg-2">
            There is no earlier approved specification of this requirement to compare with. Create a new requirement
            version, then analyse and approve it.
          </p>
        )}
        {spec.data.status !== 'APPROVED' && (
          <p className="mt-2 text-sm text-warn">
            This specification is not approved yet.{' '}
            <Link to={`/clarification/${specId}`} className="text-accent underline">
              Open Clarification
            </Link>
          </p>
        )}
      </Panel>

      {error && <ErrorState error={error} />}
      {report && <ImpactWarnings warnings={report.warnings} />}
      {report && <ImpactSummary report={report} />}

      <Panel bodyClassName="p-0">
        <div className="px-3 pt-1">
          <Tabs
            label="Impact views"
            value={tab}
            onChange={setTab}
            items={[
              { id: 'diff', label: 'Requirement diff' },
              { id: 'rules', label: 'Rule changes', count: report?.rule_changes.length },
              { id: 'tests', label: 'Impacted tests', count: report?.impacted_tests.length },
            ]}
          />
        </div>
        {tab === 'diff' && (
          <div className="p-4">
            {fromItem && toItem ? (
              <VersionDiff before={fromItem.version} after={toItem.version} />
            ) : (
              <p className="text-sm text-fg-3">
                {family.loading ? 'Loading versions…' : 'Select a previous specification to compare.'}
              </p>
            )}
          </div>
        )}
        {tab !== 'diff' && !report && (
          <EmptyState
            icon={GitCompare}
            title="No analysis yet"
            description="Run the analysis to see which rules changed and which tests are affected."
          />
        )}
        {tab === 'rules' && report && <RuleChanges report={report} />}
        {tab === 'tests' && report && (
          <ImpactTests report={report} filter={classFilter} onFilter={setClassFilter} toSpecId={specId} />
        )}
      </Panel>

      {report && (
        <Panel title="Rerun recommendation">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm">
              {report.rerun_test_ids.length} test(s) recommended;{' '}
              <span className="font-medium">{approvedRerun === null ? '…' : approvedRerun.length}</span> approved and
              ready to run.
            </p>
            <Button
              variant="primary"
              disabled={!canRun || approvedRerun === null || approvedRerun.length === 0}
              onClick={() => setConfirm(true)}
            >
              Rerun approved recommended tests
            </Button>
          </div>
          {waiting && (
            <Notice tone="info" title="Nothing can run yet">
              Stale and new tests are not approved.{' '}
              <Link to={`/tests/${specId}`} className="text-accent underline">
                Re-approve them in Test review
              </Link>
              , then come back.
            </Notice>
          )}
        </Panel>
      )}

      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        size="sm"
        title="Rerun impacted tests?"
        description="Only approved tests from the recommendation are sent to the mock API."
        footer={
          <>
            <Button onClick={() => setConfirm(false)}>Cancel</Button>
            <Button variant="primary" disabled={busy} onClick={rerun}>
              {busy ? 'Running…' : `Run ${approvedRerun?.length ?? 0} test(s)`}
            </Button>
          </>
        }
      >
        <p className="text-sm text-fg-2">
          If the system under test has not been updated for the policy change, the new boundary tests will fail. That is
          a real finding: the requirement and the implementation disagree.
        </p>
      </Dialog>
    </div>
  )
}

export default function ImpactPage() {
  const { specId } = useParams()
  const workspace = useWorkspace()
  if (!specId) {
    return workspace.specId ? <Navigate to={`/impact/${workspace.specId}`} replace /> : <SpecPicker />
  }
  return <ImpactBoard key={specId} specId={specId} />
}
