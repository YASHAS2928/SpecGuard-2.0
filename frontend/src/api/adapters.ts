import { api } from './client'
import type { Requirement, RequirementVersion, Spec } from './types'

export interface SpecIndexItem {
  requirement: Requirement
  version: RequirementVersion
  spec: Spec
}

/** Every specification of every requirement's latest version (small data sets only). */
export async function loadSpecIndex(): Promise<SpecIndexItem[]> {
  const requirements = await api.listRequirements()
  const groups = await Promise.all(
    requirements.map(async (requirement) => {
      const version = requirement.versions[requirement.versions.length - 1]
      if (!version) return []
      const specs = await api.listSpecs(version.id)
      return specs.map((spec) => ({ requirement, version, spec }))
    }),
  )
  return groups.flat()
}
