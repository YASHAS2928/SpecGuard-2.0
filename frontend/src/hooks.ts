import { useEffect, useEffectEvent, useState } from 'react'
import { toApiError } from './api/client'
import type { ApiError } from './api/client'

/** Loads data when `key` changes (or `reload` is called). */
export function useLoad<T>(loader: () => Promise<T>, key: string) {
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState<{
    key: string
    tick: number
    data: T | null
    error: ApiError | null
  } | null>(null)
  const load = useEffectEvent(loader)

  useEffect(() => {
    let cancelled = false
    load()
      .then((value) => {
        if (!cancelled) {
          setResult({ key, tick, data: value, error: null })
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setResult({ key, tick, data: null, error: toApiError(e) })
      })
    return () => {
      cancelled = true
    }
  }, [key, tick])

  const current = result?.key === key && result.tick === tick ? result : null
  return {
    data: current?.data ?? null,
    setData: (data: T | null) => setResult({ key, tick, data, error: null }),
    error: current?.error ?? null,
    loading: current === null,
    reload: () => setTick((t) => t + 1),
  }
}
