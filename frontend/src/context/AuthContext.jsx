import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { ApiError, get, post, setWorkspaceId, storedWorkspaceId } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [state, setState] = useState({ loading: true, user: null, workspaces: [], workspace: null })

  const apply = useCallback((payload) => {
    if (!payload?.user) {
      setWorkspaceId(null)
      setState({ loading: false, user: null, workspaces: [], workspace: null })
      return
    }
    const wanted = storedWorkspaceId()
    const workspace = payload.workspaces.find((w) => String(w.id) === wanted) || payload.workspaces[0] || null
    setWorkspaceId(workspace?.id ?? null)
    setState({ loading: false, user: payload.user, workspaces: payload.workspaces, workspace })
  }, [])

  const refresh = useCallback(async () => {
    try {
      apply(await get('/auth/me/'))
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) apply(null)
      else setState((s) => ({ ...s, loading: false }))
    }
  }, [apply])

  useEffect(() => {
    refresh()
  }, [refresh])

  const value = useMemo(
    () => ({
      ...state,
      refresh,
      async login(username, password) {
        apply(await post('/auth/login/', { username, password }))
      },
      async register(data) {
        apply(await post('/auth/register/', data))
      },
      async logout() {
        await post('/auth/logout/')
        apply(null)
      },
      selectWorkspace(id) {
        const ws = state.workspaces.find((w) => w.id === id)
        if (ws) {
          setWorkspaceId(ws.id)
          setState((s) => ({ ...s, workspace: ws }))
        }
      },
      canManage: ['owner', 'admin'].includes(state.workspace?.role),
    }),
    [state, refresh, apply],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
