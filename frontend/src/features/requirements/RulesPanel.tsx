import { Link } from 'react-router-dom'
import type { Spec } from '../../api/types'
import { GroundedMark, ParamList } from '../../components/domain/SpecParts'
import { Panel, Pill, ProvenanceBadge, StatusPill } from '../../components/ui'
import type { Located } from '../../lib/spans'

export function RulesPanel({
  spec,
  located,
  activeKey,
  onSelect,
  versionNumber,
}: {
  spec: Spec
  located: Located[]
  activeKey: string | null
  onSelect: (ruleKey: string) => void
  versionNumber: number
}) {
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          Extracted rules <ProvenanceBadge source="ai" label="AI-extracted" />
        </span>
      }
      bodyClassName="space-y-2 p-2"
    >
      {spec.rules.map((rule) => {
        const place = located.find((item) => item.ruleKey === rule.rule_key)
        const active = rule.rule_key === activeKey
        const needsClarification = rule.unresolved_params.length > 0
        return (
          <article
            key={rule.id}
            className={`rounded-md border ${active ? 'border-accent/60 bg-raised' : 'border-line'}`}
          >
            <button
              type="button"
              onClick={() => onSelect(rule.rule_key)}
              aria-pressed={active}
              className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left"
            >
              <span className="font-mono text-sm font-medium">{rule.rule_key}</span>
              <Pill>{rule.type}</Pill>
              {rule.origin === 'CLARIFIED' ? (
                <ProvenanceBadge source="human" label="Clarified" />
              ) : (
                <StatusPill value={rule.origin} />
              )}
              {needsClarification && <Pill tone="warn">needs clarification</Pill>}
            </button>
            <div className="space-y-2 border-t border-line px-3 py-2">
              <ParamList params={rule.params} />
              <blockquote className="border-l-2 border-prov-ai/60 pl-2 text-xs italic text-fg-2">
                “{rule.source_span}”
              </blockquote>
              <p className="flex flex-wrap items-center gap-x-3 text-xs">
                <GroundedMark value={rule.grounded} />
                <span className="text-fg-3">
                  {place
                    ? `found in ${place.section === 'requirement' ? 'requirement text' : place.section}`
                    : 'not located in the displayed sources'}
                </span>
              </p>
              <p className="font-mono text-[11px] text-fg-3" aria-label="Trace">
                v{versionNumber} › {rule.policy_ref ?? 'requirement text'} › {rule.rule_key}
              </p>
            </div>
          </article>
        )
      })}
      {spec.rules.length === 0 && <p className="px-2 py-4 text-center text-sm text-fg-3">No rules extracted.</p>}
      {spec.open_ambiguities > 0 && (
        <p className="px-1 pt-1 text-xs text-fg-2">
          {spec.open_ambiguities} open question(s).{' '}
          <Link to={`/clarification/${spec.id}`} className="text-accent underline">
            Resolve in Clarification
          </Link>
        </p>
      )}
    </Panel>
  )
}
