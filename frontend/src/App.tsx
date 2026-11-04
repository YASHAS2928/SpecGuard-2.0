import { Route, Routes } from 'react-router-dom'
import { SessionProvider } from './app/session'
import { ThemeProvider } from './app/theme'
import { WorkspaceProvider } from './app/workspace'
import { AppShell } from './components/layout/AppShell'
import { EmptyState, Panel, ToastProvider } from './components/ui'
import ClarificationPage from './features/clarification/ClarificationPage'
import RequirementsPage from './features/requirements/RequirementsPage'
import OverviewPage from './features/overview/OverviewPage'
import RunsPage from './features/runs/RunsPage'
import TestsPage from './features/tests/TestsPage'
import ImpactPage from './features/impact/ImpactPage'
import AuditPage from './features/audit/AuditPage'

function NotFound() {
  return (
    <Panel>
      <EmptyState title="Page not found" description="Use the sidebar or press Ctrl K to jump somewhere." />
    </Panel>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <SessionProvider>
        <WorkspaceProvider>
          <ToastProvider>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<OverviewPage />} />
                <Route path="requirements/:requirementId?" element={<RequirementsPage />} />
                <Route path="clarification/:specId?" element={<ClarificationPage />} />
                <Route path="tests/:specId?" element={<TestsPage />} />
                <Route path="runs/:specId?" element={<RunsPage />} />
                <Route path="impact/:specId?" element={<ImpactPage />} />
                <Route path="audit" element={<AuditPage />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </ToastProvider>
        </WorkspaceProvider>
      </SessionProvider>
    </ThemeProvider>
  )
}
