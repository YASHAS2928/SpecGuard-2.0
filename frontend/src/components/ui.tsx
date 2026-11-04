import type { ReactNode } from 'react'
import type { ApiError } from '../api/client'

export const inputClass =
  'w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none'

const BADGE: Record<string, string> = {
  DRAFT: 'bg-slate-100 text-slate-700',
  ANALYZED: 'bg-blue-100 text-blue-800',
  SPEC_APPROVED: 'bg-green-100 text-green-800',
  APPROVED: 'bg-green-100 text-green-800',
  CHANGED: 'bg-amber-100 text-amber-800',
  SUPERSEDED: 'bg-slate-200 text-slate-600',
  OPEN: 'bg-amber-100 text-amber-800',
  RESOLVED: 'bg-green-100 text-green-800',
  DEFERRED: 'bg-purple-100 text-purple-800',
  BLOCK: 'bg-red-100 text-red-800',
  WARN: 'bg-amber-100 text-amber-800',
  POLICY: 'bg-indigo-100 text-indigo-800',
  EXPLICIT: 'bg-indigo-100 text-indigo-800',
  CLARIFIED: 'bg-green-100 text-green-800',
  ASSUMED: 'bg-amber-100 text-amber-800',
  NEEDS_CLARIFICATION: 'bg-red-100 text-red-800',
}

export function Badge({ value }: { value: string }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${BADGE[value] ?? 'bg-slate-100 text-slate-700'}`}
    >
      {value}
    </span>
  )
}

export function Button({
  children,
  onClick,
  disabled,
  variant = 'primary',
  type = 'button',
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'primary' | 'secondary' | 'danger'
  type?: 'button' | 'submit'
}) {
  const styles = {
    primary: 'bg-indigo-600 text-white hover:bg-indigo-700',
    secondary: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
    danger: 'bg-red-600 text-white hover:bg-red-700',
  }[variant]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}
    >
      {children}
    </button>
  )
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      {title && <h2 className="mb-3 text-base font-semibold">{title}</h2>}
      {children}
    </section>
  )
}

export function Loading() {
  return <p className="text-sm text-slate-500">Loading…</p>
}

export function ErrorBox({ error }: { error: ApiError | null }) {
  if (!error) return null
  const hasDetails = error.details !== null && error.details !== undefined
  return (
    <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900">
      <p className="font-medium">{error.message}</p>
      <p className="mt-1 text-xs text-red-700">
        {error.code}
        {error.traceId ? ` · trace ${error.traceId}` : ''}
      </p>
      {hasDetails && (
        <pre className="mt-2 overflow-x-auto rounded bg-white p-2 text-xs text-slate-700">
          {JSON.stringify(error.details, null, 2)}
        </pre>
      )}
    </div>
  )
}
