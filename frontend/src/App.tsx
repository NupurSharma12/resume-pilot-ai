import { Routes, Route } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import DashboardPage from './pages/DashboardPage'
import ResumePage from './pages/ResumePage'
import JobDescriptionPage from './pages/JobDescriptionPage'
import HistoryPage from './pages/HistoryPage'
import SettingsPage from './pages/SettingsPage'
import CareerConversationPage from './pages/CareerConversationPage'
import TailoredResumePage from './pages/TailoredResumePage'
import InterviewPreparationPage from './pages/InterviewPreparationPage'
import { ResumeSessionProvider } from './session/ResumeSessionContext'

function App() {
  return (
    // Above the route tree (not inside DashboardLayout) so normal page
    // navigation -- which only swaps the `<Outlet>`'s child, not
    // `DashboardLayout` itself -- can never remount it either. See
    // docs/frontend/resume-session-state.md.
    <ResumeSessionProvider>
      <Routes>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/resume" element={<ResumePage />} />
          <Route path="/job-description" element={<JobDescriptionPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/career-conversation" element={<CareerConversationPage />} />
          <Route path="/tailored-resume" element={<TailoredResumePage />} />
          <Route path="/interview-preparation" element={<InterviewPreparationPage />} />
        </Route>
      </Routes>
    </ResumeSessionProvider>
  )
}

export default App
