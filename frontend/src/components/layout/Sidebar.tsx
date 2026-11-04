import { PanelLeftClose, PanelLeftOpen, ShieldCheck } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { getHealth } from '../../api/system'
import { useWorkspace } from '../../app/workspace'
import { useLoad } from '../../hooks'
import { IconButton } from '../ui'
import { NAV_ITEMS, isActivePath } from './nav'

export function Sidebar({
  collapsed,
  onToggle,
  mobileOpen,
  onCloseMobile,
}: {
  collapsed: boolean
  onToggle: () => void
  mobileOpen: boolean
  onCloseMobile: () => void
}) {
  const { pathname } = useLocation()
  const workspace = useWorkspace()
  const health = useLoad(() => getHealth(), 'health')
  const ai = health.data?.ai
  const dot = !ai ? 'bg-fg-3' : ai.configured ? 'bg-ok' : 'bg-warn'
  const hide = collapsed ? 'md:hidden' : ''
  const groups = Array.from(new Set(NAV_ITEMS.map((item) => item.group)))

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={onCloseMobile} aria-hidden="true" />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-56 shrink-0 flex-col border-r border-line bg-surface transition-transform md:static md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } ${collapsed ? 'md:w-14' : 'md:w-56'}`}
        aria-label="Primary"
      >
        <div className="flex h-12 items-center gap-2 border-b border-line px-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-accent-fg">
            <ShieldCheck size={16} aria-hidden="true" />
          </span>
          <span className={`text-base font-semibold tracking-tight ${hide}`}>SpecGuard</span>
        </div>

        <nav className="flex-1 space-y-3 overflow-y-auto px-2 py-3">
          {groups.map((group) => (
            <div key={group || 'top'}>
              {group && (
                <p className={`px-2 pb-1 text-[10px] font-medium uppercase tracking-wider text-fg-3 ${hide}`}>
                  {group}
                </p>
              )}
              <ul className="space-y-0.5">
                {NAV_ITEMS.filter((item) => item.group === group).map((item) => {
                  const active = isActivePath(pathname, item)
                  const contextual = ['clarification', 'tests', 'runs', 'impact'].includes(item.id)
                  const to = contextual && workspace.specId ? `${item.to}/${workspace.specId}` : item.to
                  const Icon = item.icon
                  return (
                    <li key={item.id}>
                      <Link
                        to={to}
                        title={item.label}
                        aria-current={active ? 'page' : undefined}
                        onClick={onCloseMobile}
                        className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors ${
                          active
                            ? 'bg-raised font-medium text-fg'
                            : 'text-fg-2 hover:bg-raised hover:text-fg'
                        }`}
                      >
                        <Icon
                          size={15}
                          aria-hidden="true"
                          className={active ? 'text-accent' : 'text-fg-3'}
                        />
                        <span className={`min-w-0 flex-1 truncate ${hide}`}>{item.label}</span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="space-y-2 border-t border-line p-2">
          <div
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-fg-2"
            title={
              ai
                ? `AI provider: ${ai.provider}${ai.model ? ` (${ai.model})` : ''}${ai.configured ? '' : ' (not configured)'}`
                : 'Backend status unknown'
            }
          >
            <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} aria-hidden="true" />
            <span className={`truncate ${hide}`}>
              {ai
                ? ai.provider === 'fake'
                  ? 'AI: fake (no language model used)'
                  : `AI: ${ai.provider} · ${ai.model ?? 'model unavailable'}${ai.configured ? '' : ' (not set up)'}`
                : health.error
                  ? 'Backend unreachable'
                  : 'Checking backend…'}
            </span>
          </div>
          <IconButton
            label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={onToggle}
            className="hidden md:inline-flex"
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </IconButton>
        </div>
      </aside>
    </>
  )
}
