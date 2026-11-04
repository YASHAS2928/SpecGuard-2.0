import {
  GitCompare,
  LayoutDashboard,
  ListChecks,
  MessagesSquare,
  Play,
  ScrollText,
  FileText,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  id: string
  to: string
  label: string
  icon: LucideIcon
  group: string
  /** Name of the batch that delivers the screen, when it is not built yet. */
  soon?: string
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'overview', to: '/', label: 'Overview', icon: LayoutDashboard, group: '' },
  { id: 'requirements', to: '/requirements', label: 'Requirements', icon: FileText, group: 'Specify' },
  { id: 'clarification', to: '/clarification', label: 'Clarification', icon: MessagesSquare, group: 'Specify' },
  { id: 'tests', to: '/tests', label: 'Test review', icon: ListChecks, group: 'Verify' },
  { id: 'runs', to: '/runs', label: 'Execution & defects', icon: Play, group: 'Verify' },
  { id: 'impact', to: '/impact', label: 'Change impact', icon: GitCompare, group: 'Evolve' },
  { id: 'audit', to: '/audit', label: 'Audit history', icon: ScrollText, group: 'Govern' },
]

export function isActivePath(pathname: string, item: NavItem): boolean {
  return item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)
}
