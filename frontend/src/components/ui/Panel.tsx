import type { KeyboardEvent, ReactNode } from 'react'

export function Panel({
  title,
  actions,
  children,
  className = '',
  bodyClassName = 'p-3',
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={`rounded-lg border border-line bg-surface ${className}`}>
      {(title || actions) && (
        <header className="flex min-h-10 items-center justify-between gap-2 border-b border-line px-3 py-2">
          <h2 className="text-xs font-medium uppercase tracking-wide text-fg-3">{title}</h2>
          {actions}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}

export interface TabItem {
  id: string
  label: string
  count?: number
}

export function Tabs({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem[]
  value: string
  onChange: (id: string) => void
  label: string
}) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    const current = items.findIndex((item) => item.id === value)
    const step = event.key === 'ArrowRight' ? 1 : -1
    const next = (current + step + items.length) % items.length
    const target = items[next]
    if (!target) return
    event.preventDefault()
    onChange(target.id)
    event.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus()
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className="flex gap-1 border-b border-line"
    >
      {items.map((item) => {
        const selected = item.id === value
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              selected
                ? 'border-accent text-fg'
                : 'border-transparent text-fg-3 hover:text-fg-2'
            }`}
          >
            {item.label}
            {item.count !== undefined && (
              <span className="rounded bg-well px-1 text-xs tabular-nums text-fg-2">{item.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
