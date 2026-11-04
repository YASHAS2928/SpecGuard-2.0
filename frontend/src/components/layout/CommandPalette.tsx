import { FileText, Moon, PanelLeft, Plus, Search, UserCog } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { ROLES, useSession } from '../../app/session'
import { useTheme } from '../../app/theme'
import { useWorkspace } from '../../app/workspace'
import { humanize } from '../../lib/format'
import { useOverlay } from '../ui'
import { NAV_ITEMS } from './nav'

interface Command {
  id: string
  label: string
  group: string
  icon: LucideIcon
  run: () => void
}

export function CommandPalette({
  onClose,
  onToggleSidebar,
}: {
  onClose: () => void
  onToggleSidebar: () => void
}) {
  const navigate = useNavigate()
  const { toggle: toggleTheme } = useTheme()
  const { actor, setActor } = useSession()
  const workspace = useWorkspace()
  const [query, setQuery] = useState('')
  const [index, setIndex] = useState(0)
  const ref = useRef<HTMLDivElement>(null)
  useOverlay(true, onClose, ref)

  const commands = useMemo<Command[]>(() => {
    const list: Command[] = NAV_ITEMS.map((item) => ({
      id: `go-${item.id}`,
      label: `Go to ${item.label}`,
      group: 'Navigate',
      icon: item.icon,
      run: () => navigate(item.to),
    }))
    list.push({
      id: 'new-requirement',
      label: 'New requirement',
      group: 'Actions',
      icon: Plus,
      run: () => navigate('/requirements?new=1'),
    })
    if (workspace.requirementId) {
      list.push({
        id: 'open-requirement',
        label: `Open requirement ${workspace.requirementCode ?? ''}`,
        group: 'Actions',
        icon: FileText,
        run: () => navigate(`/requirements/${workspace.requirementId}`),
      })
    }
    if (workspace.specId) {
      list.push({
        id: 'open-spec',
        label: `Open clarification for spec v${workspace.specVersion}`,
        group: 'Actions',
        icon: Search,
        run: () => navigate(`/clarification/${workspace.specId}`),
      })
    }
    list.push(
      { id: 'theme', label: 'Toggle light / dark theme', group: 'Settings', icon: Moon, run: toggleTheme },
      { id: 'sidebar', label: 'Collapse or expand sidebar', group: 'Settings', icon: PanelLeft, run: onToggleSidebar },
    )
    for (const role of ROLES) {
      if (role !== actor.actor_role) {
        list.push({
          id: `role-${role}`,
          label: `Switch role to ${humanize(role)}`,
          group: 'Settings',
          icon: UserCog,
          run: () => setActor({ ...actor, actor_role: role }),
        })
      }
    }
    return list
  }, [navigate, workspace, toggleTheme, onToggleSidebar, actor, setActor])

  const results = commands.filter((command) =>
    command.label.toLowerCase().includes(query.trim().toLowerCase()),
  )
  const active = Math.min(index, Math.max(results.length - 1, 0))
  const activeId = results[active] ? `cmd-${results[active].id}` : undefined

  useEffect(() => {
    if (activeId) document.getElementById(activeId)?.scrollIntoView({ block: 'nearest' })
  }, [activeId])

  function run(command: Command) {
    onClose()
    command.run()
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setIndex(Math.min(active + 1, results.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setIndex(Math.max(active - 1, 0))
    } else if (event.key === 'Enter' && results[active]) {
      event.preventDefault()
      run(results[active])
    }
  }

  return createPortal(
    <div
      className="anim-fade fixed inset-0 z-50 flex items-start justify-center bg-black/55 p-4 pt-[12vh]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="anim-pop w-full max-w-lg overflow-hidden rounded-lg border border-line-strong bg-surface shadow-float"
      >
        <input
          data-autofocus
          role="combobox"
          aria-expanded="true"
          aria-controls="command-list"
          aria-activedescendant={activeId}
          aria-label="Search commands"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setIndex(0)
          }}
          onKeyDown={onKeyDown}
          placeholder="Type a command or page name…"
          className="w-full border-b border-line bg-transparent px-4 py-3 text-base text-fg placeholder:text-fg-3 focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        />
        <ul id="command-list" role="listbox" className="max-h-80 overflow-y-auto p-1">
          {results.length === 0 && <li className="px-3 py-6 text-center text-sm text-fg-3">No matching command</li>}
          {results.map((command, position) => {
            const Icon = command.icon
            return (
              <li
                key={command.id}
                id={`cmd-${command.id}`}
                role="option"
                aria-selected={position === active}
                onMouseMove={() => setIndex(position)}
                onClick={() => run(command)}
                className={`flex cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-sm ${
                  position === active ? 'bg-raised text-fg' : 'text-fg-2'
                }`}
              >
                <Icon size={14} aria-hidden="true" className="text-fg-3" />
                <span className="flex-1">{command.label}</span>
                <span className="text-xs text-fg-3">{command.group}</span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>,
    document.body,
  )
}
