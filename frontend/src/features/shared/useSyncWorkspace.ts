import { useEffect } from 'react'
import { loadSpecIndex } from '../../api/adapters'
import { useWorkspace } from '../../app/workspace'
import { useLoad } from '../../hooks'

/** Keeps the top-bar context (requirement + spec) in sync with the spec shown on screen. */
export function useSyncWorkspace(specId: string, specVersion: number | undefined) {
  const { setActive } = useWorkspace()
  const index = useLoad(() => loadSpecIndex(), 'spec-index')
  const owner = index.data?.find((item) => item.spec.id === specId)
  const requirementId = owner?.requirement.id
  const requirementCode = owner?.requirement.code

  useEffect(() => {
    if (requirementId && requirementCode && specVersion !== undefined) {
      setActive({ requirementId, requirementCode, specId, specVersion })
    }
  }, [requirementId, requirementCode, specVersion, specId, setActive])

  return owner
}
