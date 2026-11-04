/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Actor, Role } from '../api/types'

export const ROLES: Role[] = ['BUSINESS_ANALYST', 'QA_ENGINEER', 'DEVELOPER', 'ADMIN']
const KEY = 'specguard.actor'
const DEFAULT_ACTOR: Actor = { actor: 'asha.ba', actor_role: 'BUSINESS_ANALYST' }

interface SessionValue {
  actor: Actor
  setActor: (actor: Actor) => void
}

const SessionContext = createContext<SessionValue | null>(null)

function load(): Actor {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Actor
      if (parsed.actor && ROLES.includes(parsed.actor_role)) return parsed
    }
  } catch {
    // ignore storage errors
  }
  return DEFAULT_ACTOR
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [actor, setActor] = useState<Actor>(load)

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(actor))
    } catch {
      // ignore storage errors
    }
  }, [actor])

  const value = useMemo(() => ({ actor, setActor }), [actor])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside SessionProvider')
  return value
}
