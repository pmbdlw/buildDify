'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { type ColDef } from 'ag-grid-community'
import {
  type Dataset,
  type KbDocument,
  createDataset,
  listDatasets,
  listDocuments,
  uploadDocument,
} from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import TopNav from '@/components/TopNav'
import DataGrid from '@/components/DataGrid'
import { EmptyState, ErrorBanner, PageLoading } from '@/components/States'

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  pending: { text: '待处理', cls: 'bg-gray-100 text-gray-600' },
  processing: { text: '处理中', cls: 'bg-amber-100 text-amber-700' },
  ready: { text: '就绪', cls: 'bg-green-100 text-green-700' },
  error: { text: '失败', cls: 'bg-red-100 text-red-700' },
}

export default function KnowledgePage() {
  const { ready, user } = useRequireAuth()
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [documents, setDocuments] = useState<KbDocument[]>([])
  const [newName, setNewName] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!ready) return
    void refreshDatasets()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready])

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

  const columnDefs = useMemo<ColDef<KbDocument>[]>(
    () => [
      { headerName: '文档', field: 'name', flex: 2, minWidth: 180 },
      {
        headerName: '类型',
        field: 'file_type',
        maxWidth: 100,
        valueFormatter: (p) => (p.value || '').toUpperCase(),
      },
      {
        headerName: '状态',
        field: 'status',
        maxWidth: 110,
        cellRenderer: (p: { value: string }) => {
          const s = STATUS_LABEL[p.value] ?? STATUS_LABEL.pending
          return <span className={`rounded-full px-2 py-0.5 text-xs ${s.cls}`}>{s.text}</span>
        },
      },
      { headerName: '字数', field: 'char_count', maxWidth: 110 },
      { headerName: '分段', field: 'segment_count', maxWidth: 100 },
      { headerName: '错误', field: 'error', flex: 1, valueFormatter: (p) => p.value || '' },
    ],
    [],
  )

  if (!ready) return <PageLoading text="校验登录态…" full />

  const activeName = activeId ? datasets.find((d) => d.id === activeId)?.name : null

  return (
    <div className="flex h-screen flex-col bg-white text-gray-900">
      <TopNav user={user} />
      <div className="flex min-h-0 flex-1">
        {/* 侧边栏:知识库列表 */}
        <aside className="flex w-64 flex-col border-r border-gray-200 bg-gray-50">
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
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <h1 className="text-lg font-semibold">{activeName ?? '选择或新建知识库'}</h1>
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

          <div className="flex min-h-0 flex-1 flex-col px-6 py-4">
            <ErrorBanner message={error} />
            {!activeId ? (
              <EmptyState text="从左侧选择一个知识库,或新建一个。" />
            ) : documents.length === 0 ? (
              <EmptyState text="还没有文档,点右上角上传 TXT / MD / PDF。" />
            ) : (
              <div className="min-h-0 flex-1">
                <DataGrid<KbDocument>
                  rowData={documents}
                  columnDefs={columnDefs}
                  height="100%"
                />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
