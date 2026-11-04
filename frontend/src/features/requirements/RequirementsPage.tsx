import { FileText } from 'lucide-react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import { EmptyState, ErrorState, Panel, Skeleton } from '../../components/ui'
import { useLoad } from '../../hooks'
import { NewRequirementDialog } from './RequirementDialogs'
import { RequirementList } from './RequirementList'
import { RequirementWorkspace } from './RequirementWorkspace'

export default function RequirementsPage() {
  const { requirementId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const requirements = useLoad(() => api.listRequirements(), 'requirements')
  const policies = useLoad(() => api.listPolicies(), 'policies')

  const newOpen = params.get('new') === '1'
  const selected = requirements.data?.find((item) => item.id === requirementId) ?? null

  let detail
  if (!requirementId) {
    detail = (
      <Panel>
        <EmptyState
          icon={FileText}
          title="Select a requirement"
          description="Choose one on the left to read it, see the AI-extracted rules with their source evidence, and approve the specification."
        />
      </Panel>
    )
  } else if (requirements.error) {
    detail = <ErrorState error={requirements.error} onRetry={requirements.reload} />
  } else if (policies.error) {
    detail = <ErrorState error={policies.error} onRetry={policies.reload} />
  } else if (!requirements.data || !policies.data) {
    detail = <Skeleton className="h-64 w-full" />
  } else if (!selected) {
    detail = (
      <Panel>
        <EmptyState title="Requirement not found" description="It may have been removed, or the link is wrong." />
      </Panel>
    )
  } else {
    detail = (
      <RequirementWorkspace
        key={`${selected.id}:${selected.latest_version}`}
        requirement={selected}
        policies={policies.data}
        onChanged={requirements.reload}
      />
    )
  }

  return (
    <div className="mx-auto grid max-w-[1500px] gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
      <div className={requirementId ? 'hidden lg:block' : ''}>
        <RequirementList
          requirements={requirements.data}
          loading={requirements.loading}
          error={requirements.error}
          onRetry={requirements.reload}
          selectedId={requirementId}
          onNew={() => setParams({ new: '1' })}
        />
      </div>
      <div className={`min-w-0 ${requirementId ? '' : 'hidden lg:block'}`}>{detail}</div>

      {policies.data && (
        <NewRequirementDialog
          open={newOpen}
          onClose={() => setParams({})}
          policies={policies.data}
          onCreated={(created) => {
            requirements.reload()
            navigate(`/requirements/${created.id}`)
          }}
        />
      )}
    </div>
  )
}
