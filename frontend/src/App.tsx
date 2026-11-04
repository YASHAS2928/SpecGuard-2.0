import { useState } from 'react'
import type { Actor, AnalysisMetadata, Role } from './api/types'
import RequirementsPage from './pages/RequirementsPage'
import SpecPage from './pages/SpecPage'

type Tab = 'requirements' | 'spec'

const ROLES: Role[] = ['BUSINESS_ANALYST', 'QA_ENGINEER', 'DEVELOPER', 'ADMIN']
const STORAGE_KEY = 'specguard.actor'

const DEFAULT_ACTOR: Actor = { actor: 'asha.ba', actor_role: 'BUSINESS_ANALYST' }

function isRole(value: string): value is Role {
  return ROLES.some((role) => role === value)
}

function loadActor(): { actor: Actor; warning: string | null } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (
        typeof parsed === 'object' && parsed !== null &&
        'actor' in parsed && typeof parsed.actor === 'string' &&
        parsed.actor.trim().length > 0 && parsed.actor.length <= 80 &&
        'actor_role' in parsed && typeof parsed.actor_role === 'string' && isRole(parsed.actor_role)
      ) {
        return { actor: { actor: parsed.actor, actor_role: parsed.actor_role }, warning: null }
      }
      return { actor: DEFAULT_ACTOR, warning: 'Saved actor settings are invalid. Using the demo actor.' }
    }
  } catch {
    return { actor: DEFAULT_ACTOR, warning: 'Actor settings could not be loaded. Using the demo actor.' }
  }
  return { actor: DEFAULT_ACTOR, warning: null }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('requirements')
  const [actorSettings, setActorSettings] = useState(loadActor)
  const actor = actorSettings.actor
  const [specId, setSpecId] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<AnalysisMetadata | null>(null)

  function updateActor(next: Actor) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      setActorSettings({ actor: next, warning: null })
    } catch {
      setActorSettings({ actor: next, warning: 'Actor settings could not be saved; changes apply only to this session.' })
    }
  }

  function openSpec(id: string, meta: AnalysisMetadata | null) {
    setSpecId(id)
    setAnalysis(meta)
    setTab('spec')
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: 'requirements', label: 'Requirements' },
    { id: 'spec', label: 'Specification' },
  ]

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
          <h1 className="text-lg font-bold text-indigo-700">SpecGuard 2.0</h1>
          <nav className="flex gap-1">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`rounded px-3 py-1.5 text-sm font-medium ${
                  tab === item.id
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <input
              aria-label="User name"
              className="w-32 rounded border border-slate-300 px-2 py-1"
              value={actor.actor}
              onChange={(e) => updateActor({ ...actor, actor: e.target.value })}
            />
            <select
              aria-label="Role"
              className="rounded border border-slate-300 px-2 py-1"
              value={actor.actor_role}
              onChange={(e) => {
                if (isRole(e.target.value)) updateActor({ ...actor, actor_role: e.target.value })
              }}
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <p className="mb-4 text-xs text-slate-500">
          Fictional demonstration data only. Actor selection is not authentication.
        </p>
        {actorSettings.warning && (
          <p role="alert" className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm">
            {actorSettings.warning}
          </p>
        )}
        {tab === 'requirements' && <RequirementsPage actor={actor} onOpenSpec={openSpec} />}
        {tab === 'spec' && <SpecPage key={specId} specId={specId} analysis={analysis} actor={actor} />}
      </main>
    </div>
  )
}
