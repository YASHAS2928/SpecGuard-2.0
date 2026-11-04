import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useLoad } from './hooks'

describe('useLoad', () => {
  it('discards an old request when the resource key changes', async () => {
    let finishOld!: (value: string) => void
    const old = new Promise<string>((resolve) => { finishOld = resolve })
    const loader = vi.fn((key: string) => key === 'old' ? old : Promise.resolve('new data'))
    const { result, rerender } = renderHook(({ resource }) => useLoad(() => loader(resource), resource), {
      initialProps: { resource: 'old' },
    })
    expect(result.current.loading).toBe(true)
    rerender({ resource: 'new' })
    await waitFor(() => expect(result.current.data).toBe('new data'))
    await act(async () => { finishOld('stale data') })
    expect(result.current.data).toBe('new data')
  })

  it('clears errors on reload and returns fresh data', async () => {
    const loader = vi.fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error('Offline'))
      .mockResolvedValueOnce('Recovered')
    const { result } = renderHook(() => useLoad(loader, 'resource'))
    await waitFor(() => expect(result.current.error?.message).toBe('Offline'))
    act(() => result.current.reload())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.data).toBe('Recovered'))
    expect(result.current.error).toBeNull()
  })

  it('hides data from the previous key while the next resource loads', async () => {
    const { result, rerender } = renderHook(
      ({ resource }) => useLoad(() => resource === 'first'
        ? Promise.resolve('first data') : new Promise<string>(() => {}), resource),
      { initialProps: { resource: 'first' } },
    )
    await waitFor(() => expect(result.current.data).toBe('first data'))
    rerender({ resource: 'second' })
    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(true)
  })
})
