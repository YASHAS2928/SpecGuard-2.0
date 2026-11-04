/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

type ToastTone = 'ok' | 'bad' | 'info' | 'warn'

interface ToastItem {
  id: number
  tone: ToastTone
  title: string
  description?: string
}

interface ToastValue {
  push: (toast: Omit<ToastItem, 'id'>) => void
}

const ToastContext = createContext<ToastValue | null>(null)

const BAR: Record<ToastTone, string> = {
  ok: 'bg-ok',
  bad: 'bg-bad',
  info: 'bg-info',
  warn: 'bg-warn',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const counter = useRef(0)

  const push = useCallback((toast: Omit<ToastItem, 'id'>) => {
    counter.current += 1
    const id = counter.current
    setItems((current) => [...current.slice(-3), { ...toast, id }])
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 6000)
  }, [])

  const value = useMemo(() => ({ push }), [push])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2"
      >
        {items.map((item) => (
          <div
            key={item.id}
            className="anim-pop pointer-events-auto flex overflow-hidden rounded-md border border-line-strong bg-surface shadow-float"
          >
            <span className={`w-1 shrink-0 ${BAR[item.tone]}`} />
            <div className="px-3 py-2">
              <p className="text-sm font-medium">{item.title}</p>
              {item.description && <p className="text-xs text-fg-2">{item.description}</p>}
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used inside ToastProvider')
  return value
}
