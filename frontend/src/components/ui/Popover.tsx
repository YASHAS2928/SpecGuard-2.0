import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export function Popover({
  button,
  label,
  children,
  align = 'left',
  className = '',
  buttonClassName = '',
}: {
  button: ReactNode
  label: string
  children: (close: () => void) => ReactNode
  align?: 'left' | 'right'
  className?: string
  buttonClassName?: string
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onMouseDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((current) => !current)}
        className={buttonClassName}
      >
        {button}
      </button>
      {open && (
        <div
          className={`anim-pop absolute top-full z-40 mt-1 min-w-52 rounded-lg border border-line-strong bg-surface p-1 shadow-float ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

export function MenuItem({
  children,
  onSelect,
  active = false,
  disabled = false,
}: {
  children: ReactNode
  onSelect: () => void
  active?: boolean
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-raised disabled:opacity-50 ${
        active ? 'text-fg' : 'text-fg-2'
      }`}
    >
      {children}
    </button>
  )
}

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-40 mt-1 -translate-x-1/2 whitespace-nowrap rounded-md border border-line-strong bg-raised px-2 py-1 text-xs text-fg opacity-0 shadow-float transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  )
}
