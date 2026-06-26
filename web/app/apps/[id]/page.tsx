'use client'

import { use, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  type AgentTool,
  type ApiKey,
  type App,
  type AppConfig,
  type BuiltinTool,
  type Citation,
  type Dataset,
  addAgentTool,
  createApiKey,
  deleteAgentTool,
  deleteApp,
  getApp,
  getAppConfig,
  listAgentTools,
  listApiKeys,
  listBuiltinTools,
  listDatasets,
  publishApp,
  revokeApiKey,
  saveAppConfig,
  streamAgentChat,
  streamAppChat,
  updateAgentTool,
} from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'

interface TraceStep {
  kind: string // thought | tool_call | observation
  content?: string
  tool?: string
  input?: Record<string, unknown>
  output?: string
}

interface UIMessage {
  role: string
  content: string
  citations?: Citation[]
  steps?: TraceStep[]
}

export default function AppDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: appId } = use(params)
  const router = useRouter()
  const { ready } = useRequireAuth()

  const [app, setApp] = useState<App | null>(null)
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState('')

  // 配置表单
  const [model, setModel] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [temperature, setTemperature] = useState('')
  const [maxTokens, setMaxTokens] = useState(1024)
  const [datasetId, setDatasetId] = useState('')
  const [version, setVersion] = useState(0)

  // 调试窗
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [convId, setConvId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // API Keys
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [revealedKey, setRevealedKey] = useState('')

  // Agent 工具
  const [agentTools, setAgentTools] = useState<AgentTool[]>([])
  const [catalog, setCatalog] = useState<BuiltinTool[]>([])
  const isAgent = app?.mode === 'agent'

  useEffect(() => {
    if (!ready) return
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId, ready])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function load() {
    try {
      const [a, cfg, ds, ks] = await Promise.all([
        getApp(appId),
        getAppConfig(appId),
        listDatasets().catch(() => [] as Dataset[]),
        listApiKeys(appId).catch(() => [] as ApiKey[]),
      ])
      setApp(a)
      applyConfig(cfg)
      setDatasets(ds)
      setKeys(ks)
      if (a.mode === 'agent') {
        const [tools, cat] = await Promise.all([
          listAgentTools(appId).catch(() => [] as AgentTool[]),
          listBuiltinTools(appId).catch(() => [] as BuiltinTool[]),
        ])
        setAgentTools(tools)
        setCatalog(cat)
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleAddTool(type: string) {
    setError('')
    try {
      const tool = await addAgentTool(appId, { type })
      setAgentTools((prev) => [...prev, tool])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleToggleTool(tool: AgentTool) {
    try {
      const updated = await updateAgentTool(appId, tool.id, { is_enabled: !tool.is_enabled })
      setAgentTools((prev) => prev.map((t) => (t.id === tool.id ? updated : t)))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleToolDataset(tool: AgentTool, dsId: string) {
    try {
      const updated = await updateAgentTool(appId, tool.id, {
        config: { ...tool.config, dataset_id: dsId || undefined },
      })
      setAgentTools((prev) => prev.map((t) => (t.id === tool.id ? updated : t)))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleDeleteTool(toolId: string) {
    try {
      await deleteAgentTool(appId, toolId)
      setAgentTools((prev) => prev.filter((t) => t.id !== toolId))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function applyConfig(cfg: AppConfig) {
    setModel(cfg.model ?? '')
    setSystemPrompt(cfg.system_prompt ?? '')
    setTemperature(cfg.temperature == null ? '' : String(cfg.temperature))
    setMaxTokens(cfg.max_tokens)
    setDatasetId(cfg.dataset_id ?? '')
    setVersion(cfg.version)
  }

  async function handleSave() {
    setSaving(true)
    setError('')
    try {
      const cfg = await saveAppConfig(appId, {
        model: model.trim() || null,
        system_prompt: systemPrompt.trim() || null,
        temperature: temperature.trim() === '' ? null : Number(temperature),
        max_tokens: maxTokens,
        dataset_id: datasetId || null,
      })
      applyConfig(cfg)
      setSavedAt(`已保存为 v${cfg.version}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handlePublish() {
    setError('')
    try {
      const updated = await publishApp(appId)
      setApp(updated)
      setSavedAt('已发布最新配置')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleDelete() {
    if (!confirm('确定删除该应用?')) return
    try {
      await deleteApp(appId)
      router.push('/apps')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function patchLast(patch: (m: UIMessage) => UIMessage) {
    setMessages((prev) => {
      const next = [...prev]
      next[next.length - 1] = patch(next[next.length - 1])
      return next
    })
  }

  async function send() {
    const content = input.trim()
    if (!content || streaming) return
    setInput('')
    setStreaming(true)
    setMessages((prev) => [
      ...prev,
      { role: 'user', content },
      { role: 'assistant', content: '', steps: isAgent ? [] : undefined },
    ])
    if (isAgent) {
      await sendAgent(content)
      return
    }
    try {
      await streamAppChat(
        appId,
        { content, conversation_id: convId ?? undefined },
        {
          onMeta: (cid, _model, citations) => {
            setConvId(cid)
            if (citations.length > 0)
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { ...next[next.length - 1], citations }
                return next
              })
          },
          onDelta: (text) =>
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                ...next[next.length - 1],
                role: 'assistant',
                content: next[next.length - 1].content + text,
              }
              return next
            }),
          onError: (msg) =>
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = { role: 'assistant', content: `⚠️ ${msg}` }
              return next
            }),
        },
      )
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content: `⚠️ ${(e as Error).message}` }
        return next
      })
    } finally {
      setStreaming(false)
    }
  }

  async function sendAgent(content: string) {
    try {
      await streamAgentChat(appId, { content, conversation_id: convId ?? undefined }, (evt) => {
        if (evt.type === 'meta') {
          if (evt.conversation_id) setConvId(evt.conversation_id)
        } else if (evt.type === 'thought') {
          patchLast((m) => ({ ...m, steps: [...(m.steps ?? []), { kind: 'thought', content: evt.content }] }))
        } else if (evt.type === 'tool_call') {
          patchLast((m) => ({
            ...m,
            steps: [...(m.steps ?? []), { kind: 'tool_call', tool: evt.tool, input: evt.input }],
          }))
        } else if (evt.type === 'observation') {
          patchLast((m) => ({
            ...m,
            steps: [...(m.steps ?? []), { kind: 'observation', tool: evt.tool, output: evt.output }],
          }))
        } else if (evt.type === 'answer') {
          patchLast((m) => ({ ...m, content: evt.content ?? '' }))
        } else if (evt.type === 'error') {
          patchLast((m) => ({ ...m, content: `⚠️ ${evt.message}` }))
        }
      })
    } catch (e) {
      patchLast(() => ({ role: 'assistant', content: `⚠️ ${(e as Error).message}` }))
    } finally {
      setStreaming(false)
    }
  }

  function resetDebug() {
    setConvId(null)
    setMessages([])
  }

  async function handleCreateKey() {
    setError('')
    try {
      const created = await createApiKey(appId, newKeyName.trim())
      setNewKeyName('')
      setRevealedKey(created.key)
      setKeys((prev) => [created, ...prev])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleRevoke(keyId: string) {
    if (!confirm('吊销该 API Key?使用它的调用将立即失效。')) return
    try {
      await revokeApiKey(appId, keyId)
      setKeys((prev) => prev.filter((k) => k.id !== keyId))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!app) {
    return (
      <div className="flex h-screen items-center justify-center text-gray-400">
        {error ? `⚠️ ${error}` : '加载中…'}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <Link href="/apps" className="text-sm text-gray-500 hover:text-gray-900">
            ← 应用
          </Link>
          <h1 className="text-lg font-semibold">{app.name}</h1>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs ${
              app.status === 'published'
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-600'
            }`}
          >
            {app.status === 'published' ? '已发布' : '草稿'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {savedAt && <span className="text-xs text-gray-400">{savedAt}</span>}
          <button
            onClick={handlePublish}
            className="rounded-lg border border-gray-900 px-4 py-1.5 text-sm font-medium text-gray-900 hover:bg-gray-100"
          >
            发布
          </button>
          <button
            onClick={handleDelete}
            className="text-sm text-red-500 hover:text-red-700"
          >
            删除
          </button>
        </div>
      </header>

      {error && <p className="px-6 pt-3 text-sm text-red-600">⚠️ {error}</p>}

      <main className="mx-auto grid max-w-6xl grid-cols-1 gap-6 px-6 py-6 lg:grid-cols-2">
        {/* 左:配置 + API Key */}
        <section className="space-y-6">
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold">应用配置</h2>
              <span className="text-xs text-gray-400">当前 v{version}</span>
            </div>
            <div className="space-y-4">
              <label className="block">
                <span className="text-sm text-gray-600">模型</span>
                <input
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="留空用平台默认(如 claude-sonnet-4-6)"
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
                />
              </label>
              <label className="block">
                <span className="text-sm text-gray-600">系统提示词(Prompt)</span>
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  rows={5}
                  placeholder="设定应用的角色与行为,例如:你是一个专业的客服助手……"
                  className="mt-1 w-full resize-y rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
                />
              </label>
              <div className="grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="text-sm text-gray-600">温度(0–2)</span>
                  <input
                    value={temperature}
                    onChange={(e) => setTemperature(e.target.value)}
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    placeholder="默认"
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
                  />
                </label>
                <label className="block">
                  <span className="text-sm text-gray-600">最大 Tokens</span>
                  <input
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(Number(e.target.value) || 1024)}
                    type="number"
                    min="1"
                    className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
                  />
                </label>
              </div>
              <label className="block">
                <span className="text-sm text-gray-600">绑定知识库(RAG)</span>
                <select
                  value={datasetId}
                  onChange={(e) => setDatasetId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
                >
                  <option value="">不绑定</option>
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={handleSave}
                disabled={saving}
                className="w-full rounded-lg bg-gray-900 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {saving ? '保存中…' : '保存为新版本'}
              </button>
            </div>
          </div>

          {/* Agent 工具(仅 agent 应用)*/}
          {isAgent && (
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <h2 className="mb-1 font-semibold">Agent 工具</h2>
              <p className="mb-4 text-xs text-gray-400">
                启用的工具会作为 function calling 暴露给模型,由模型在 ReAct 推理中自主调用。
              </p>
              <div className="mb-3 flex flex-wrap gap-2">
                {catalog
                  .filter((c) => !agentTools.some((t) => t.type === c.type))
                  .map((c) => (
                    <button
                      key={c.type}
                      onClick={() => handleAddTool(c.type)}
                      title={c.description}
                      className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:border-gray-900"
                    >
                      + {c.name}
                    </button>
                  ))}
              </div>
              <ul className="space-y-2">
                {agentTools.map((t) => (
                  <li key={t.id} className="rounded-lg border border-gray-200 px-3 py-2 text-sm">
                    <div className="flex items-center justify-between">
                      <div className="min-w-0">
                        <p className="truncate font-medium">{t.name}</p>
                        <p className="text-xs text-gray-400">{t.type}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <label className="flex items-center gap-1 text-xs text-gray-500">
                          <input
                            type="checkbox"
                            checked={t.is_enabled}
                            onChange={() => handleToggleTool(t)}
                          />
                          启用
                        </label>
                        <button
                          onClick={() => handleDeleteTool(t.id)}
                          className="text-xs text-red-500 hover:text-red-700"
                        >
                          移除
                        </button>
                      </div>
                    </div>
                    {t.type === 'knowledge_retrieval' && (
                      <select
                        value={(t.config?.dataset_id as string) ?? ''}
                        onChange={(e) => handleToolDataset(t, e.target.value)}
                        className="mt-2 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-xs outline-none focus:border-gray-900"
                      >
                        <option value="">用应用绑定的知识库</option>
                        {datasets.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </li>
                ))}
                {agentTools.length === 0 && (
                  <p className="text-sm text-gray-400">还没有工具,从上方添加。</p>
                )}
              </ul>
            </div>
          )}

          {/* API Key 管理 */}
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h2 className="mb-1 font-semibold">API Key</h2>
            <p className="mb-4 text-xs text-gray-400">
              用于对外调用 <code className="rounded bg-gray-100 px-1">POST /v1/apps/{appId}/chat</code>
              (需先发布)。密钥明文仅在创建时显示一次。
            </p>
            <div className="mb-3 flex gap-2">
              <input
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="密钥名称(可选)"
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
              />
              <button
                onClick={handleCreateKey}
                className="rounded-lg bg-gray-900 px-4 text-sm text-white hover:bg-gray-800"
              >
                生成
              </button>
            </div>
            {revealedKey && (
              <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                <p className="mb-1 text-xs text-amber-700">请立即复制并妥善保存,关闭后无法再查看:</p>
                <code className="block break-all text-xs text-amber-900">{revealedKey}</code>
                <button
                  onClick={() => setRevealedKey('')}
                  className="mt-2 text-xs text-amber-700 hover:text-amber-900"
                >
                  我已保存,关闭
                </button>
              </div>
            )}
            <ul className="space-y-2">
              {keys.map((k) => (
                <li
                  key={k.id}
                  className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{k.name || '未命名'}</p>
                    <p className="text-xs text-gray-400">
                      {k.key_prefix}… · {k.last_used_at ? '已使用' : '未使用'}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRevoke(k.id)}
                    className="shrink-0 text-xs text-red-500 hover:text-red-700"
                  >
                    吊销
                  </button>
                </li>
              ))}
              {keys.length === 0 && <p className="text-sm text-gray-400">还没有 API Key</p>}
            </ul>
          </div>
        </section>

        {/* 右:调试对话窗 */}
        <section className="flex h-[calc(100vh-9rem)] flex-col rounded-xl border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
            <h2 className="font-semibold">调试对话</h2>
            <button onClick={resetDebug} className="text-xs text-gray-500 hover:text-gray-900">
              清空重开
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">
            <div className="space-y-4">
              {messages.length === 0 && (
                <p className="mt-16 text-center text-sm text-gray-400">
                  保存配置后,在此试聊验证效果。
                </p>
              )}
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={m.role === 'user' ? 'flex justify-end' : 'flex flex-col items-start'}
                >
                  {m.steps && m.steps.length > 0 && (
                    <div className="mb-2 max-w-[85%] space-y-1.5">
                      {m.steps.map((s, si) => (
                        <div key={si} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs">
                          {s.kind === 'thought' && (
                            <p className="whitespace-pre-wrap text-gray-500">💭 {s.content}</p>
                          )}
                          {s.kind === 'tool_call' && (
                            <details>
                              <summary className="cursor-pointer select-none text-blue-600">
                                🔧 调用工具 <span className="font-medium">{s.tool}</span>
                              </summary>
                              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-gray-500">
                                {JSON.stringify(s.input, null, 2)}
                              </pre>
                            </details>
                          )}
                          {s.kind === 'observation' && (
                            <details>
                              <summary className="cursor-pointer select-none text-emerald-600">
                                📥 {s.tool} 返回
                              </summary>
                              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-gray-500">
                                {s.output}
                              </pre>
                            </details>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  <div
                    className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                      m.role === 'user' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-900'
                    } max-w-[85%]`}
                  >
                    {m.content ||
                      (streaming
                        ? m.steps && m.steps.length > 0
                          ? '推理中…'
                          : '…'
                        : '')}
                  </div>
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-2 max-w-[85%] space-y-1">
                      <p className="text-xs font-medium text-gray-400">引用来源</p>
                      {m.citations.map((c) => (
                        <details
                          key={c.index}
                          className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-600"
                        >
                          <summary className="cursor-pointer select-none">
                            [{c.index}] 相关度 {(c.score * 100).toFixed(0)}%
                          </summary>
                          <p className="mt-1 whitespace-pre-wrap text-gray-500">{c.content}</p>
                        </details>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </div>
          <div className="border-t border-gray-200 px-5 py-3">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send()
                  }
                }}
                rows={1}
                placeholder="输入消息调试,Enter 发送"
                className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
              />
              <button
                onClick={() => void send()}
                disabled={streaming || !input.trim()}
                className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {streaming ? '…' : '发送'}
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
