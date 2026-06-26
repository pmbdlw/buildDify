'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { type App, createApp, getToken, listApps } from '@/lib/api'

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  draft: { text: '草稿', cls: 'bg-gray-100 text-gray-600' },
  published: { text: '已发布', cls: 'bg-green-100 text-green-700' },
}

export default function AppsPage() {
  const router = useRouter()
  const [apps, setApps] = useState<App[]>([])
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login')
      return
    }
    void refresh()
  }, [router])

  async function refresh() {
    try {
      setApps(await listApps())
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleCreate() {
    const name = newName.trim()
    if (!name || creating) return
    setCreating(true)
    setError('')
    try {
      const app = await createApp(name)
      setNewName('')
      router.push(`/apps/${app.id}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <h1 className="text-lg font-semibold">应用</h1>
        <nav className="flex gap-4 text-sm text-gray-500">
          <Link href="/chat" className="hover:text-gray-900">
            对话
          </Link>
          <Link href="/knowledge" className="hover:text-gray-900">
            知识库
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-6 flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="新建应用名称"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newName.trim()}
            className="rounded-lg bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            + 新建应用
          </button>
        </div>

        {error && <p className="mb-4 text-sm text-red-600">⚠️ {error}</p>}

        {apps.length === 0 ? (
          <p className="mt-16 text-center text-gray-400">还没有应用,新建一个 Chatbot 应用开始。</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {apps.map((app) => {
              const s = STATUS_LABEL[app.status] ?? STATUS_LABEL.draft
              return (
                <li key={app.id}>
                  <Link
                    href={`/apps/${app.id}`}
                    className="block rounded-xl border border-gray-200 bg-white p-4 transition hover:border-gray-400 hover:shadow-sm"
                  >
                    <div className="flex items-start justify-between">
                      <p className="truncate font-medium">{app.name}</p>
                      <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs ${s.cls}`}>
                        {s.text}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-sm text-gray-500">
                      {app.description || 'Chatbot 应用'}
                    </p>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </main>
    </div>
  )
}
