import { Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { ApiError } from '../../api/client'
import type { Requirement } from '../../api/types'
import { Button, EmptyState, ErrorState, Panel, SkeletonRows, StatusPill, inputClass } from '../../components/ui'

export function RequirementList({
  requirements,
  loading,
  error,
  onRetry,
  selectedId,
  onNew,
}: {
  requirements: Requirement[] | null
  loading: boolean
  error: ApiError | null
  onRetry: () => void
  selectedId: string | undefined
  onNew: () => void
}) {
  const [query, setQuery] = useState('')
  const visible = (requirements ?? []).filter((requirement) =>
    `${requirement.code} ${requirement.title}`.toLowerCase().includes(query.trim().toLowerCase()),
  )

  return (
    <Panel
      title="Requirements"
      actions={
        <Button size="sm" variant="primary" onClick={onNew}>
          <Plus size={12} aria-hidden="true" />
          New
        </Button>
      }
      bodyClassName="p-2"
    >
      <div className="relative mb-2">
        <Search size={13} className="absolute left-2 top-2.5 text-fg-3" aria-hidden="true" />
        <input
          aria-label="Filter requirements"
          placeholder="Filter…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={`${inputClass} pl-7`}
        />
      </div>
      {loading && !requirements && <SkeletonRows rows={3} />}
      {error && <ErrorState error={error} onRetry={onRetry} compact />}
      {requirements && requirements.length === 0 && (
        <EmptyState
          title="No requirements yet"
          description="Create the first requirement to start the analysis."
          action={
            <Button variant="primary" onClick={onNew}>
              New requirement
            </Button>
          }
        />
      )}
      {requirements && requirements.length > 0 && visible.length === 0 && (
        <p className="px-2 py-4 text-center text-sm text-fg-3">No match for “{query}”.</p>
      )}
      <ul className="space-y-1">
        {visible.map((requirement) => (
          <li key={requirement.id}>
            <Link
              to={`/requirements/${requirement.id}`}
              aria-current={requirement.id === selectedId ? 'page' : undefined}
              className={`block rounded-md border px-2.5 py-2 hover:bg-raised ${
                requirement.id === selectedId ? 'border-accent/60 bg-raised' : 'border-transparent'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs font-medium">{requirement.code}</span>
                <StatusPill value={requirement.status} />
              </div>
              <p className="mt-0.5 truncate text-sm text-fg-2">{requirement.title}</p>
              <p className="text-xs text-fg-3">{requirement.latest_version} version(s)</p>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
