/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export interface ActiveContext {
  requirementId: string | null
  requirementCode: string | null
  specId: string | null
  specVersion: number | null
}

const KEY = 'specguard.workspace'
const EMPTY: ActiveContext = {
  requirementId: null,
  requirementCode: null,
  specId: null,
  specVersion: null,
}

interface WorkspaceValue extends ActiveContext {
  setActive: (next: ActiveContext) => void
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null)

function load(): ActiveContext {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...EMPTY, ...(JSON.parse(raw) as Partial<ActiveContext>) }
  } catch {
    // ignore storage errors
  }
  return EMPTY
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ActiveContext>(load)

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(state))
    } catch {
      // ignore storage errors
    }
  }, [state])

  const setActive = useCallback((next: ActiveContext) => {
    setState((prev) =>
      prev.requirementId === next.requirementId &&
      prev.requirementCode === next.requirementCode &&
      prev.specId === next.specId &&
      prev.specVersion === next.specVersion
        ? prev
        : next,
    )
  }, [])

  const value = useMemo(() => ({ ...state, setActive }), [state, setActive])
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace(): WorkspaceValue {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return value
}
