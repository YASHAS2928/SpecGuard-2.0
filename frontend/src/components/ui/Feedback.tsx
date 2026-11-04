import { AlertTriangle, RefreshCw } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ApiError } from '../../api/client'
import { Button } from './Button'

export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-md bg-well ${className}`} />
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      {Icon && <Icon size={22} className="text-fg-3" aria-hidden="true" />}
      <p className="text-base font-medium">{title}</p>
      {description && <p className="max-w-md text-sm text-fg-2">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function ErrorState({
  error,
  onRetry,
  compact = false,
}: {
  error: ApiError
  onRetry?: () => void
  compact?: boolean
}) {
  return (
    <div
      role="alert"
      className={`rounded-md border border-bad/40 bg-bad/10 text-sm ${compact ? 'p-3' : 'p-4'}`}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-bad" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-fg">{error.message}</p>
          <p className="mt-0.5 font-mono text-xs text-fg-2">
            {error.code}
            {error.traceId ? ` · trace ${error.traceId}` : ''}
          </p>
        </div>
        {onRetry && (
          <Button size="sm" onClick={onRetry}>
            <RefreshCw size={12} aria-hidden="true" />
            Retry
          </Button>
        )}
      </div>
    </div>
  )
}

export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'ok' | 'ai'
  title?: string
  children?: ReactNode
}) {
  const style = {
    info: 'border-info/30 bg-info/10',
    warn: 'border-warn/30 bg-warn/10',
    ok: 'border-ok/30 bg-ok/10',
    ai: 'border-prov-ai/30 bg-prov-ai/10',
  }[tone]
  return (
    <div className={`rounded-md border px-3 py-2 text-sm ${style}`}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className="text-fg-2">{children}</div>}
    </div>
  )
}
