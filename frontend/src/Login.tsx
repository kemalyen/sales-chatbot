import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, describeError, setToken } from './api'
import './Login.css'

const MAX_PASSWORD_LENGTH = 72
const MIN_PASSWORD_LENGTH = 8

type Mode = 'login' | 'signup'

type TokenResponse = {
  access_token: string
  token_type: string
}

type LoginProps = {
  onAuthenticated: (token: string) => void
}

function Login({ onAuthenticated }: LoginProps) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const isSignup = mode === 'signup'

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) {
      return
    }

    const trimmedEmail = email.trim()
    if (!trimmedEmail) {
      setError('Email is required.')
      return
    }
    if (!password) {
      setError('Password is required.')
      return
    }
    if (isSignup && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      if (isSignup) {
        await api.post('/api/auth/register', {
          email: trimmedEmail,
          password,
        })
      }

      const { data } = await api.post<TokenResponse>('/api/auth/login', {
        email: trimmedEmail,
        password,
      })

      setToken(data.access_token)
      onAuthenticated(data.access_token)
    } catch (caught) {
      setError(describeError(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth">
      <form className="auth-card" onSubmit={handleSubmit} noValidate>
        <h1 className="auth-title">Sales Chatbot</h1>
        <p className="auth-subtitle">
          {isSignup
            ? 'Create an account to start shopping.'
            : 'Sign in to continue shopping.'}
        </p>

        <div className="auth-tabs" role="group" aria-label="Authentication mode">
          <button
            type="button"
            className="auth-tab"
            aria-pressed={!isSignup}
            onClick={() => switchMode('login')}
          >
            Log in
          </button>
          <button
            type="button"
            className="auth-tab"
            aria-pressed={isSignup}
            onClick={() => switchMode('signup')}
          >
            Sign up
          </button>
        </div>

        <label className="auth-field">
          <span>Email</span>
          <input
            type="email"
            name="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={submitting}
            required
          />
        </label>

        <label className="auth-field">
          <span>Password</span>
          <input
            type="password"
            name="password"
            autoComplete={isSignup ? 'new-password' : 'current-password'}
            value={password}
            maxLength={MAX_PASSWORD_LENGTH}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            required
          />
        </label>

        {isSignup && (
          <p className="auth-hint">
            Between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters.
          </p>
        )}

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="auth-submit" disabled={submitting}>
          {submitting ? 'Please wait…' : isSignup ? 'Create account' : 'Log in'}
        </button>
      </form>
    </main>
  )
}

export default Login