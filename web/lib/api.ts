// 后端 API 调用封装。token 存于 localStorage(MVP 简化方案)。
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000'

const TOKEN_KEY = 'builddify_token'

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new ApiError(res.status, detail?.detail ?? `请求失败(${res.status})`)
  }
  return res.json() as Promise<T>
}

// ---- 鉴权 ----
export interface User {
  id: string
  email: string
  name: string
  is_active: boolean
  created_at: string
}

export function register(email: string, password: string, name: string) {
  return apiFetch<User>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, name }),
  })
}

export async function login(email: string, password: string): Promise<string> {
  const data = await apiFetch<{ access_token: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setToken(data.access_token)
  return data.access_token
}

export function getMe() {
  return apiFetch<User>('/api/auth/me')
}
