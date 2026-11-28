import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { DatabaseProvider } from './lib/database'
import { SessionProvider, useSession } from './lib/session'
import Account from './screens/Account'
import Admin from './screens/Admin'
import Arena from './screens/Arena'
import Ask from './screens/Ask'
import Data from './screens/Data'
import History from './screens/History'
import Knowledge from './screens/Knowledge'
import Landing from './screens/Landing'
import Login from './screens/Login'
import Review from './screens/Review'
import ReviewDetail from './screens/ReviewDetail'
import Saved from './screens/Saved'

// The working pages need a logged-in user; send everyone else to the login page.
function RequireLogin({ children }: { children: ReactNode }) {
  const { me, loading } = useSession()
  const location = useLocation()
  if (loading) return <p className="p-8 text-sm text-muted">Loading...</p>
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <>{children}</>
}

// The provider panel needs role "admin".
function RequireAdmin({ children }: { children: ReactNode }) {
  const { me } = useSession()
  if (me?.user.role !== 'admin') return <Navigate to="/ask" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login mode="login" />} />
          <Route path="/signup" element={<Login mode="signup" />} />
          <Route
            element={
              <RequireLogin>
                <DatabaseProvider>
                  <AppShell />
                </DatabaseProvider>
              </RequireLogin>
            }
          >
            <Route path="/ask" element={<Ask />} />
            <Route path="/history" element={<History />} />
            <Route path="/saved" element={<Saved />} />
            <Route path="/data" element={<Data />} />
            <Route path="/metrics" element={<Knowledge key="meanings" mode="meanings" />} />
            <Route path="/review" element={<Review />} />
            <Route path="/review/:id" element={<ReviewDetail />} />
            <Route path="/knowledge" element={<Knowledge key="learned" mode="learned" />} />
            <Route
              path="/arena"
              element={
                <RequireAdmin>
                  <Arena />
                </RequireAdmin>
              }
            />
            <Route path="/account" element={<Account />} />
            <Route
              path="/admin"
              element={
                <RequireAdmin>
                  <Admin />
                </RequireAdmin>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  )
}
