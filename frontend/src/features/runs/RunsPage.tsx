import { Play } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { loadSpecIndex } from '../../api/adapters'
import { api, toApiError } from '../../api/client'
import type { ApiError } from '../../api/client'
import { createRun, listDefects, loadRunHistory } from '../../api/runs'
import type { DefectRecord, RunRecord } from '../../api/runs'
import { listSpecTests } from '../../api/tests'
import { useSession } from '../../app/session'
import { useWorkspace } from '../../app/workspace'
import { SegmentedBar } from '../../components/domain/Charts'
import { canEditSpec } from '../../components/domain/SpecParts'
import {
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Notice,
  Panel,
  Pill,
  Skeleton,
  SkeletonRows,
  StatusPill,
  Tabs,
  useToast,
} from '../../components/ui'
import { useLoad } from '../../hooks'
import { formatDateTime } from '../../lib/format'
import { percent, passRate } from '../../lib/runs'
import { useSyncWorkspace } from '../shared/useSyncWorkspace'
import { DefectList } from './DefectList'
import { MockControl } from './MockControl'
import { ResultDrawer } from './ResultDrawer'
import { RunHistory } from './RunHistory'
import { RunTable } from './RunTable'

function SpecPicker() {
  const index = useLoad(() => loadSpecIndex(), 'spec-index')
  const approved = index.data?.filter((item) => item.spec.status === 'APPROVED') ?? []
  return (
    <div className="mx-auto max-w-2xl">
      <Panel title="Choose an approved specification">
        {index.loading && !index.data && <SkeletonRows rows={3} />}
        {index.error && <ErrorState error={index.error} onRetry={index.reload} />}
        {index.data && approved.length === 0 && (
          <EmptyState
            icon={Play}
            title="Nothing to run yet"
            description="Tests run from an approved specification with approved tests."
            action={
              <Link to="/requirements">
                <Button variant="primary">Go to Requirements</Button>
              </Link>
            }
          />
        )}
        <ul className="space-y-1">
          {approved.map((item) => (
            <li key={item.spec.id}>
              <Link
                to={`/runs/${item.spec.id}`}
                className="flex items-center gap-2 rounded-md border border-line px-3 py-2 hover:bg-raised"
              >
                <span className="font-mono text-xs font-medium">{item.requirement.code}</span>
                <span className="text-sm text-fg-2">spec v{item.spec.version}</span>
                <span className="ml-auto"><StatusPill value={item.spec.status} /></span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}

function RunBoard({ specId }: { specId: string }) {
  const { actor } = useSession()
  const toast = useToast()
  const spec = useLoad(() => api.getSpec(specId), `spec:${specId}`)
  const tests = useLoad(() => listSpecTests(specId), `tests:${specId}`)
  const defects = useLoad(() => listDefects({ spec_id: specId }), `defects:${specId}`)
  const history = useLoad(() => loadRunHistory(10, specId), `history:${specId}`)
  const owner = useSyncWorkspace(specId, spec.data?.version)
  const canRun = canEditSpec(actor.actor_role)

  const [pickedId, setPickedId] = useState<string | null>(null)
  const [fresh, setFresh] = useState<RunRecord | null>(null)
  const [filter, setFilter] = useState('all')
  const [openResult, setOpenResult] = useState<string | null>(null)
  const [defectFilter, setDefectFilter] = useState<DefectRecord | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [mockVersion, setMockVersion] = useState('')

  const approved = (tests.data ?? []).filter((test) => test.status === 'APPROVED')
  const testsById = useMemo(() => new Map((tests.data ?? []).map((test) => [test.id, test])), [tests.data])

  const activeId = pickedId ?? fresh?.id ?? history.data?.[0]?.id ?? null
  const run =
    (fresh && fresh.id === activeId ? fresh : null) ?? history.data?.find((item) => item.id === activeId) ?? null

  const results = useMemo(() => {
    const all = run?.results ?? []
    const byStatus =
      filter === 'failed' ? all.filter((r) => r.status === 'FAIL')
      : filter === 'errors' ? all.filter((r) => r.status === 'ERROR')
      : filter === 'passed' ? all.filter((r) => r.status === 'PASS')
      : all
    if (!defectFilter) return byStatus
    const wanted = new Set(defectFilter.evidence_result_ids)
    return byStatus.filter((r) => wanted.has(r.id))
  }, [run, filter, defectFilter])

  const opened = run?.results.find((item) => item.id === openResult) ?? null

  async function execute() {
    setBusy(true)
    setError(null)
    try {
      const result = await createRun(specId, null, actor)
      setFresh(result)
      setPickedId(result.id)
      setDefectFilter(null)
      setFilter('all')
      setConfirm(false)
      history.reload()
      defects.reload()
      toast.push({
        tone: result.totals.failed + result.totals.errors === 0 ? 'ok' : 'warn',
        title: `Run finished: ${result.totals.passed}/${result.totals.total} passed`,
        description: `mock ${result.sut_version}`,
      })
    } catch (caught) {
      setError(toApiError(caught))
    } finally {
      setBusy(false)
    }
  }

  if (spec.error) return <ErrorState error={spec.error} onRetry={spec.reload} />
  if (!spec.data) return <Skeleton className="h-64 w-full" />

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">
          <span className="font-mono">{owner?.requirement.code ?? 'Specification'}</span>
          <span className="ml-2 text-fg-2">v{spec.data.version}</span>
        </h2>
        <StatusPill value={spec.data.status} />
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-fg-2">{approved.length} approved test(s)</span>
          <Button variant="primary" disabled={!canRun || approved.length === 0} onClick={() => setConfirm(true)}>
            <Play size={14} aria-hidden="true" />
            Run approved tests
          </Button>
        </div>
      </div>

      {approved.length === 0 && !tests.loading && (
        <Notice tone="warn" title="No approved tests">
          Only approved tests can run.{' '}
          <Link to={`/tests/${specId}`} className="text-accent underline">
            Review and approve tests
          </Link>
          .
        </Notice>
      )}
      {error && <ErrorState error={error} />}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-4">
          {!run && !history.loading && (
            <Panel>
              <EmptyState
                icon={Play}
                title="No run yet"
                description="Run the approved tests against the system under test to see expected vs. observed results."
              />
            </Panel>
          )}
          {history.loading && !history.data && <Skeleton className="h-40 w-full" />}
          {history.error && <ErrorState error={history.error} onRetry={history.reload} />}

          {run && (
            <>
              <Panel>
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="text-base font-semibold">Run on mock {run.sut_version}</h3>
                  <Pill tone={run.totals.failed + run.totals.errors === 0 ? 'ok' : 'bad'}>
                    {percent(passRate(run.totals))} passed
                  </Pill>
                  <span className="text-xs text-fg-3">
                    {formatDateTime(run.started_at)} · {run.trigger.toLowerCase()}
                  </span>
                </div>
                <div className="mt-3">
                  <SegmentedBar
                    label="Run result"
                    segments={[
                      { label: 'passed', value: run.totals.passed, className: 'bg-ok' },
                      { label: 'failed', value: run.totals.failed, className: 'bg-bad' },
                      { label: 'errors', value: run.totals.errors, className: 'bg-warn' },
                    ]}
                  />
                </div>
                {run.totals.errors > 0 && (
                  <p className="mt-2 text-xs text-warn">
                    Errors mean the system could not be reached or answered unexpectedly. They are never counted as passes.
                  </p>
                )}
              </Panel>

              <Panel bodyClassName="p-0">
                <div className="px-3 pt-1">
                  <Tabs
                    label="Result filter"
                    value={filter}
                    onChange={setFilter}
                    items={[
                      { id: 'all', label: 'All', count: run.totals.total },
                      { id: 'failed', label: 'Failed', count: run.totals.failed },
                      { id: 'errors', label: 'Errors', count: run.totals.errors },
                      { id: 'passed', label: 'Passed', count: run.totals.passed },
                    ]}
                  />
                </div>
                {defectFilter && (
                  <div className="flex items-center gap-2 border-b border-line px-3 py-2 text-sm">
                    <Pill tone="accent">defect: {defectFilter.title}</Pill>
                    <Button size="sm" variant="ghost" onClick={() => setDefectFilter(null)}>
                      Clear
                    </Button>
                  </div>
                )}
                {results.length === 0 ? (
                  <p className="px-3 py-8 text-center text-sm text-fg-3">
                    {defectFilter ? 'This defect has no failing results in the selected run.' : 'Nothing in this view.'}
                  </p>
                ) : (
                  <RunTable results={results} testsById={testsById} onOpen={setOpenResult} />
                )}
              </Panel>
            </>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          <MockControl onChanged={setMockVersion} />
          {defects.loading && !defects.data && <Skeleton className="h-32 w-full" />}
          {defects.error && <ErrorState error={defects.error} onRetry={defects.reload} compact />}
          {defects.data && (
            <DefectList defects={defects.data} activeId={defectFilter?.id ?? null} onShow={setDefectFilter} />
          )}
          <RunHistory
            runs={history.data}
            loading={history.loading}
            activeId={activeId}
            onSelect={(id) => {
              setPickedId(id)
              setFresh(null)
            }}
          />
        </div>
      </div>

      <ResultDrawer
        result={opened}
        test={opened ? testsById.get(opened.test_case_id) : undefined}
        defects={defects.data ?? []}
        runVersion={run?.sut_version ?? ''}
        onClose={() => setOpenResult(null)}
      />

      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        size="sm"
        title="Run approved tests?"
        description="Only approved tests are sent to the configured mock API."
        footer={
          <>
            <Button onClick={() => setConfirm(false)}>Cancel</Button>
            <Button variant="primary" onClick={execute} disabled={busy}>
              {busy ? 'Running…' : 'Run'}
            </Button>
          </>
        }
      >
        <p className="text-sm">
          {approved.length} approved test(s) will run as <span className="font-medium">{actor.actor}</span> against mock{' '}
          <span className="font-mono">{mockVersion || 'version unavailable'}</span>. Results are saved and written to the
          audit log.
        </p>
      </Dialog>
    </div>
  )
}

export default function RunsPage() {
  const { specId } = useParams()
  const workspace = useWorkspace()
  if (!specId) {
    return workspace.specId ? <Navigate to={`/runs/${workspace.specId}`} replace /> : <SpecPicker />
  }
  return <RunBoard key={specId} specId={specId} />
}
