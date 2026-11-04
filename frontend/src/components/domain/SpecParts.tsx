/* eslint-disable react-refresh/only-export-components */
import type { PatchOp, Role, Spec } from '../../api/types'
import { formatValue } from '../../lib/format'

export const EDITOR_ROLES: Role[] = ['BUSINESS_ANALYST', 'QA_ENGINEER', 'ADMIN']

export function canEditSpec(role: Role): boolean {
  return EDITOR_ROLES.includes(role)
}

const BLOCKER_LABELS: Record<string, string> = {
  open_ambiguities: 'Open questions',
  deferred_ambiguities: 'Deferred questions (must be resolved)',
  unresolved_params: 'Unresolved parameters',
  blocking_issues: 'Blocking validation issues',
  ungrounded_rules: 'Rules whose source text has not been verified',
}

export function Blockers({ details }: { details: unknown }) {
  if (typeof details !== 'object' || details === null) return null
  const entries = Object.entries(details as Record<string, unknown>).filter(
    ([, value]) => Array.isArray(value) && value.length > 0,
  )
  return (
    <div role="alert" className="rounded-md border border-bad/40 bg-bad/10 p-3 text-sm">
      <p className="font-medium">The backend refused approval:</p>
      <ul className="mt-2 space-y-1 text-fg-2">
        {entries.map(([key, value]) => (
          <li key={key}>
            <span className="font-medium text-fg">{BLOCKER_LABELS[key] ?? key}:</span>{' '}
            {(value as string[]).join(', ')}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function GroundedMark({ value }: { value: boolean | null }) {
  if (value === true) return <span className="text-ok">✓ verified in sources</span>
  if (value === false) return <span className="text-bad">✕ not found in sources</span>
  return <span className="text-fg-3">? not checked</span>
}

export function ParamList({ params }: { params: Record<string, unknown> }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
      {Object.entries(params).map(([name, value]) => (
        <div key={name} className="contents">
          <dt className="text-fg-3">{name}</dt>
          <dd className={value === null ? 'font-medium text-bad' : 'text-fg'}>
            {value === null ? 'UNRESOLVED' : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export interface Change {
  target: string
  before: string
  after: string
}

/** Describe what a clarification patch operation would change in the current spec. */
export function describeChange(spec: Spec, op: PatchOp): Change {
  const parts = op.path.split('/') // ['', 'rules', KEY, 'params', name] | ['', 'rules', KEY, 'origin']
  const key = parts[2] ?? ''
  const rule = spec.rules.find((item) => item.rule_key === key)
  if (parts[3] === 'origin') {
    return { target: `${key}.origin`, before: formatValue(rule?.origin), after: formatValue(op.value) }
  }
  const name = parts[4] ?? ''
  return {
    target: `${key}.${name}`,
    before: formatValue(rule?.params[name]),
    after: formatValue(op.value),
  }
}
