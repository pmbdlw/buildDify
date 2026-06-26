'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  type Conversation,
  getMessages,
  getToken,
  listConversations,
  streamChat,
} from '@/lib/api'

interface UIMessage {
  role: string
  content: string
}

export default function ChatPage() {
  const router = useRouter()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login')
      return
    }
    void refreshConversations()
  }, [router])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function refreshConversations() {
    try {
      setConversations(await listConversations())
    } catch {
      /* 忽略 */
    }
  }

  async function openConversation(id: string) {
    setActiveId(id)
    const msgs = await getMessages(id)
    setMessages(msgs.map((m) => ({ role: m.role, content: m.content })))
  }

  function newChat() {
    setActiveId(null)
    setMessages([])
  }

  async function send() {
    const content = input.trim()
    if (!content || streaming) return
    setInput('')
    setStreaming(true)
    setMessages((prev) => [...prev, { role: 'user', content }, { role: 'assistant', content: '' }])

    try {
      await streamChat(
        { content, conversation_id: activeId ?? undefined },
        {
          onMeta: (cid) => setActiveId(cid),
          onDelta: (text) =>
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                role: 'assistant',
                content: next[next.length - 1].content + text,
              }
              return next
            }),
          onDone: () => void refreshConversations(),
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

  return (
    <div className="flex h-screen bg-white text-gray-900">
      {/* 侧边栏:会话列表 */}
      <aside className="flex w-64 flex-col border-r border-gray-200 bg-gray-50">
        <div className="p-3">
          <button
            onClick={newChat}
            className="w-full rounded-lg bg-gray-900 py-2 text-sm font-medium text-white hover:bg-gray-800"
          >
            + 新对话
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 pb-2">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => openConversation(c.id)}
              className={`mb-1 w-full truncate rounded-lg px-3 py-2 text-left text-sm ${
                activeId === c.id ? 'bg-gray-200 font-medium' : 'hover:bg-gray-100'
              }`}
              title={c.title}
            >
              {c.title || '新对话'}
            </button>
          ))}
          {conversations.length === 0 && (
            <p className="px-3 py-2 text-sm text-gray-400">还没有对话</p>
          )}
        </nav>
      </aside>

      {/* 主区:消息 + 输入 */}
      <main className="flex flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-2xl space-y-4">
            {messages.length === 0 && (
              <p className="mt-20 text-center text-gray-400">发一条消息开始对话</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div
                  className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                    m.role === 'user'
                      ? 'bg-gray-900 text-white'
                      : 'bg-gray-100 text-gray-900'
                  } max-w-[80%]`}
                >
                  {m.content || (streaming ? '…' : '')}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-gray-200 px-6 py-4">
          <div className="mx-auto flex max-w-2xl items-end gap-2">
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
              placeholder="输入消息,Enter 发送 / Shift+Enter 换行"
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
      </main>
    </div>
  )
}
