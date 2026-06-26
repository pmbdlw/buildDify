'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  type Dataset,
  type NodeRun,
  type WfGraph,
  type WorkflowRun,
  getWorkflow,
  listDatasets,
  runWorkflow,
  saveWorkflow,
} from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'

// ---- 节点类型元信息(标签 / 颜色 / 是否可增删)----
type NodeType = 'start' | 'end' | 'llm' | 'knowledge_retrieval' | 'condition' | 'code' | 'template'

const NODE_META: Record<NodeType, { label: string; color: string; addable: boolean }> = {
  start: { label: '开始', color: '#16a34a', addable: false },
  end: { label: '结束', color: '#dc2626', addable: false },
  llm: { label: 'LLM', color: '#7c3aed', addable: true },
  knowledge_retrieval: { label: '知识检索', color: '#0891b2', addable: true },
  condition: { label: '条件', color: '#d97706', addable: true },
  code: { label: '代码', color: '#475569', addable: true },
  template: { label: '模板', color: '#2563eb', addable: true },
}

const STATUS_COLOR: Record<string, string> = {
  succeeded: '#16a34a',
  failed: '#dc2626',
  skipped: '#9ca3af',
  running: '#d97706',
}

type FlowNode = Node<Record<string, unknown>>

// ---- 自定义节点渲染:展示类型标签 + 运行状态边框 + 连接点 ----
function FlowNodeView({ data, type, selected }: NodeProps) {
  const meta = NODE_META[(type as NodeType) ?? 'llm'] ?? NODE_META.llm
  const status = (data.__status as string | undefined) ?? ''
  const label = (data.label as string) || meta.label
  const borderColor = status ? STATUS_COLOR[status] : selected ? '#111827' : '#e5e7eb'
  const isCondition = type === 'condition'
  const isStart = type === 'start'
  const isEnd = type === 'end'
  return (
    <div
      className="rounded-lg border-2 bg-white px-3 py-2 text-xs shadow-sm"
      style={{ borderColor, minWidth: 132 }}
    >
      {!isStart && <Handle type="target" position={Position.Left} />}
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: meta.color }} />
        <span className="font-medium text-gray-800">{meta.label}</span>
        {status && (
          <span className="ml-auto text-[10px]" style={{ color: STATUS_COLOR[status] }}>
            {status === 'succeeded'
              ? '✓'
              : status === 'failed'
                ? '✕'
                : status === 'skipped'
                  ? '—'
                  : '…'}
          </span>
        )}
      </div>
      <div className="mt-0.5 truncate text-gray-500">{label}</div>
      {isCondition ? (
        <>
          <Handle id="true" type="source" position={Position.Right} style={{ top: '35%' }} />
          <Handle id="false" type="source" position={Position.Right} style={{ top: '70%' }} />
          <div className="mt-1 flex justify-end gap-2 text-[9px] text-gray-400">
            <span>真</span>
            <span>假</span>
          </div>
        </>
      ) : (
        !isEnd && <Handle type="source" position={Position.Right} />
      )}
    </div>
  )
}

// graph 里的节点 type 存在 data 之外;React Flow 用统一 nodeType 'flowNode' 渲染,
// 真实业务类型放 node.type(自定义),渲染组件读 props.type。
function toFlowNodes(graph: WfGraph): FlowNode[] {
  return (graph.nodes ?? []).map((n) => ({
    id: n.id,
    type: n.type, // 业务类型直接作为 React Flow 节点 type,映射到同一个渲染组件
    position: n.position ?? { x: 0, y: 0 },
    data: { ...n.data },
  }))
}

function toGraph(nodes: FlowNode[], edges: Edge[]): WfGraph {
  return {
    nodes: nodes.map((n) => {
      const data = { ...n.data }
      delete data.__status // 运行态不入库
      return { id: n.id, type: n.type as string, position: n.position, data }
    }),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? null,
    })),
  }
}

const OPERATORS: { value: string; label: string }[] = [
  { value: 'eq', label: '等于' },
  { value: 'ne', label: '不等于' },
  { value: 'contains', label: '包含' },
  { value: 'not_contains', label: '不包含' },
  { value: 'gt', label: '大于' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '小于' },
  { value: 'lte', label: '≤' },
  { value: 'empty', label: '为空' },
  { value: 'not_empty', label: '非空' },
]

let _idSeq = 0
function newNodeId(type: string): string {
  _idSeq += 1
  return `${type}_${Date.now().toString(36)}_${_idSeq}`
}

// 用统一的所有业务类型注册到 nodeTypes（都用同一个渲染组件）
const ALL_NODE_TYPES = Object.keys(NODE_META).reduce(
  (acc, t) => ({ ...acc, [t]: FlowNodeView }),
  {} as Record<string, typeof FlowNodeView>,
)

export default function WorkflowEditorPage() {
  const { ready } = useRequireAuth()
  const params = useParams<{ id: string }>()
  const wfId = params.id

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [name, setName] = useState('')
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [running, setRunning] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [inputValues, setInputValues] = useState<Record<string, string>>({})

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedId) ?? null,
    [nodes, selectedId],
  )

  // start 节点声明的输入变量(用于运行表单)
  const startVariables = useMemo(() => {
    const start = nodes.find((n) => n.type === 'start')
    return ((start?.data.variables as { name: string }[]) ?? []).filter((v) => v?.name)
  }, [nodes])

  useEffect(() => {
    if (!ready) return
    void (async () => {
      try {
        const [wf, ds] = await Promise.all([getWorkflow(wfId), listDatasets().catch(() => [])])
        setName(wf.name)
        setNodes(toFlowNodes(wf.graph))
        setEdges(
          (wf.graph.edges ?? []).map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle ?? undefined,
            markerEnd: { type: MarkerType.ArrowClosed },
          })),
        )
        setDatasets(ds)
      } catch (e) {
        setError((e as Error).message)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wfId, ready])

  const onConnect = useCallback(
    (conn: Connection) =>
      setEdges((eds) =>
        addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed } }, eds),
      ),
    [setEdges],
  )

  function addNode(type: NodeType) {
    const id = newNodeId(type)
    setNodes((ns) => {
      // 按已有节点数做级联偏移,避免新节点叠在一起(确定性,不用随机)
      const k = ns.length
      const node: FlowNode = {
        id,
        type,
        position: { x: 300 + (k % 4) * 60, y: 120 + (k % 6) * 70 },
        data: defaultData(type),
      }
      return [...ns, node]
    })
    setSelectedId(id)
  }

  function updateNodeData(id: string, patch: Record<string, unknown>) {
    setNodes((ns) =>
      ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)),
    )
  }

  function removeSelected() {
    if (!selectedNode) return
    if (selectedNode.type === 'start' || selectedNode.type === 'end') {
      setToast('开始/结束节点不可删除')
      return
    }
    const id = selectedNode.id
    setNodes((ns) => ns.filter((n) => n.id !== id))
    setEdges((es) => es.filter((e) => e.source !== id && e.target !== id))
    setSelectedId(null)
  }

  async function handleSave() {
    setSaving(true)
    setError('')
    try {
      await saveWorkflow(wfId, { name, graph: toGraph(nodes, edges) })
      setToast('已保存')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleRun() {
    setRunning(true)
    setError('')
    setRun(null)
    try {
      // 先保存当前画布,确保运行的是最新版
      await saveWorkflow(wfId, { name, graph: toGraph(nodes, edges) })
      const inputs: Record<string, unknown> = {}
      for (const v of startVariables) inputs[v.name] = inputValues[v.name] ?? ''
      const result = await runWorkflow(wfId, inputs)
      setRun(result)
      setSelectedId(null)
      // 把节点状态染色
      const statusById: Record<string, string> = {}
      for (const nr of result.node_runs) statusById[nr.node_id] = nr.status
      setNodes((ns) =>
        ns.map((n) => ({ ...n, data: { ...n.data, __status: statusById[n.id] ?? '' } })),
      )
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 2000)
    return () => clearTimeout(t)
  }, [toast])

  return (
    <div className="flex h-screen flex-col bg-gray-50 text-gray-900">
      <header className="flex items-center gap-3 border-b border-gray-200 bg-white px-5 py-3">
        <Link href="/workflows" className="text-sm text-gray-500 hover:text-gray-900">
          ← 工作流
        </Link>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="rounded-md border border-transparent px-2 py-1 text-sm font-medium hover:border-gray-200 focus:border-gray-900 focus:outline-none"
        />
        <div className="ml-auto flex items-center gap-2">
          {toast && <span className="text-xs text-green-600">{toast}</span>}
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm hover:bg-gray-100 disabled:opacity-50"
          >
            {saving ? '保存中…' : '保存'}
          </button>
          <button
            onClick={handleRun}
            disabled={running}
            className="rounded-lg bg-gray-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {running ? '运行中…' : '▶ 运行'}
          </button>
        </div>
      </header>

      {error && (
        <div className="border-b border-red-100 bg-red-50 px-5 py-2 text-sm text-red-600">
          ⚠️ {error}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* 左侧节点面板 */}
        <aside className="w-40 shrink-0 border-r border-gray-200 bg-white p-3">
          <p className="mb-2 text-xs font-medium text-gray-400">添加节点</p>
          <div className="flex flex-col gap-1.5">
            {(Object.keys(NODE_META) as NodeType[])
              .filter((t) => NODE_META[t].addable)
              .map((t) => (
                <button
                  key={t}
                  onClick={() => addNode(t)}
                  className="flex items-center gap-2 rounded-md border border-gray-200 px-2.5 py-1.5 text-left text-xs hover:border-gray-400 hover:bg-gray-50"
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: NODE_META[t].color }}
                  />
                  {NODE_META[t].label}
                </button>
              ))}
          </div>
        </aside>

        {/* 画布 */}
        <div className="min-w-0 flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={ALL_NODE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>

        {/* 右侧:节点配置 或 运行面板 */}
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-gray-200 bg-white p-4">
          {selectedNode ? (
            <ConfigPanel
              node={selectedNode}
              datasets={datasets}
              onChange={(patch) => updateNodeData(selectedNode.id, patch)}
              onClose={() => setSelectedId(null)}
              onDelete={removeSelected}
            />
          ) : (
            <RunPanel
              variables={startVariables}
              values={inputValues}
              onValueChange={(k, v) => setInputValues((s) => ({ ...s, [k]: v }))}
              run={run}
            />
          )}
        </aside>
      </div>
    </div>
  )
}

function defaultData(type: NodeType): Record<string, unknown> {
  switch (type) {
    case 'llm':
      return { label: 'LLM', prompt: '{{ start.query }}', system_prompt: '', max_tokens: 1024 }
    case 'knowledge_retrieval':
      return { label: '知识检索', dataset_id: '', query: '{{ start.query }}', top_k: 4 }
    case 'condition':
      return {
        label: '条件',
        logic: 'and',
        conditions: [{ variable: '{{ start.query }}', operator: 'not_empty', value: '' }],
      }
    case 'code':
      return {
        label: '代码',
        inputs: [{ name: 'x', value: '{{ start.query }}' }],
        code: "outputs = {'result': inputs['x']}",
      }
    case 'template':
      return { label: '模板', template: '{{ start.query }}' }
    default:
      return { label: NODE_META[type].label }
  }
}

// ---- 节点配置面板 ----
function ConfigPanel({
  node,
  datasets,
  onChange,
  onClose,
  onDelete,
}: {
  node: FlowNode
  datasets: Dataset[]
  onChange: (patch: Record<string, unknown>) => void
  onClose: () => void
  onDelete: () => void
}) {
  const type = node.type as NodeType
  const d = node.data
  const removable = type !== 'start' && type !== 'end'
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{NODE_META[type].label} 配置</h3>
        <button onClick={onClose} className="text-xs text-gray-400 hover:text-gray-700">
          关闭
        </button>
      </div>
      <Field label="节点名称">
        <input
          value={(d.label as string) ?? ''}
          onChange={(e) => onChange({ label: e.target.value })}
          className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
        />
      </Field>

      {type === 'start' && (
        <ListEditor
          label="输入变量"
          items={(d.variables as { name: string }[]) ?? []}
          render={(item, set) => (
            <input
              value={item.name ?? ''}
              onChange={(e) => set({ name: e.target.value })}
              placeholder="变量名,如 query"
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
            />
          )}
          empty={{ name: '' }}
          onChange={(variables) => onChange({ variables })}
        />
      )}

      {type === 'end' && (
        <ListEditor
          label="输出变量"
          items={(d.outputs as { name: string; value: string }[]) ?? []}
          render={(item, set) => (
            <div className="space-y-1">
              <input
                value={item.name ?? ''}
                onChange={(e) => set({ name: e.target.value })}
                placeholder="输出名"
                className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
              />
              <input
                value={item.value ?? ''}
                onChange={(e) => set({ value: e.target.value })}
                placeholder="值,如 {{ llm.text }}"
                className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
              />
            </div>
          )}
          empty={{ name: '', value: '' }}
          onChange={(outputs) => onChange({ outputs })}
        />
      )}

      {type === 'llm' && (
        <>
          <Field label="模型(留空用默认)">
            <input
              value={(d.model as string) ?? ''}
              onChange={(e) => onChange({ model: e.target.value })}
              placeholder="如 claude-sonnet-4-6"
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
            />
          </Field>
          <Field label="System Prompt">
            <textarea
              value={(d.system_prompt as string) ?? ''}
              onChange={(e) => onChange({ system_prompt: e.target.value })}
              rows={2}
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
            />
          </Field>
          <Field label="Prompt(支持 {{ 节点.字段 }})">
            <textarea
              value={(d.prompt as string) ?? ''}
              onChange={(e) => onChange({ prompt: e.target.value })}
              rows={4}
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
            />
          </Field>
          <Field label="max_tokens">
            <input
              type="number"
              value={(d.max_tokens as number) ?? 1024}
              onChange={(e) => onChange({ max_tokens: Number(e.target.value) })}
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
            />
          </Field>
        </>
      )}

      {type === 'knowledge_retrieval' && (
        <>
          <Field label="知识库">
            <select
              value={(d.dataset_id as string) ?? ''}
              onChange={(e) => onChange({ dataset_id: e.target.value })}
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
            >
              <option value="">— 选择知识库 —</option>
              {datasets.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="检索 query(支持变量)">
            <textarea
              value={(d.query as string) ?? ''}
              onChange={(e) => onChange({ query: e.target.value })}
              rows={2}
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
            />
          </Field>
          <Field label="top_k">
            <input
              type="number"
              value={(d.top_k as number) ?? 4}
              onChange={(e) => onChange({ top_k: Number(e.target.value) })}
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
            />
          </Field>
        </>
      )}

      {type === 'condition' && (
        <>
          <Field label="逻辑">
            <select
              value={(d.logic as string) ?? 'and'}
              onChange={(e) => onChange({ logic: e.target.value })}
              className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
            >
              <option value="and">全部满足(AND)</option>
              <option value="or">任一满足(OR)</option>
            </select>
          </Field>
          <ListEditor
            label="条件(命中走「真」边)"
            items={(d.conditions as { variable: string; operator: string; value: string }[]) ?? []}
            render={(item, set) => (
              <div className="space-y-1">
                <input
                  value={item.variable ?? ''}
                  onChange={(e) => set({ variable: e.target.value })}
                  placeholder="变量,如 {{ start.query }}"
                  className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
                />
                <div className="flex gap-1">
                  <select
                    value={item.operator ?? 'eq'}
                    onChange={(e) => set({ operator: e.target.value })}
                    className="rounded-md border border-gray-300 px-1 py-1 text-xs focus:border-gray-900 focus:outline-none"
                  >
                    {OPERATORS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  <input
                    value={item.value ?? ''}
                    onChange={(e) => set({ value: e.target.value })}
                    placeholder="比较值"
                    className="min-w-0 flex-1 rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
                  />
                </div>
              </div>
            )}
            empty={{ variable: '', operator: 'eq', value: '' }}
            onChange={(conditions) => onChange({ conditions })}
          />
        </>
      )}

      {type === 'code' && (
        <>
          <ListEditor
            label="输入(注入 inputs)"
            items={(d.inputs as { name: string; value: string }[]) ?? []}
            render={(item, set) => (
              <div className="flex gap-1">
                <input
                  value={item.name ?? ''}
                  onChange={(e) => set({ name: e.target.value })}
                  placeholder="名"
                  className="w-20 rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
                />
                <input
                  value={item.value ?? ''}
                  onChange={(e) => set({ value: e.target.value })}
                  placeholder="{{ start.query }}"
                  className="min-w-0 flex-1 rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
                />
              </div>
            )}
            empty={{ name: '', value: '' }}
            onChange={(inputs) => onChange({ inputs })}
          />
          <Field label="Python(读 inputs,写 outputs dict)">
            <textarea
              value={(d.code as string) ?? ''}
              onChange={(e) => onChange({ code: e.target.value })}
              rows={6}
              spellCheck={false}
              className="w-full rounded-md border border-gray-300 px-2 py-1 font-mono text-xs focus:border-gray-900 focus:outline-none"
            />
          </Field>
        </>
      )}

      {type === 'template' && (
        <Field label="模板(支持 {{ 节点.字段 }})">
          <textarea
            value={(d.template as string) ?? ''}
            onChange={(e) => onChange({ template: e.target.value })}
            rows={5}
            className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-gray-900 focus:outline-none"
          />
        </Field>
      )}

      {removable && (
        <button
          onClick={onDelete}
          className="mt-2 w-full rounded-md border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50"
        >
          删除节点
        </button>
      )}
    </div>
  )
}

// ---- 运行面板:输入表单 + 运行结果回放 ----
function RunPanel({
  variables,
  values,
  onValueChange,
  run,
}: {
  variables: { name: string }[]
  values: Record<string, string>
  onValueChange: (k: string, v: string) => void
  run: WorkflowRun | null
}) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-2 text-sm font-semibold">运行输入</h3>
        {variables.length === 0 ? (
          <p className="text-xs text-gray-400">开始节点未声明输入变量。</p>
        ) : (
          <div className="space-y-2">
            {variables.map((v) => (
              <Field key={v.name} label={v.name}>
                <input
                  value={values[v.name] ?? ''}
                  onChange={(e) => onValueChange(v.name, e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
                />
              </Field>
            ))}
          </div>
        )}
        <p className="mt-2 text-[11px] text-gray-400">点击右上角「▶ 运行」执行(会先保存)。</p>
      </div>

      {run && (
        <div className="space-y-2 border-t border-gray-100 pt-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">运行结果</h3>
            <span
              className="rounded-full px-2 py-0.5 text-[10px] text-white"
              style={{ background: STATUS_COLOR[run.status] ?? '#6b7280' }}
            >
              {run.status}
            </span>
            {run.elapsed_ms != null && (
              <span className="text-[10px] text-gray-400">{run.elapsed_ms}ms</span>
            )}
          </div>
          {run.error && <p className="text-xs text-red-600">{run.error}</p>}
          {run.outputs && (
            <pre className="overflow-x-auto rounded-md bg-gray-900 p-2 text-[11px] text-gray-100">
              {JSON.stringify(run.outputs, null, 2)}
            </pre>
          )}
          <div className="space-y-1.5">
            {run.node_runs.map((nr) => (
              <NodeRunRow key={nr.id} nr={nr} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function NodeRunRow({ nr }: { nr: NodeRun }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-md border border-gray-200">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs"
      >
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: STATUS_COLOR[nr.status] ?? '#9ca3af' }}
        />
        <span className="font-medium text-gray-700">{nr.node_id}</span>
        <span className="text-gray-400">{nr.node_type}</span>
        {nr.elapsed_ms != null && nr.status !== 'skipped' && (
          <span className="ml-auto text-[10px] text-gray-400">{nr.elapsed_ms}ms</span>
        )}
      </button>
      {open && (
        <div className="space-y-1 border-t border-gray-100 px-2 py-1.5 text-[11px]">
          {nr.error && <p className="text-red-600">{nr.error}</p>}
          {nr.inputs && Object.keys(nr.inputs).length > 0 && (
            <div>
              <span className="text-gray-400">输入</span>
              <pre className="overflow-x-auto rounded bg-gray-50 p-1">
                {JSON.stringify(nr.inputs, null, 2)}
              </pre>
            </div>
          )}
          {nr.outputs && (
            <div>
              <span className="text-gray-400">输出</span>
              <pre className="overflow-x-auto rounded bg-gray-50 p-1">
                {JSON.stringify(nr.outputs, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---- 小型可复用控件 ----
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-gray-500">{label}</span>
      {children}
    </label>
  )
}

function ListEditor<T extends Record<string, unknown>>({
  label,
  items,
  render,
  empty,
  onChange,
}: {
  label: string
  items: T[]
  render: (item: T, set: (patch: Partial<T>) => void) => React.ReactNode
  empty: T
  onChange: (items: T[]) => void
}) {
  // 每次渲染的 onChange 闭包都基于当前 items;改一项即触发重渲染拿到最新数组
  return (
    <div>
      <span className="mb-1 block text-xs text-gray-500">{label}</span>
      <div className="space-y-1.5">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-1">
            <div className="min-w-0 flex-1">
              {render(item, (patch) => {
                const next = items.map((it, j) => (j === i ? { ...it, ...patch } : it))
                onChange(next)
              })}
            </div>
            <button
              onClick={() => onChange(items.filter((_, j) => j !== i))}
              className="px-1 text-gray-400 hover:text-red-600"
              title="删除"
            >
              ×
            </button>
          </div>
        ))}
        <button
          onClick={() => onChange([...items, { ...empty }])}
          className="rounded-md border border-dashed border-gray-300 px-2 py-1 text-xs text-gray-500 hover:border-gray-400"
        >
          + 添加
        </button>
      </div>
    </div>
  )
}
