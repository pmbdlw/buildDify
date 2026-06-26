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
  await consumeSSE(res.body, handlers)
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

// ---- 应用构建器 ----
export interface App {
  id: string
  name: string
  description: string | null
  mode: string
  status: string // draft | published
  published_config_id: string | null
  created_at: string
  updated_at: string
}

export interface AppConfig {
  id: string
  app_id: string
  version: number
  model: string | null
  system_prompt: string | null
  temperature: number | null
  max_tokens: number
  dataset_id: string | null
  created_at: string
}

export interface AppConfigInput {
  model?: string | null
  system_prompt?: string | null
  temperature?: number | null
  max_tokens: number
  dataset_id?: string | null
}

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  last_used_at: string | null
  created_at: string
}

export interface ApiKeyCreated extends ApiKey {
  key: string
}

export function listApps() {
  return apiFetch<App[]>('/api/apps')
}

export function createApp(name: string, mode: string = 'chatbot', description?: string) {
  return apiFetch<App>('/api/apps', {
    method: 'POST',
    body: JSON.stringify({ name, mode, description: description ?? null }),
  })
}

export function getApp(appId: string) {
  return apiFetch<App>(`/api/apps/${appId}`)
}

export function updateApp(appId: string, data: { name?: string; description?: string }) {
  return apiFetch<App>(`/api/apps/${appId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteApp(appId: string) {
  return apiFetch<void>(`/api/apps/${appId}`, { method: 'DELETE' })
}

export function getAppConfig(appId: string) {
  return apiFetch<AppConfig>(`/api/apps/${appId}/config`)
}

export function saveAppConfig(appId: string, config: AppConfigInput) {
  return apiFetch<AppConfig>(`/api/apps/${appId}/config`, {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export function publishApp(appId: string) {
  return apiFetch<App>(`/api/apps/${appId}/publish`, { method: 'POST' })
}

export function listApiKeys(appId: string) {
  return apiFetch<ApiKey[]>(`/api/apps/${appId}/api-keys`)
}

export function createApiKey(appId: string, name: string) {
  return apiFetch<ApiKeyCreated>(`/api/apps/${appId}/api-keys`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function revokeApiKey(appId: string, keyId: string) {
  return apiFetch<void>(`/api/apps/${appId}/api-keys/${keyId}`, { method: 'DELETE' })
}

// ---- 工作流 ----
// 画布节点/连线(对应 React Flow 与后端 graph JSON);data 为各节点自由配置
export interface WfNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export interface WfEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
}

export interface WfGraph {
  nodes: WfNode[]
  edges: WfEdge[]
}

export interface WorkflowListItem {
  id: string
  name: string
  description: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface Workflow extends WorkflowListItem {
  app_id: string | null
  graph: WfGraph
}

export interface NodeRun {
  id: string
  node_id: string
  node_type: string
  status: string // running | succeeded | failed | skipped
  inputs: Record<string, unknown> | null
  outputs: Record<string, unknown> | null
  error: string | null
  elapsed_ms: number | null
  sort_order: number
}

export interface WorkflowRun {
  id: string
  workflow_id: string
  status: string // pending | running | succeeded | failed
  inputs: Record<string, unknown>
  outputs: Record<string, unknown> | null
  error: string | null
  elapsed_ms: number | null
  created_at: string
  node_runs: NodeRun[]
}

export function listWorkflows() {
  return apiFetch<WorkflowListItem[]>('/api/workflows')
}

export function createWorkflow(name: string, description?: string) {
  return apiFetch<Workflow>('/api/workflows', {
    method: 'POST',
    body: JSON.stringify({ name, description: description ?? null }),
  })
}

export function getWorkflow(id: string) {
  return apiFetch<Workflow>(`/api/workflows/${id}`)
}

export function saveWorkflow(
  id: string,
  data: { name?: string; description?: string; graph?: WfGraph },
) {
  return apiFetch<Workflow>(`/api/workflows/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteWorkflow(id: string) {
  return apiFetch<void>(`/api/workflows/${id}`, { method: 'DELETE' })
}

export function runWorkflow(id: string, inputs: Record<string, unknown>) {
  return apiFetch<WorkflowRun>(`/api/workflows/${id}/run`, {
    method: 'POST',
    body: JSON.stringify({ inputs }),
  })
}

// 应用调试对话(走最新配置版本,SSE 流式)
export async function streamAppChat(
  appId: string,
  body: { content: string; conversation_id?: string },
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/apps/${appId}/chat`, {
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
  await consumeSSE(res.body, handlers)
}

// ---- Agent ----
export interface BuiltinTool {
  type: string
  name: string
  description: string
  parameters: Record<string, unknown>
}

export interface AgentTool {
  id: string
  app_id: string
  type: string
  name: string
  description: string | null
  is_enabled: boolean
  config: Record<string, unknown>
  sort_order: number
  created_at: string
}

export interface AgentToolInput {
  type: string
  name?: string | null
  description?: string | null
  config?: Record<string, unknown>
}

export interface AgentThought {
  id: string
  conversation_id: string
  message_id: string | null
  kind: string // thought | tool_call | observation | answer
  content: string | null
  tool_name: string | null
  tool_input: Record<string, unknown> | null
  tool_output: string | null
  input_tokens: number
  output_tokens: number
  elapsed_ms: number | null
  sort_order: number
}

export function listBuiltinTools(appId: string) {
  return apiFetch<BuiltinTool[]>(`/api/apps/${appId}/agent/tools/catalog`)
}

export function listAgentTools(appId: string) {
  return apiFetch<AgentTool[]>(`/api/apps/${appId}/agent/tools`)
}

export function addAgentTool(appId: string, data: AgentToolInput) {
  return apiFetch<AgentTool>(`/api/apps/${appId}/agent/tools`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateAgentTool(
  appId: string,
  toolId: string,
  data: { name?: string; description?: string; is_enabled?: boolean; config?: Record<string, unknown> },
) {
  return apiFetch<AgentTool>(`/api/apps/${appId}/agent/tools/${toolId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteAgentTool(appId: string, toolId: string) {
  return apiFetch<void>(`/api/apps/${appId}/agent/tools/${toolId}`, { method: 'DELETE' })
}

export function getMessageThoughts(conversationId: string, messageId: string) {
  return apiFetch<AgentThought[]>(
    `/api/conversations/${conversationId}/messages/${messageId}/thoughts`,
  )
}

// Agent 调试运行的 SSE 轨迹步骤
export interface AgentStepEvent {
  type: 'meta' | 'thought' | 'tool_call' | 'observation' | 'answer' | 'done' | 'error'
  conversation_id?: string
  model?: string
  content?: string
  tool?: string
  input?: Record<string, unknown>
  output?: string
  message_id?: string
  message?: string
}

export async function streamAgentChat(
  appId: string,
  body: { content: string; conversation_id?: string },
  onEvent: (evt: AgentStepEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/apps/${appId}/agent/chat`, {
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
      onEvent(JSON.parse(line.slice(5).trim()))
    }
  }
}

// SSE 流读公共逻辑(对话页与应用调试窗共用)
async function consumeSSE(stream: ReadableStream<Uint8Array>, handlers: StreamHandlers) {
  const reader = stream.getReader()
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
