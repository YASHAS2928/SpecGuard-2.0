import { Check, ChevronDown, FilePlus, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { AnalysisMetadata, AnalyzeResponse, Policy, Requirement, Spec } from '../../api/types'
import { useWorkspace } from '../../app/workspace'
import { AnalysisBanner } from '../../components/domain/AnalysisBanner'
import { ApproveSpecDialog } from '../../components/domain/ApproveSpecDialog'
import {
  Button,
  EmptyState,
  ErrorState,
  MenuItem,
  Panel,
  Pill,
  Popover,
  Skeleton,
  StatusPill,
  Tabs,
} from '../../components/ui'
import { useLoad } from '../../hooks'
import { formatDateTime } from '../../lib/format'
import { locateRules } from '../../lib/spans'
import { AnalyseDialog, NewVersionDialog } from './RequirementDialogs'
import { DocumentViewer } from './DocumentViewer'
import { RulesPanel } from './RulesPanel'

function defaultSpec(specs: Spec[]): Spec | null {
  const live = [...specs].reverse().find((spec) => spec.status !== 'SUPERSEDED')
  return live ?? specs[specs.length - 1] ?? null
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'ok' | 'warn' | 'bad' }) {
  const color = tone === 'ok' ? 'text-ok' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-bad' : 'text-fg'
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2">
      <p className="text-[10px] font-medium uppercase tracking-wider text-fg-3">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${color}`}>{value}</p>
    </div>
  )
}

export function RequirementWorkspace({
  requirement,
  policies,
  onChanged,
}: {
  requirement: Requirement
  policies: Policy[]
  onChanged: () => void
}) {
  const { setActive } = useWorkspace()
  const versions = requirement.versions
  const latest = versions[versions.length - 1]
  const [versionId, setVersionId] = useState(latest?.id ?? '')
  const version = versions.find((item) => item.id === versionId) ?? latest
  const specs = useLoad(() => api.listSpecs(version?.id ?? ''), `specs:${version?.id ?? 'none'}`)
  const [pickedSpecId, setPickedSpecId] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<AnalysisMetadata | null>(null)
  const [tab, setTab] = useState('document')
  const [activeRule, setActiveRule] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'analyse' | 'version' | 'approve' | null>(null)

  const specList = specs.data ?? []
  const spec = specList.find((item) => item.id === pickedSpecId) ?? defaultSpec(specList)
  const specId = spec?.id ?? null
  const specVersion = spec?.version ?? null

  useEffect(() => {
    if (specId && specVersion !== null) {
      setActive({
        requirementId: requirement.id,
        requirementCode: requirement.code,
        specId,
        specVersion,
      })
    }
  }, [specId, specVersion, requirement.id, requirement.code, setActive])

  const attached = useMemo(
    () =>
      (version?.policy_ids ?? [])
        .map((ref) => policies.find((policy) => policy.ref === ref))
        .filter((policy): policy is Policy => policy !== undefined),
    [version, policies],
  )

  const located = useMemo(() => {
    if (!spec || !version) return []
    const policyText: Record<string, string> = {}
    for (const policy of attached) policyText[policy.ref] = policy.rule_text
    return locateRules(spec.rules, version.text, policyText)
  }, [spec, version, attached])

  const unresolved = useMemo(
    () => new Set((spec?.rules ?? []).filter((rule) => rule.unresolved_params.length > 0).map((rule) => rule.rule_key)),
    [spec],
  )

  if (!version) return <EmptyState title="This requirement has no versions." />

  function selectVersion(id: string) {
    setVersionId(id)
    setPickedSpecId(null)
    setAnalysis(null)
    setActiveRule(null)
  }

  function onAnalysed(result: AnalyzeResponse) {
    setAnalysis(result.analysis)
    setPickedSpecId(result.spec.id)
    specs.setData([...(specs.data ?? []).filter((item) => item.id !== result.spec.id), result.spec])
    specs.reload()
    onChanged()
  }

  const groundedCount = spec ? spec.rules.filter((rule) => rule.grounded === true).length : 0
  const isLatest = version.id === latest?.id

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="text-xl font-semibold">
          <span className="font-mono">{requirement.code}</span>
          <span className="ml-2 text-fg-2">{requirement.title}</span>
        </h2>
        <StatusPill value={requirement.status} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Popover
          label="Select version"
          buttonClassName="inline-flex h-8 items-center gap-2 rounded-md border border-line-strong bg-raised px-3 text-sm hover:bg-well"
          button={
            <>
              Version {version.version}
              {isLatest && <Pill tone="info">latest</Pill>}
              <ChevronDown size={13} aria-hidden="true" />
            </>
          }
        >
          {(close) =>
            [...versions].reverse().map((item) => (
              <MenuItem
                key={item.id}
                active={item.id === version.id}
                onSelect={() => {
                  selectVersion(item.id)
                  close()
                }}
              >
                <span className="w-4">{item.id === version.id && <Check size={13} />}</span>
                Version {item.version}
                <span className="ml-auto text-xs text-fg-3">{formatDateTime(item.created_at)}</span>
              </MenuItem>
            ))
          }
        </Popover>

        {specList.length > 1 && spec && (
          <Popover
            label="Select specification"
            buttonClassName="inline-flex h-8 items-center gap-2 rounded-md border border-line-strong bg-raised px-3 text-sm hover:bg-well"
            button={
              <>
                Spec v{spec.version}
                <ChevronDown size={13} aria-hidden="true" />
              </>
            }
          >
            {(close) =>
              [...specList].reverse().map((item) => (
                <MenuItem
                  key={item.id}
                  active={item.id === spec.id}
                  onSelect={() => {
                    setPickedSpecId(item.id)
                    setAnalysis(null)
                    close()
                  }}
                >
                  <span className="w-4">{item.id === spec.id && <Check size={13} />}</span>
                  Spec v{item.version}
                  <span className="ml-auto">
                    <StatusPill value={item.status} />
                  </span>
                </MenuItem>
              ))
            }
          </Popover>
        )}

        <div className="ml-auto flex flex-wrap gap-2">
          <Button onClick={() => setDialog('version')}>
            <FilePlus size={14} aria-hidden="true" />
            New version
          </Button>
          <Button onClick={() => setDialog('analyse')} variant={spec ? 'secondary' : 'primary'}>
            <Sparkles size={14} aria-hidden="true" />
            {spec ? 'Re-analyse' : 'Analyse'}
          </Button>
          {spec && spec.status === 'DRAFT' && (
            <Button variant="primary" onClick={() => setDialog('approve')}>
              Approve specification
            </Button>
          )}
        </div>
      </div>

      {analysis && <AnalysisBanner analysis={analysis} />}

      {spec && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat
            label="Rules verified"
            value={`${groundedCount} / ${spec.rules.length}`}
            tone={groundedCount === spec.rules.length && spec.rules.length > 0 ? 'ok' : 'warn'}
          />
          <Stat
            label="Open questions"
            value={String(spec.open_ambiguities)}
            tone={spec.open_ambiguities === 0 ? 'ok' : 'warn'}
          />
          <Stat
            label="Blocking issues"
            value={String(spec.blocking_issue_count)}
            tone={spec.blocking_issue_count === 0 ? 'ok' : 'bad'}
          />
          <div className="rounded-md border border-line bg-surface px-3 py-2">
            <p className="text-[10px] font-medium uppercase tracking-wider text-fg-3">Specification</p>
            <div className="mt-1.5 flex items-center gap-2">
              <StatusPill value={spec.status} />
              {spec.approved_by && <span className="truncate text-xs text-fg-2">by {spec.approved_by}</span>}
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel bodyClassName="p-0">
          <div className="px-3 pt-1">
            <Tabs
              label="Requirement views"
              value={tab}
              onChange={setTab}
              items={[
                { id: 'document', label: 'Document' },
                { id: 'versions', label: 'Versions', count: versions.length },
              ]}
            />
          </div>
          <div className="p-4">
            {tab === 'document' && (
              <>
                <p className="mb-3 text-xs text-fg-3">
                  Version {version.version} by {version.author} · {formatDateTime(version.created_at)}
                  {version.change_note ? ` · “${version.change_note}”` : ''}
                </p>
                <DocumentViewer
                  requirementText={version.text}
                  policies={attached}
                  located={located}
                  activeKey={activeRule}
                  unresolved={unresolved}
                  onSelect={setActiveRule}
                />
              </>
            )}
            {tab === 'versions' && (
              <ul className="space-y-2">
                {[...versions].reverse().map((item) => (
                  <li key={item.id} className="rounded-md border border-line p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">Version {item.version}</span>
                      {item.id === latest?.id && <Pill tone="info">latest</Pill>}
                      <span className="text-xs text-fg-3">
                        {item.author} · {formatDateTime(item.created_at)}
                      </span>
                      <div className="ml-auto flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => {
                            selectVersion(item.id)
                            setTab('document')
                          }}
                        >
                          View
                        </Button>
                        <Button size="sm" variant="ghost" disabled title="Visual diff arrives with the Change Impact screen">
                          Compare
                        </Button>
                      </div>
                    </div>
                    {item.change_note && <p className="mt-1 text-sm text-fg-2">“{item.change_note}”</p>}
                    <p className="mt-1 font-mono text-xs text-fg-3">{item.policy_ids.join(', ')}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>

        <div className="space-y-4">
          {specs.loading && !specs.data && <Skeleton className="h-48 w-full" />}
          {specs.error && <ErrorState error={specs.error} onRetry={specs.reload} />}
          {specs.data && !spec && (
            <Panel>
              <EmptyState
                icon={Sparkles}
                title="Not analysed yet"
                description="Run the analysis to extract rules, source evidence and clarification questions."
                action={
                  <Button variant="primary" onClick={() => setDialog('analyse')}>
                    Analyse version {version.version}
                  </Button>
                }
              />
            </Panel>
          )}
          {spec && (
            <RulesPanel
              spec={spec}
              located={located}
              activeKey={activeRule}
              onSelect={setActiveRule}
              versionNumber={version.version}
            />
          )}
          {spec && spec.ambiguities.length > 0 && (
            <p className="text-xs text-fg-3">
              Questions and interpretations live in{' '}
              <Link to={`/clarification/${spec.id}`} className="text-accent underline">
                Clarification
              </Link>
              . Tests that cover these rules appear in Test review (next batch).
            </p>
          )}
        </div>
      </div>

      <AnalyseDialog
        open={dialog === 'analyse'}
        onClose={() => setDialog(null)}
        version={version}
        hasApprovedSpec={specList.some((item) => item.status === 'APPROVED')}
        onDone={onAnalysed}
      />
      <NewVersionDialog
        open={dialog === 'version'}
        onClose={() => setDialog(null)}
        requirement={requirement}
        policies={policies}
        onCreated={onChanged}
      />
      {spec && (
        <ApproveSpecDialog
          open={dialog === 'approve'}
          onClose={() => setDialog(null)}
          spec={spec}
          onApproved={(approved) => {
            specs.setData((specs.data ?? []).map((item) => (item.id === approved.id ? approved : item)))
            specs.reload()
            onChanged()
          }}
        />
      )}
    </div>
  )
}
