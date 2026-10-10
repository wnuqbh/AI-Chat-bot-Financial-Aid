import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler, type User } from './api'

interface AuthState {
  user: User | null
  /** True while an existing token is being checked on page load. */
  loading: boolean
  /** Set when the user was logged out because their token expired. */
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => getToken() !== null)
  const [sessionExpired, setSessionExpired] = useState(false)

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null)
      setUser(null)
      setSessionExpired(true)
    })
  }, [])

  useEffect(() => {
    if (!getToken()) return
    api
      .me()
      .then(({ user }) => setUser(user))
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      sessionExpired,
      login: async (email, password) => {
        const { user, access_token } = await api.login(email, password)
        setToken(access_token)
        setSessionExpired(false)
        setUser(user)
      },
      register: async (email, password, fullName) => {
        const { user, access_token } = await api.register(email, password, fullName)
        setToken(access_token)
        setSessionExpired(false)
        setUser(user)
      },
      logout,
    }),
    [user, loading, sessionExpired, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
