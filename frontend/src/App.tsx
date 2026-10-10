import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AuthProvider, useAuth } from './auth'
import Layout from './components/Layout'
import AdminPage from './pages/AdminPage'
import AuthPage from './pages/AuthPage'
import ChatPage from './pages/ChatPage'
import PortfolioPage from './pages/PortfolioPage'

function AppRoutes() {
  const { user, loading } = useAuth()

  if (loading) {
    return <div className="flex h-full items-center justify-center text-slate-400">Loading…</div>
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        {/* One optional-param route, so starting a new chat doesn't remount the page */}
        <Route path="/chat/:conversationId?" element={<ChatPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        {user.is_admin && <Route path="/admin" element={<AdminPage />} />}
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
