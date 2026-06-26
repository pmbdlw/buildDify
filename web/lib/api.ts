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

// ---- 对话 ----
export interface Conversation {
  id: string
  title: string
  model: string | null
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  role: string
  content: string
  model: string | null
  input_tokens: number
  output_tokens: number
  created_at: string
}

export function listConversations() {
  return apiFetch<Conversation[]>('/api/conversations')
}

export function getMessages(conversationId: string) {
  return apiFetch<ChatMessage[]>(`/api/conversations/${conversationId}/messages`)
}

export interface Citation {
  index: number
  document_id: string
  content: string
  score: number
}

export interface StreamHandlers {
  onMeta?: (conversationId: string, model: string, citations: Citation[]) => void
  onDelta?: (text: string) => void
  onDone?: (messageId: string) => void
  onError?: (message: string) => void
}

// POST + Bearer 的 SSE 用 fetch 流读(EventSource 不支持自定义头与 POST)
export async function streamChat(
  body: { content: string; conversation_id?: string; model?: string; dataset_id?: string },
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    const detail = await res.json().catch(() => ({}))
    throw new ApiError(res.status, detail?.detail ?? `请求失败(${res.status})`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const blocks = buf.split('\n\n')
    buf = blocks.pop() ?? ''
    for (const block of blocks) {
      const line = block.trim()
      if (!line.startsWith('data:')) continue
      const evt = JSON.parse(line.slice(5).trim())
      if (evt.type === 'meta')
        handlers.onMeta?.(evt.conversation_id, evt.model, evt.citations ?? [])
      else if (evt.type === 'delta') handlers.onDelta?.(evt.content)
      else if (evt.type === 'done') handlers.onDone?.(evt.message_id)
      else if (evt.type === 'error') handlers.onError?.(evt.message)
    }
  }
}

// ---- 知识库 ----
export interface Dataset {
  id: string
  name: string
  description: string | null
  embedding_model: string
  created_at: string
  updated_at: string
}

export interface KbDocument {
  id: string
  dataset_id: string
  name: string
  file_type: string
  status: string // pending | processing | ready | error
  error: string | null
  char_count: number
  segment_count: number
  created_at: string
  updated_at: string
}

export function listDatasets() {
  return apiFetch<Dataset[]>('/api/knowledge/datasets')
}

export function createDataset(name: string, description?: string) {
  return apiFetch<Dataset>('/api/knowledge/datasets', {
    method: 'POST',
    body: JSON.stringify({ name, description: description ?? null }),
  })
}

export function listDocuments(datasetId: string) {
  return apiFetch<KbDocument[]>(`/api/knowledge/datasets/${datasetId}/documents`)
}

// 文件上传走 multipart;不要手动设 Content-Type,交给浏览器带 boundary
export async function uploadDocument(datasetId: string, file: File): Promise<KbDocument> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/api/knowledge/datasets/${datasetId}/documents`, {
    method: 'POST',
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: form,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new ApiError(res.status, detail?.detail ?? `上传失败(${res.status})`)
  }
  return res.json() as Promise<KbDocument>
}
