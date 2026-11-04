/* eslint-disable react-refresh/only-export-components */
import { Check, Menu, Moon, Search, Sun } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { ROLES, useSession } from '../../app/session'
import { useTheme } from '../../app/theme'
import { useWorkspace } from '../../app/workspace'
import { humanize } from '../../lib/format'
import { IconButton, Kbd, MenuItem, Popover } from '../ui'
import { NAV_ITEMS, isActivePath } from './nav'

export const MOD_KEY =
  typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform) ? '⌘' : 'Ctrl'

function UserMenu() {
  const { actor, setActor } = useSession()
  return (
    <Popover
      label="User and role"
      align="right"
      buttonClassName="flex h-8 items-center gap-2 rounded-md border border-line-strong bg-raised pl-1 pr-2 text-xs hover:bg-well"
      button={
        <>
          <span className="flex h-6 w-6 items-center justify-center rounded bg-accent/20 text-xs font-semibold uppercase text-accent">
            {actor.actor.charAt(0) || '?'}
          </span>
          <span className="hidden sm:inline">{humanize(actor.actor_role)}</span>
        </>
      }
    >
      {(close) => (
        <div className="w-64 space-y-2 p-2">
          <label className="block text-xs text-fg-2">
            Name
            <input
              value={actor.actor}
              onChange={(event) => setActor({ ...actor, actor: event.target.value })}
              className="mt-1 w-full rounded-md border border-line-strong bg-well px-2 py-1.5 text-sm text-fg"
            />
          </label>
          <div>
            <p className="mb-1 text-xs text-fg-2">Role</p>
            {ROLES.map((role) => (
              <MenuItem
                key={role}
                active={role === actor.actor_role}
                onSelect={() => {
                  setActor({ ...actor, actor_role: role })
                  close()
                }}
              >
                <span className="w-4">{role === actor.actor_role && <Check size={13} />}</span>
                {humanize(role)}
              </MenuItem>
            ))}
          </div>
          <p className="border-t border-line pt-2 text-xs text-fg-3">
            Roles are self-declared. This build has no authentication.
          </p>
        </div>
      )}
    </Popover>
  )
}

export function TopBar({ onMenu, onSearch }: { onMenu: () => void; onSearch: () => void }) {
  const { pathname } = useLocation()
  const { theme, toggle } = useTheme()
  const workspace = useWorkspace()
  const current = NAV_ITEMS.find((item) => isActivePath(pathname, item))

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-surface px-3">
      <IconButton label="Open navigation" className="md:hidden" onClick={onMenu}>
        <Menu size={16} />
      </IconButton>
      <h1 className="text-base font-semibold">{current?.label ?? 'SpecGuard'}</h1>
      {workspace.specId && workspace.requirementCode && (
        <Link
          to={`/clarification/${workspace.specId}`}
          title="Active requirement and specification"
          className="ml-2 hidden items-center gap-1.5 rounded-md border border-line-strong bg-raised px-2 py-1 text-xs hover:bg-well sm:inline-flex"
        >
          <span className="font-mono">{workspace.requirementCode}</span>
          <span className="text-fg-3">spec v{workspace.specVersion}</span>
        </Link>
      )}
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={onSearch}
          className="hidden h-8 items-center gap-2 rounded-md border border-line-strong bg-raised px-2.5 text-xs text-fg-3 hover:bg-well sm:flex"
        >
          <Search size={13} aria-hidden="true" />
          Search or jump to…
          <Kbd>{MOD_KEY} K</Kbd>
        </button>
        <IconButton label="Search" className="sm:hidden" onClick={onSearch}>
          <Search size={16} />
        </IconButton>
        <IconButton
          label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          onClick={toggle}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </IconButton>
        <UserMenu />
      </div>
    </header>
  )
}
