'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { type ColDef } from 'ag-grid-community'
import { type WorkflowListItem, createWorkflow, listWorkflows } from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import { formatDateTime } from '@/lib/format'
import TopNav from '@/components/TopNav'
import DataGrid from '@/components/DataGrid'
import { EmptyState, ErrorBanner, PageLoading } from '@/components/States'

export default function WorkflowsPage() {
  const router = useRouter()
  const { ready, user } = useRequireAuth()
  const [items, setItems] = useState<WorkflowListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!ready) return
    let alive = true
    void (async () => {
      try {
        const data = await listWorkflows()
        if (alive) setItems(data)
      } catch (e) {
        if (alive) setError((e as Error).message)
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [ready])

  async function handleCreate() {
    const name = newName.trim()
    if (!name || creating) return
    setCreating(true)
    setError('')
    try {
      const wf = await createWorkflow(name)
      setNewName('')
      router.push(`/workflows/${wf.id}`)
    } catch (e) {
      setError((e as Error).message)
      setCreating(false)
    }
  }

  const columnDefs = useMemo<ColDef<WorkflowListItem>[]>(
    () => [
      { headerName: '名称', field: 'name', flex: 2, minWidth: 160 },
      { headerName: '版本', field: 'version', maxWidth: 110, valueFormatter: (p) => `v${p.value}` },
      {
        headerName: '描述',
        field: 'description',
        flex: 2,
        valueFormatter: (p) => p.value || '可视化节点编排',
      },
      {
        headerName: '更新时间',
        field: 'updated_at',
        maxWidth: 180,
        valueFormatter: (p) => formatDateTime(p.value),
      },
    ],
    [],
  )

  if (!ready) return <PageLoading text="校验登录态…" full />

  return (
    <div className="flex h-screen flex-col bg-gray-50 text-gray-900">
      <TopNav user={user} />
      <main className="mx-auto w-full max-w-5xl flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-5 flex items-center justify-between">
          <h1 className="text-lg font-semibold">工作流</h1>
          <div className="flex gap-2">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              placeholder="新建工作流名称"
              className="w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-gray-900"
            />
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="rounded-lg bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            >
              + 新建
            </button>
          </div>
        </div>

        <ErrorBanner message={error} />

        {loading ? (
          <PageLoading />
        ) : items.length === 0 ? (
          <EmptyState text="还没有工作流,新建一个并在画布上编排节点。" />
        ) : (
          <DataGrid<WorkflowListItem>
            rowData={items}
            columnDefs={columnDefs}
            onRowClicked={(row) => router.push(`/workflows/${row.id}`)}
          />
        )}
      </main>
    </div>
  )
}
