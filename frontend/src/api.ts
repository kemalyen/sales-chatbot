import axios from 'axios'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const TOKEN_KEY = 'sales-chatbot-token'

export const api = axios.create({ baseURL: API_BASE_URL })

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Storage unavailable (private mode): the session stays in memory only.
  }
  api.defaults.headers.common.Authorization = `Bearer ${token}`
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing to clean up if storage is unavailable.
  }
  delete api.defaults.headers.common.Authorization
}

type ValidationItem = {
  loc?: (string | number)[]
  msg?: string
}

function detailFrom(data: unknown): string | null {
  if (typeof data !== 'object' || data === null || !('detail' in data)) {
    return null
  }

  const detail = (data as { detail: unknown }).detail
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((item: ValidationItem) => {
      const field = item.loc?.at(-1)
      const message = item.msg ?? 'is invalid'
      return field ? `${field}: ${message}` : message
    })
    return parts.length > 0 ? parts.join(' · ') : null
  }
  return null
}

export function describeError(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return 'Something went wrong. Please try again.'
  }
  if (!error.response) {
    return 'Cannot reach the server. Is the backend running?'
  }

  return (
    detailFrom(error.response.data) ??
    `Request failed with status ${error.response.status}.`
  )
}

const storedToken = getToken()
if (storedToken) {
  api.defaults.headers.common.Authorization = `Bearer ${storedToken}`
}