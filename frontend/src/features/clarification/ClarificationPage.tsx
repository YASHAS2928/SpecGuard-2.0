import { Check, ChevronDown, MessagesSquare } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import { loadSpecIndex } from '../../api/adapters'
import { useWorkspace } from '../../app/workspace'
import { ApproveSpecDialog } from '../../components/domain/ApproveSpecDialog'
import {
  Button,
  EmptyState,
  ErrorState,
  MenuItem,
  Panel,
  Popover,
  Skeleton,
  SkeletonRows,
  StatusPill,
  Tabs,
} from '../../components/ui'
import { useLoad } from '../../hooks'
import { AmbiguityDetail } from './AmbiguityDetail'

function SpecPicker() {
  const index = useLoad(() => loadSpecIndex(), 'spec-index')
  return (
    <div className="mx-auto max-w-2xl">
      <Panel title="Choose a specification">
        {index.loading && !index.data && <SkeletonRows rows={3} />}
        {index.error && <ErrorState error={index.error} onRetry={index.reload} />}
        {index.data && index.data.length === 0 && (
          <EmptyState
            icon={MessagesSquare}
            title="No specification to clarify yet"
            description="Analyse a requirement version first. The AI's questions appear here."
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
                to={`/clarification/${item.spec.id}`}
                className="flex items-center gap-2 rounded-md border border-line px-3 py-2 hover:bg-raised"
              >
                <span className="font-mono text-xs font-medium">{item.requirement.code}</span>
                <span className="text-sm text-fg-2">spec v{item.spec.version}</span>
                <span className="ml-auto flex items-center gap-2">
                  <span className="text-xs text-fg-3">{item.spec.open_ambiguities} open</span>
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

function ClarificationBoard({ specId }: { specId: string }) {
  const { setActive } = useWorkspace()
  const spec = useLoad(() => api.getSpec(specId), `spec:${specId}`)
  const index = useLoad(() => loadSpecIndex(), 'spec-index')
  const [filter, setFilter] = useState('todo')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [approveOpen, setApproveOpen] = useState(false)

  const owner = index.data?.find((item) => item.spec.id === specId)
  const ownerRequirementId = owner?.requirement.id
  const ownerCode = owner?.requirement.code
  const specVersion = spec.data?.version

  useEffect(() => {
    if (ownerRequirementId && ownerCode && specVersion !== undefined) {
      setActive({
        requirementId: ownerRequirementId,
        requirementCode: ownerCode,
        specId,
        specVersion,
      })
    }
  }, [ownerRequirementId, ownerCode, specVersion, specId, setActive])

  if (spec.error) return <ErrorState error={spec.error} onRetry={spec.reload} />
  if (!spec.data) return <Skeleton className="h-64 w-full" />

  const data = spec.data
  const todo = data.ambiguities.filter((item) => item.status !== 'RESOLVED')
  const done = data.ambiguities.filter((item) => item.status === 'RESOLVED')
  const shown = filter === 'todo' ? todo : filter === 'resolved' ? done : data.ambiguities
  const selected =
    data.ambiguities.find((item) => item.id === selectedId) ?? todo[0] ?? data.ambiguities[0] ?? null
  const total = data.ambiguities.length

  return (
    <div className="mx-auto max-w-[1500px] space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">
          <span className="font-mono">{ownerCode ?? 'Specification'}</span>
          <span className="ml-2 text-fg-2">v{data.version}</span>
        </h2>
        <StatusPill value={data.status} />
        <Popover
          label="Switch specification"
          buttonClassName="inline-flex h-8 items-center gap-2 rounded-md border border-line-strong bg-raised px-3 text-sm hover:bg-well"
          button={
            <>
              Switch spec
              <ChevronDown size={13} aria-hidden="true" />
            </>
          }
        >
          {(close) =>
            (index.data ?? []).map((item) => (
              <Link key={item.spec.id} to={`/clarification/${item.spec.id}`} onClick={close}>
                <MenuItem active={item.spec.id === specId} onSelect={() => undefined}>
                  <span className="w-4">{item.spec.id === specId && <Check size={13} />}</span>
                  <span className="font-mono text-xs">{item.requirement.code}</span> v{item.spec.version}
                </MenuItem>
              </Link>
            ))
          }
        </Popover>
        <div className="ml-auto flex items-center gap-3">
          {ownerRequirementId && (
            <Link to={`/requirements/${ownerRequirementId}`} className="text-sm text-accent underline">
              Open in workspace
            </Link>
          )}
          {data.status === 'DRAFT' && (
            <Button variant="primary" onClick={() => setApproveOpen(true)}>
              Approve specification
            </Button>
          )}
        </div>
      </div>

      <div className="rounded-md border border-line bg-surface p-3">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium">
            {done.length} of {total} questions resolved
          </span>
          <span className="text-fg-3">{todo.length} still need a decision</span>
        </div>
        <div className="mt-2 flex h-1.5 overflow-hidden rounded bg-well" role="img" aria-label={`${done.length} of ${total} resolved`}>
          <div className="bg-ok" style={{ width: total ? `${(done.length / total) * 100}%` : '0%' }} />
        </div>
      </div>

      {total === 0 ? (
        <Panel>
          <EmptyState
            title="The AI found no ambiguities"
            description="You can approve the specification once its rules are verified."
          />
        </Panel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[20rem_minmax(0,1fr)]">
          <Panel bodyClassName="p-0">
            <div className="px-3 pt-1">
              <Tabs
                label="Question filter"
                value={filter}
                onChange={setFilter}
                items={[
                  { id: 'todo', label: 'To decide', count: todo.length },
                  { id: 'resolved', label: 'Resolved', count: done.length },
                  { id: 'all', label: 'All', count: total },
                ]}
              />
            </div>
            <ul className="space-y-1 p-2">
              {shown.length === 0 && <li className="px-2 py-6 text-center text-sm text-fg-3">Nothing here.</li>}
              {shown.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    aria-current={selected?.id === item.id}
                    className={`w-full rounded-md border px-3 py-2 text-left hover:bg-raised ${
                      selected?.id === item.id ? 'border-accent/60 bg-raised' : 'border-transparent'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-medium">{item.amb_code}</span>
                      <StatusPill value={item.status} />
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-sm text-fg-2">{item.question}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-fg-3">{item.affects_rules.join(', ')}</p>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
          <div className="min-w-0">
            {selected && (
              <AmbiguityDetail
                key={selected.id}
                spec={data}
                ambiguity={selected}
                onSpecChanged={(updated) => spec.setData(updated)}
              />
            )}
          </div>
        </div>
      )}

      <ApproveSpecDialog
        open={approveOpen}
        onClose={() => setApproveOpen(false)}
        spec={data}
        onApproved={(approved) => spec.setData(approved)}
      />
    </div>
  )
}

export default function ClarificationPage() {
  const { specId } = useParams()
  const workspace = useWorkspace()
  if (!specId) {
    return workspace.specId ? <Navigate to={`/clarification/${workspace.specId}`} replace /> : <SpecPicker />
  }
  return <ClarificationBoard key={specId} specId={specId} />
}
