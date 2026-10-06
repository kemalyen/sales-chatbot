import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import { API_BASE_URL, clearToken, getToken } from './api'
import Chat from './Chat'
import Login from './Login'
import './App.css'

type CurrentUser = {
  id: number
  email: string
  created_at: string
}

function App() {
  const [token, setToken] = useState<string | null>(() => getToken())
  const [user, setUser] = useState<CurrentUser | null>(null)

  useEffect(() => {
    if (!token) {
      return
    }

    let cancelled = false
    axios
      .get<CurrentUser>(`${API_BASE_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then(({ data }) => {
        if (!cancelled) {
          setUser(data)
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearToken()
          setToken(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [token])

  const handleSignOut = useCallback(() => {
    clearToken()
    setToken(null)
    setUser(null)
  }, [])

  if (!token) {
    return <Login onAuthenticated={setToken} />
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">AI Sales Assistant – Portal</h1>
        <div className="app-header-right">
          {user && <span className="app-user">{user.email}</span>}
          <button type="button" className="app-logout" onClick={handleSignOut}>
            Log out
          </button>
        </div>
      </header>

      <Chat token={token} onLogout={handleSignOut} />
    </div>
  )
}

export default App