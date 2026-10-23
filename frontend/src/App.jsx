import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import { useAuth } from './context/AuthContext'
import Login from './pages/Login'

const Activity = lazy(() => import('./pages/Activity'))
const AISettings = lazy(() => import('./pages/AISettings'))
const Automation = lazy(() => import('./pages/Automation'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Inbox = lazy(() => import('./pages/Inbox'))
const Integrations = lazy(() => import('./pages/Integrations'))
const Knowledge = lazy(() => import('./pages/Knowledge'))
const Personalization = lazy(() => import('./pages/Personalization'))
const Voice = lazy(() => import('./pages/Voice'))

function Protected({ children }) {
  const { loading, user } = useAuth()
  if (loading) return <Loading label="Loading workspace…" />
  if (!user) return <Navigate to="/login" replace />
  return <Suspense fallback={<Loading />}>{children}</Suspense>
}

export default function App() {
  const { user, loading } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={!loading && user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={!loading && user ? <Navigate to="/" replace /> : <Login register />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="inbox" element={<Inbox />} />
        <Route path="inbox/:id" element={<Inbox />} />
        <Route path="ai" element={<AISettings />} />
        <Route path="personalization" element={<Personalization />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="automation" element={<Automation />} />
        <Route path="voice" element={<Voice />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="activity" element={<Activity />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
