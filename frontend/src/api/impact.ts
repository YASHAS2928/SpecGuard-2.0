import { api, request } from './client'
import type { Actor, ChangeImpact, RequirementVersion, Run, Spec } from './types'

export type ImpactClass = ChangeImpact['impacted_tests'][number]['impact_class']
export type ImpactReport = ChangeImpact
export type RuleChange = ChangeImpact['rule_changes'][number]
export type ImpactedTest = ChangeImpact['impacted_tests'][number]

export interface FamilyItem {
  spec: Spec
  version: RequirementVersion
}

export function analyzeImpact(newSpecId: string, fromSpecId: string, actor: Actor): Promise<ChangeImpact> {
  return request<ChangeImpact>('POST', `/specs/${newSpecId}/impact`, { from_spec_id: fromSpecId, ...actor })
}

export function rerunImpacted(specId: string, testIds: string[], actor: Actor): Promise<Run> {
  return request<Run>('POST', '/runs', { spec_id: specId, test_ids: testIds, trigger: 'IMPACT_RERUN', ...actor })
}

/** Every specification of every version of one requirement. */
export async function loadRequirementSpecs(requirementId: string): Promise<FamilyItem[]> {
  const requirements = await api.listRequirements()
  const requirement = requirements.find((item) => item.id === requirementId)
  if (!requirement) return []
  const groups = await Promise.all(
    requirement.versions.map(async (version) => (await api.listSpecs(version.id)).map((spec) => ({ spec, version }))),
  )
  return groups.flat()
}
