import { ShieldCheck, Sparkles, User } from 'lucide-react'
import type { ReactNode } from 'react'
import { humanize } from '../../lib/format'

export type Tone = 'neutral' | 'ok' | 'warn' | 'bad' | 'info' | 'accent'

const TONE: Record<Tone, string> = {
  neutral: 'border-line-strong bg-well text-fg-2',
  ok: 'border-ok/30 bg-ok/12 text-ok',
  warn: 'border-warn/30 bg-warn/12 text-warn',
  bad: 'border-bad/30 bg-bad/12 text-bad',
  info: 'border-info/30 bg-info/12 text-info',
  accent: 'border-accent/35 bg-accent/12 text-accent',
}

const STATUS_TONE: Record<string, Tone> = {
  DRAFT: 'neutral',
  ANALYZED: 'info',
  SPEC_APPROVED: 'ok',
  APPROVED: 'ok',
  CHANGED: 'warn',
  SUPERSEDED: 'neutral',
  OPEN: 'warn',
  RESOLVED: 'ok',
  DEFERRED: 'accent',
  BLOCK: 'bad',
  WARN: 'warn',
  POLICY: 'info',
  EXPLICIT: 'info',
  CLARIFIED: 'ok',
  ASSUMED: 'warn',
  NEEDS_CLARIFICATION: 'bad',
  BLOCKED: 'bad',
  REJECTED: 'bad',
  COMPLETED: 'ok',
  FAILED: 'bad',
  STALE: 'warn',
  OBSOLETE: 'neutral',
  STALE_EXPECTED: 'warn',
  NEW: 'info',
  UNAFFECTED: 'neutral',
  ADDED: 'ok',
  REMOVED: 'bad',
  PARAM_CHANGED: 'warn',
  POLICY_VERSION_CHANGED: 'info',
  PASS: 'ok',
  FAIL: 'bad',
  ERROR: 'warn',
  FIXED: 'info',
  VERIFIED: 'ok',
}

export function Pill({
  tone = 'neutral',
  children,
  className = '',
}: {
  tone?: Tone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-xs font-medium ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

export function StatusPill({ value }: { value: string }) {
  return <Pill tone={STATUS_TONE[value] ?? 'neutral'}>{humanize(value)}</Pill>
}

type Provenance = 'ai' | 'oracle' | 'human'

const PROVENANCE = {
  ai: {
    icon: Sparkles,
    label: 'AI',
    style: 'border-prov-ai/40 bg-prov-ai/10 text-prov-ai',
    hint: 'Drafted by the AI provider. Advisory until a person approves it.',
  },
  oracle: {
    icon: ShieldCheck,
    label: 'Oracle',
    style: 'border-prov-oracle/40 bg-prov-oracle/10 text-prov-oracle',
    hint: 'Computed by the deterministic oracle from the approved specification.',
  },
  human: {
    icon: User,
    label: 'Human',
    style: 'border-prov-human/40 bg-prov-human/10 text-prov-human',
    hint: 'Decided or approved by a person.',
  },
} as const

export function ProvenanceBadge({ source, label }: { source: Provenance; label?: string }) {
  const config = PROVENANCE[source]
  const Icon = config.icon
  return (
    <span
      title={config.hint}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-xs font-medium ${config.style}`}
    >
      <Icon size={11} aria-hidden="true" />
      {label ?? config.label}
    </span>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line-strong bg-well px-1 font-mono text-[10px] text-fg-3">
      {children}
    </kbd>
  )
}
