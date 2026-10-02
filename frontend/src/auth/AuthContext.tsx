import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, tokens } from '../api/client'

interface User {
  id: string; username: string; full_name: string
  roles: string[]; permissions: string[]; is_admin?: boolean
}
interface AuthCtx {
  user: User | null
  can: (perm: string) => boolean
  login: (u: string, p: string) => Promise<void>
  logout: () => void
}
const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)

  const load = useCallback(async () => {
    if (!tokens.access) return
    try {
      const me = await api.get('/auth/me')
      setUser(me.data)
    } catch { /* 401 by interceptor */ }
  }, [])

  useEffect(() => { load() }, [load])

  const login = useCallback(async (username: string, password: string) => {
    const r = await api.post('/auth/login', { username, password })
    tokens.access = r.data.access_token
    tokens.refresh = r.data.refresh_token
    const me = await api.get('/auth/me')
    setUser(me.data)
  }, [])

  const logout = useCallback(() => {
    api.post('/auth/logout', { refresh_token: tokens.refresh }).catch(() => {})
    tokens.access = ''
    tokens.refresh = ''
    setUser(null)
  }, [])

  const can = useCallback((perm: string) => {
    if (!user) return false
    if (user.is_admin || user.roles?.includes('ADMIN')) return true
    return user.permissions?.includes(perm) ?? false
  }, [user])

  return <Ctx.Provider value={{ user, can, login, logout }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
