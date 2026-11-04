import { FlaskConical, Search, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { loadSpecIndex } from '../../api/adapters'
import { api } from '../../api/client'
import { designSpecTests, listSpecTests, reviewSpecTests } from '../../api/tests'
import type { CriterionRecord, ReviewResult, Technique, TestRecord } from '../../api/tests'
import { useSession } from '../../app/session'
import { useWorkspace } from '../../app/workspace'
import { canEditSpec } from '../../components/domain/SpecParts'
import {
  Button,
  EmptyState,
  ErrorState,
  Panel,
  Pill,
  Skeleton,
  SkeletonRows,
  StatusPill,
  inputClass,
  useToast,
} from '../../components/ui'
import { useLoad } from '../../hooks'
import { countByStatus, isBulkEligible, TECHNIQUES } from '../../lib/tests'
import { useSyncWorkspace } from '../shared/useSyncWorkspace'
import { CoverageMatrix } from './CoverageMatrix'
import type { MatrixPick } from './CoverageMatrix'
import { GenerateDialog, ReviewDialog } from './Dialogs'
import { TestDrawer } from './TestDrawer'
import { TestTable } from './TestTable'

const STATUSES = ['DRAFT', 'BLOCKED', 'APPROVED', 'REJECTED', 'STALE', 'OBSOLETE']
const EMPTY_TESTS: TestRecord[] = []

interface Pending {
  mode: 'approve' | 'reject'
  ids: string[]
  label: string
}

function SpecPicker() {
  const index = useLoad(() => loadSpecIndex(), 'spec-index')
  return (
    <div className="mx-auto max-w-2xl">
      <Panel title="Choose an approved specification">
        {index.loading && !index.data && <SkeletonRows rows={3} />}
        {index.error && <ErrorState error={index.error} onRetry={index.reload} />}
        {index.data && index.data.length === 0 && (
          <EmptyState
            icon={FlaskConical}
            title="No specification yet"
            description="Tests are designed from an approved specification. Analyse and approve one first."
            action={
              <Link to="/requirements">
                <Button variant="primary">Go to Requirements</Button>
              </Link>
            }
          />
        )}
        <ul className="space-y-1">
          {index.data?.map((item) => (
            <li key={item.spec.id}>
              <Link
                to={`/tests/${item.spec.id}`}
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

function TestBoard({ specId }: { specId: string }) {
  const { actor } = useSession()
  const toast = useToast()
  const spec = useLoad(() => api.getSpec(specId), `spec:${specId}`)
  const tests = useLoad(() => listSpecTests(specId), `tests:${specId}`)
  const owner = useSyncWorkspace(specId, spec.data?.version)

  const [filters, setFilters] = useState({ q: '', technique: '', status: '', origin: '', rule: '' })
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openId, setOpenId] = useState<string | null>(null)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [refusals, setRefusals] = useState<ReviewResult['refused']>([])
  const [criteria, setCriteria] = useState<Record<string, CriterionRecord>>({})

  const all = tests.data ?? EMPTY_TESTS
  const visible = useMemo(() => {
    const query = filters.q.trim().toLowerCase()
    return all.filter(
      (test) =>
        (!filters.technique || test.technique === filters.technique) &&
        (!filters.status || test.status === filters.status) &&
        (!filters.origin || test.origin === filters.origin) &&
        (!filters.rule || test.rule_keys.includes(filters.rule)) &&
        (!query || `${test.tc_code} ${test.rationale} ${test.rule_keys.join(' ')}`.toLowerCase().includes(query)),
    )
  }, [all, filters])

  const counts = countByStatus(all)
  const canReview = canEditSpec(actor.actor_role)
  const opened = all.find((test) => test.id === openId) ?? null
  const codeById = new Map(all.map((test) => [test.id, test.tc_code]))
  const matrixPick: MatrixPick = { rule: filters.rule, technique: filters.technique as Technique | '' }

  function rememberCriteria(list: CriterionRecord[]) {
    setCriteria((current) => ({ ...current, ...Object.fromEntries(list.map((item) => [item.crit_code, item])) }))
  }

  async function loadCriteria() {
    try {
      const result = await designSpecTests(specId, false, actor)
      rememberCriteria(result.criteria)
    } catch {
      toast.push({ tone: 'bad', title: 'Could not load criterion text' })
    }
  }

  async function confirmReview(reason: string) {
    if (!pending) return
    const result = await reviewSpecTests(
      pending.ids,
      pending.mode === 'approve' ? 'APPROVE' : 'REJECT',
      reason || null,
      actor,
    )
    setRefusals(result.refused)
    setSelected(new Set())
    setOpenId(null)
    tests.reload()
    toast.push({
      tone: result.refused.length > 0 ? 'warn' : 'ok',
      title: `${result.reviewed.length} test(s) ${pending.mode === 'approve' ? 'approved' : 'rejected'}`,
      description: result.refused.length > 0 ? `${result.refused.length} refused, see the list below` : undefined,
    })
  }

  if (spec.error) return <ErrorState error={spec.error} onRetry={spec.reload} />
  if (!spec.data) return <Skeleton className="h-64 w-full" />
  const data = spec.data

  const header = (
    <div className="flex flex-wrap items-center gap-3">
      <h2 className="text-xl font-semibold">
        <span className="font-mono">{owner?.requirement.code ?? 'Specification'}</span>
        <span className="ml-2 text-fg-2">v{data.version}</span>
      </h2>
      <StatusPill value={data.status} />
      <Link to="/clarification" className="text-sm text-accent underline">
        Specification details
      </Link>
      <div className="ml-auto flex gap-2">
        <Button variant="primary" disabled={data.status !== 'APPROVED'} onClick={() => setGenerateOpen(true)}>
          <Sparkles size={14} aria-hidden="true" />
          {all.length > 0 ? 'Generate / refresh' : 'Generate tests'}
        </Button>
      </div>
    </div>
  )

  if (data.status !== 'APPROVED' && all.length === 0) {
    return (
      <div className="mx-auto max-w-[1500px] space-y-4">
        {header}
        <Panel>
          <EmptyState
            icon={FlaskConical}
            title="This specification is not approved"
            description="Tests can only be designed from an approved specification. Resolve the open questions and approve it first."
            action={
              <Link to={`/clarification/${data.id}`}>
                <Button variant="primary">Open Clarification</Button>
              </Link>
            }
          />
        </Panel>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      {header}

      <div className="flex flex-wrap gap-2">
        {STATUSES.filter((name) => counts[name]).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setFilters((f) => ({ ...f, status: f.status === name ? '' : name }))}
            aria-pressed={filters.status === name}
            className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${
              filters.status === name ? 'border-accent bg-accent/10' : 'border-line bg-surface hover:bg-raised'
            }`}
          >
            <StatusPill value={name} />
            <span className="tabular-nums">{counts[name]}</span>
          </button>
        ))}
        {all.length === 0 && !tests.loading && <Pill tone="info">no tests yet</Pill>}
      </div>

      {refusals.length > 0 && (
        <div role="alert" className="rounded-md border border-warn/40 bg-warn/10 p-3 text-sm">
          <div className="flex items-center justify-between">
            <p className="font-medium">{refusals.length} test(s) were not changed:</p>
            <Button size="sm" variant="ghost" onClick={() => setRefusals([])}>
              Dismiss
            </Button>
          </div>
          <ul className="mt-1 space-y-0.5 text-fg-2">
            {refusals.map((item) => (
              <li key={item.test_id}>
                <span className="font-mono text-xs">{codeById.get(item.test_id) ?? item.test_id}</span>: {item.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {all.length > 0 && (
        <CoverageMatrix
          ruleKeys={data.rules.map((rule) => rule.rule_key)}
          tests={all}
          active={matrixPick}
          onPick={(pick) => setFilters((f) => ({ ...f, rule: pick.rule, technique: pick.technique }))}
        />
      )}

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-48 flex-1">
            <Search size={13} className="absolute left-2 top-2.5 text-fg-3" aria-hidden="true" />
            <input
              aria-label="Search tests"
              placeholder="Search code, rationale, rule…"
              value={filters.q}
              onChange={(event) => setFilters((f) => ({ ...f, q: event.target.value }))}
              className={`${inputClass} pl-7`}
            />
          </div>
          <select aria-label="Technique" className={`${inputClass} w-auto`} value={filters.technique} onChange={(e) => setFilters((f) => ({ ...f, technique: e.target.value }))}>
            <option value="">All techniques</option>
            {TECHNIQUES.map((name) => <option key={name}>{name}</option>)}
          </select>
          <select aria-label="Origin" className={`${inputClass} w-auto`} value={filters.origin} onChange={(e) => setFilters((f) => ({ ...f, origin: e.target.value }))}>
            <option value="">All origins</option>
            <option value="ENGINE">Engine</option>
            <option value="AI">AI</option>
          </select>
          <select aria-label="Status" className={`${inputClass} w-auto`} value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
            <option value="">All statuses</option>
            {STATUSES.map((name) => <option key={name}>{name}</option>)}
          </select>
          {filters.rule && (
            <Pill tone="accent">
              rule {filters.rule}
              <button type="button" aria-label="Clear rule filter" onClick={() => setFilters((f) => ({ ...f, rule: '' }))}>
                ×
              </button>
            </Pill>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <span className="text-sm text-fg-2">
            {visible.length} of {all.length} tests
            {selected.size > 0 ? ` · ${selected.size} selected` : ''}
          </span>
          <div className="ml-auto flex gap-2">
            <Button
              size="sm"
              disabled={!canReview}
              onClick={() => {
                const ids = visible.filter(isBulkEligible).map((test) => test.id)
                setSelected(new Set(ids))
              }}
            >
              Select engine tests in view
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={!canReview || selected.size === 0}
              title={canReview ? undefined : 'Your role cannot review tests'}
              onClick={() => setPending({ mode: 'approve', ids: [...selected], label: `${selected.size} engine test(s)` })}
            >
              Approve selected
            </Button>
          </div>
        </div>

        {tests.loading && !tests.data && (
          <div className="p-3"><SkeletonRows rows={5} /></div>
        )}
        {tests.error && (
          <div className="p-3"><ErrorState error={tests.error} onRetry={tests.reload} /></div>
        )}
        {tests.data && all.length === 0 && (
          <EmptyState
            icon={FlaskConical}
            title="No tests yet"
            description="Generate tests from the approved specification. Expected values come from the oracle, never from the AI."
            action={<Button variant="primary" onClick={() => setGenerateOpen(true)}>Generate tests</Button>}
          />
        )}
        {all.length > 0 && visible.length === 0 && (
          <p className="px-3 py-8 text-center text-sm text-fg-3">No test matches these filters.</p>
        )}
        {visible.length > 0 && (
          <TestTable
            tests={visible}
            selected={selected}
            onToggle={(id) =>
              setSelected((current) => {
                const next = new Set(current)
                if (next.has(id)) next.delete(id)
                else next.add(id)
                return next
              })
            }
            onToggleAll={(ids, on) => setSelected(on ? new Set(ids) : new Set())}
            onOpen={setOpenId}
          />
        )}
      </Panel>

      <TestDrawer
        test={opened}
        criteria={criteria}
        canReview={canReview}
        onClose={() => setOpenId(null)}
        onApprove={(test: TestRecord) => setPending({ mode: 'approve', ids: [test.id], label: test.tc_code })}
        onReject={(test: TestRecord) => setPending({ mode: 'reject', ids: [test.id], label: test.tc_code })}
        onLoadCriteria={loadCriteria}
      />

      <GenerateDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        specId={specId}
        onDone={(result) => {
          rememberCriteria(result.criteria)
          tests.reload()
        }}
      />

      {pending && (
        <ReviewDialog
          open
          mode={pending.mode}
          count={pending.ids.length}
          label={pending.label}
          onClose={() => setPending(null)}
          onConfirm={confirmReview}
        />
      )}
    </div>
  )
}

export default function TestsPage() {
  const { specId } = useParams()
  const workspace = useWorkspace()
  if (!specId) {
    return workspace.specId ? <Navigate to={`/tests/${workspace.specId}`} replace /> : <SpecPicker />
  }
  return <TestBoard key={specId} specId={specId} />
}
