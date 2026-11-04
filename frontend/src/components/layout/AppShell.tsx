import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { CommandPalette } from './CommandPalette'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

const KEY = 'specguard.sidebar'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem(KEY, collapsed ? '1' : '0')
    } catch {
      // ignore storage errors
    }
  }, [collapsed])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((open) => !open)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="flex h-full bg-canvas text-fg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-1.5 focus:text-accent-fg"
      >
        Skip to content
      </a>
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((value) => !value)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setMobileOpen(true)} onSearch={() => setPaletteOpen(true)} />
        <main id="main" className="min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>
      {paletteOpen && (
        <CommandPalette
          onClose={() => setPaletteOpen(false)}
          onToggleSidebar={() => setCollapsed((value) => !value)}
        />
      )}
    </div>
  )
}
