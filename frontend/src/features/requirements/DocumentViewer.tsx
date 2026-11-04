import type { Policy } from '../../api/types'
import { Pill } from '../../components/ui'
import { buildSegments } from '../../lib/spans'
import type { Located } from '../../lib/spans'

function MarkedText({
  text,
  section,
  located,
  activeKey,
  unresolved,
  onSelect,
}: {
  text: string
  section: string
  located: Located[]
  activeKey: string | null
  unresolved: Set<string>
  onSelect: (ruleKey: string) => void
}) {
  const marks = located.filter((item) => item.section === section)
  const segments = buildSegments(text, marks)
  return (
    <p className="whitespace-pre-wrap text-base leading-7 text-fg">
      {segments.map((segment, position) => {
        const key = segment.ruleKey
        if (key === null) return <span key={position}>{segment.text}</span>
        const active = key === activeKey
        const tone = unresolved.has(key)
          ? active
            ? 'bg-warn/35'
            : 'bg-warn/15 hover:bg-warn/25'
          : active
            ? 'bg-prov-ai/35'
            : 'bg-prov-ai/15 hover:bg-prov-ai/25'
        return (
          <mark
            key={position}
            role="button"
            tabIndex={0}
            title={`Rule ${key}`}
            onClick={() => onSelect(key)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSelect(key)
              }
            }}
            className={`cursor-pointer rounded-sm px-0.5 text-fg ${tone}`}
          >
            {segment.text}
          </mark>
        )
      })}
    </p>
  )
}

export function DocumentViewer({
  requirementText,
  policies,
  located,
  activeKey,
  unresolved,
  onSelect,
}: {
  requirementText: string
  policies: Policy[]
  located: Located[]
  activeKey: string | null
  unresolved: Set<string>
  onSelect: (ruleKey: string) => void
}) {
  return (
    <div className="space-y-5">
      <section aria-label="Requirement text">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-fg-3">Requirement text</p>
        <MarkedText
          text={requirementText}
          section="requirement"
          located={located}
          activeKey={activeKey}
          unresolved={unresolved}
          onSelect={onSelect}
        />
      </section>
      {policies.map((policy) => (
        <section key={policy.ref} aria-label={`Policy ${policy.ref}`} className="border-t border-line pt-3">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-medium">{policy.ref}</span>
            <span className="text-xs text-fg-3">
              from {policy.effective_from}
              {policy.effective_to ? ` to ${policy.effective_to}` : ''}
            </span>
            {policy.fictional && <Pill tone="warn">fictional</Pill>}
          </div>
          <MarkedText
            text={policy.rule_text}
            section={policy.ref}
            located={located}
            activeKey={activeKey}
            unresolved={unresolved}
            onSelect={onSelect}
          />
        </section>
      ))}
    </div>
  )
}
