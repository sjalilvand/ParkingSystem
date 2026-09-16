import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { api, tokens } from '../api/client'

interface User { id: string; username: string; full_name: string }
interface AuthCtx { user: User | null; login: (u: string, p: string) => Promise<void>; logout: () => void }
const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)

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

  return <Ctx.Provider value={{ user, login, logout }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)