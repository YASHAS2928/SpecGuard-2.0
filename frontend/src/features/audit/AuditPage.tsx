import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listAuditEvents } from '../../api/audit'
import type { AuditRecord } from '../../api/audit'
import {
  Button,
  Drawer,
  EmptyState,
  ErrorState,
  Panel,
  Pill,
  ProvenanceBadge,
  SkeletonRows,
  inputClass,
  useToast,
} from '../../components/ui'
import { useLoad } from '../../hooks'
import { formatDateTime, humanize } from '../../lib/format'

const PAGE = 25

const ENTITY_TYPES = [
  'REQUIREMENT',
  'REQUIREMENT_VERSION',
  'SPEC',
  'RULE',
  'AMBIGUITY',
  'CRITERION',
  'TEST_CASE',
  'RUN',
  'RESULT',
  'DEFECT',
  'CHANGE_IMPACT',
]
const ACTIONS = [
  'REQUIREMENT_CREATED',
  'REQUIREMENT_VERSION_CREATED',
  'REQUIREMENT_ANALYZED',
  'AMBIGUITY_RESOLVED',
  'AMBIGUITY_DEFERRED',
  'SPEC_APPROVED',
  'SPEC_SUPERSEDED',
  'TESTS_DESIGNED',
  'TEST_APPROVED',
  'TEST_REJECTED',
  'RUN_EXECUTED',
  'DEFECT_UPDATED',
  'CHANGE_IMPACT_ANALYZED',
]

function entityLink(event: AuditRecord): string | null {
  if (event.entity_type === 'REQUIREMENT') return `/requirements/${event.entity_id}`
  if (event.entity_type === 'SPEC') return `/clarification/${event.entity_id}`
  if (event.entity_type === 'RUN') return `/runs/${event.entity_id}`
  if (event.entity_type === 'CHANGE_IMPACT' && typeof event.detail?.to_spec_id === 'string') {
    return `/impact/${event.detail.to_spec_id}`
  }
  return null
}

function dayLabel(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function Hash({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-wider text-fg-3">{label}</dt>
      <dd className="mt-0.5 break-all font-mono text-xs">{value ?? '—'}</dd>
    </div>
  )
}

function EventDrawer({ event, onClose }: { event: AuditRecord | null; onClose: () => void }) {
  const toast = useToast()
  if (!event) return null
  const link = entityLink(event)
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.push({ tone: 'ok', title: 'Copied' })
    } catch {
      toast.push({ tone: 'warn', title: 'Copy is not available in this browser' })
    }
  }
  return (
    <Drawer open onClose={onClose} title={humanize(event.action)} description={formatDateTime(event.ts)}>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-[10px] font-medium uppercase tracking-wider text-fg-3">Actor</dt>
          <dd>{event.actor}</dd>
        </div>
        <div>
          <dt className="text-[10px] font-medium uppercase tracking-wider text-fg-3">Role</dt>
          <dd>{humanize(event.actor_role)}</dd>
        </div>
        <div>
          <dt className="text-[10px] font-medium uppercase tracking-wider text-fg-3">Entity</dt>
          <dd>{humanize(event.entity_type)}</dd>
        </div>
        <div>
          <dt className="text-[10px] font-medium uppercase tracking-wider text-fg-3">Entity id</dt>
          <dd className="break-all font-mono text-xs">{event.entity_id}</dd>
        </div>
      </dl>
      {link && (
        <Link to={link} className="text-sm text-accent underline">
          Open this {humanize(event.entity_type).toLowerCase()}
        </Link>
      )}
      <section>
        <h3 className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-3">Integrity</h3>
        <dl className="space-y-2">
          <Hash label="Hash before" value={event.before_hash} />
          <Hash label="Hash after" value={event.after_hash} />
        </dl>
        <p className="mt-1 text-xs text-fg-3">
          SHA-256 of the entity state before and after the action. Events are append-only.
        </p>
      </section>
      <section>
        <h3 className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-3">Trace</h3>
        <div className="flex items-center gap-2">
          <span className="break-all font-mono text-xs">{event.trace_id ?? '—'}</span>
          {event.trace_id && (
            <Button size="sm" onClick={() => copy(event.trace_id ?? '')}>
              Copy
            </Button>
          )}
        </div>
      </section>
      <section>
        <h3 className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-fg-3">Detail</h3>
        <pre className="overflow-x-auto rounded-md border border-line bg-well p-3 font-mono text-xs">
          {event.detail ? JSON.stringify(event.detail, null, 2) : 'No detail recorded.'}
        </pre>
      </section>
    </Drawer>
  )
}

export default function AuditPage() {
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const [actorFilter, setActorFilter] = useState('')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [openId, setOpenId] = useState<string | null>(null)

  const events = useLoad(
    () => listAuditEvents({ entity_type: entityType, action, limit: PAGE, offset }),
    `audit:${entityType}:${action}:${offset}`,
  )

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return (events.data?.items ?? []).filter(
      (event) =>
        (!actorFilter || event.actor.toLowerCase().includes(actorFilter.toLowerCase())) &&
        (!needle ||
          `${event.actor} ${event.action} ${event.entity_type} ${event.entity_id} ${event.trace_id ?? ''}`
            .toLowerCase()
            .includes(needle)),
    )
  }, [events.data, actorFilter, query])

  const groups = useMemo(() => {
    const map = new Map<string, AuditRecord[]>()
    for (const event of shown) {
      const key = dayLabel(event.ts)
      map.set(key, [...(map.get(key) ?? []), event])
    }
    return Array.from(map.entries())
  }, [shown])

  const total = events.data?.total ?? 0
  const opened = shown.find((event) => event.id === openId) ?? null
  const clientFiltered = actorFilter !== '' || query !== ''

  function resetPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setOffset(0)
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-xl font-semibold">Audit history</h2>
        <span className="text-xs text-fg-3">
          Append-only. Every decision records who, when, what and a hash of the state before and after.
        </span>
      </div>

      <Panel bodyClassName="p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-48 flex-1">
            <Search size={13} className="absolute left-2 top-2.5 text-fg-3" aria-hidden="true" />
            <input
              aria-label="Search the loaded events"
              placeholder="Search actor, action, entity id, trace…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className={`${inputClass} pl-7`}
            />
          </div>
          <input
            aria-label="Filter by actor"
            placeholder="Actor"
            value={actorFilter}
            onChange={(event) => setActorFilter(event.target.value)}
            className={`${inputClass} w-32`}
          />
          <select
            aria-label="Entity type"
            className={`${inputClass} w-auto`}
            value={entityType}
            onChange={(event) => resetPage(setEntityType)(event.target.value)}
          >
            <option value="">All entities</option>
            {ENTITY_TYPES.map((name) => (
              <option key={name} value={name}>
                {humanize(name)}
              </option>
            ))}
          </select>
          <select
            aria-label="Action"
            className={`${inputClass} w-auto`}
            value={action}
            onChange={(event) => resetPage(setAction)(event.target.value)}
          >
            <option value="">All actions</option>
            {ACTIONS.map((name) => (
              <option key={name} value={name}>
                {humanize(name)}
              </option>
            ))}
          </select>
          {(entityType || action || actorFilter || query) && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEntityType('')
                setAction('')
                setActorFilter('')
                setQuery('')
                setOffset(0)
              }}
            >
              Clear filters
            </Button>
          )}
        </div>
        {clientFiltered && (
          <p className="mt-2 text-xs text-fg-3">
            Actor and search filters only apply to the {events.data?.items.length ?? 0} events on this page.
          </p>
        )}
      </Panel>

      {events.loading && !events.data && <SkeletonRows rows={6} />}
      {events.error && <ErrorState error={events.error} onRetry={events.reload} />}
      {events.data && groups.length === 0 && (
        <Panel>
          <EmptyState
            title="No events"
            description={total === 0 ? 'Nothing has been recorded yet.' : 'No event on this page matches the filters.'}
          />
        </Panel>
      )}

      {groups.map(([day, list]) => (
        <section key={day} aria-label={day}>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-fg-3">{day}</h3>
          <ol className="space-y-1 border-l border-line pl-4">
            {list.map((event) => (
              <li key={event.id} className="relative">
                <span
                  className="absolute -left-[1.3rem] top-3 h-2 w-2 rounded-full border border-line-strong bg-surface"
                  aria-hidden="true"
                />
                <button
                  type="button"
                  onClick={() => setOpenId(event.id)}
                  className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-transparent px-3 py-2 text-left hover:border-line hover:bg-raised"
                >
                  <span className="w-14 font-mono text-xs text-fg-3">
                    {new Date(event.ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <ProvenanceBadge source={event.actor_role === 'SYSTEM' ? 'oracle' : 'human'} label={humanize(event.action)} />
                  <span className="text-sm">{event.actor}</span>
                  <Pill>{humanize(event.entity_type)}</Pill>
                  {event.trace_id && (
                    <span className="ml-auto font-mono text-[11px] text-fg-3">
                      trace {event.trace_id.slice(0, 8)}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ol>
        </section>
      ))}

      {total > 0 && (
        <div className="flex items-center justify-between text-sm text-fg-2">
          <span>
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Newer
            </Button>
            <Button size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
              Older
            </Button>
          </div>
        </div>
      )}

      <EventDrawer event={opened} onClose={() => setOpenId(null)} />
    </div>
  )
}
