'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  type Dataset,
  type KbDocument,
  createDataset,
  getToken,
  listDatasets,
  listDocuments,
  uploadDocument,
} from '@/lib/api'

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  pending: { text: '待处理', cls: 'bg-gray-100 text-gray-600' },
  processing: { text: '处理中', cls: 'bg-amber-100 text-amber-700' },
  ready: { text: '就绪', cls: 'bg-green-100 text-green-700' },
  error: { text: '失败', cls: 'bg-red-100 text-red-700' },
}

export default function KnowledgePage() {
  const router = useRouter()
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [documents, setDocuments] = useState<KbDocument[]>([])
  const [newName, setNewName] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!getToken()) {
      router.replace('/login')
      return
    }
    void refreshDatasets()
  }, [router])

  // 有文档处于 pending/processing 时轮询刷新状态
  useEffect(() => {
    if (!activeId) return
    const pendingExists = documents.some((d) => d.status === 'pending' || d.status === 'processing')
    if (!pendingExists) return
    const t = setInterval(() => void refreshDocuments(activeId), 2000)
    return () => clearInterval(t)
  }, [activeId, documents])

  async function refreshDatasets() {
    try {
      const ds = await listDatasets()
      setDatasets(ds)
      if (!activeId && ds.length > 0) void selectDataset(ds[0].id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function refreshDocuments(datasetId: string) {
    try {
      setDocuments(await listDocuments(datasetId))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function selectDataset(id: string) {
    setActiveId(id)
    await refreshDocuments(id)
  }

  async function handleCreate() {
    const name = newName.trim()
    if (!name) return
    try {
      const ds = await createDataset(name)
      setNewName('')
      setDatasets((prev) => [ds, ...prev])
      void selectDataset(ds.id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !activeId) return
    setUploading(true)
    setError('')
    try {
      await uploadDocument(activeId, file)
      await refreshDocuments(activeId)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="flex h-screen bg-white text-gray-900">
      {/* 侧边栏:知识库列表 */}
      <aside className="flex w-64 flex-col border-r border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <span className="text-sm font-semibold">知识库</span>
          <div className="flex gap-3 text-xs text-gray-500">
            <Link href="/apps" className="hover:text-gray-900">
              应用
            </Link>
            <Link href="/chat" className="hover:text-gray-900">
              去对话 →
            </Link>
          </div>
        </div>
        <div className="flex gap-2 p-3">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="新建知识库名"
            className="flex-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-gray-900"
          />
          <button
            onClick={handleCreate}
            className="rounded-lg bg-gray-900 px-3 text-sm text-white hover:bg-gray-800"
          >
            +
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 pb-2">
          {datasets.map((d) => (
            <button
              key={d.id}
              onClick={() => void selectDataset(d.id)}
              className={`mb-1 w-full truncate rounded-lg px-3 py-2 text-left text-sm ${
                activeId === d.id ? 'bg-gray-200 font-medium' : 'hover:bg-gray-100'
              }`}
            >
              {d.name}
            </button>
          ))}
          {datasets.length === 0 && (
            <p className="px-3 py-2 text-sm text-gray-400">还没有知识库</p>
          )}
        </nav>
      </aside>

      {/* 主区:文档列表 + 上传 */}
      <main className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h1 className="text-lg font-semibold">
            {activeId ? datasets.find((d) => d.id === activeId)?.name : '选择或新建知识库'}
          </h1>
          {activeId && (
            <label className="cursor-pointer rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800">
              {uploading ? '上传中…' : '上传文档'}
              <input
                ref={fileRef}
                type="file"
                accept=".txt,.md,.markdown,.pdf"
                onChange={handleUpload}
                disabled={uploading}
                className="hidden"
              />
            </label>
          )}
        </div>

        {error && <p className="px-6 pt-3 text-sm text-red-600">⚠️ {error}</p>}

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {!activeId && <p className="text-gray-400">从左侧选择一个知识库,或新建一个。</p>}
          {activeId && documents.length === 0 && (
            <p className="text-gray-400">还没有文档,点右上角上传 TXT / MD / PDF。</p>
          )}
          <ul className="space-y-2">
            {documents.map((doc) => {
              const s = STATUS_LABEL[doc.status] ?? STATUS_LABEL.pending
              return (
                <li
                  key={doc.id}
                  className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{doc.name}</p>
                    <p className="text-xs text-gray-500">
                      {doc.file_type.toUpperCase()} · {doc.char_count} 字 · {doc.segment_count} 分段
                      {doc.error ? ` · ${doc.error}` : ''}
                    </p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs ${s.cls}`}>
                    {s.text}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      </main>
    </div>
  )
}
