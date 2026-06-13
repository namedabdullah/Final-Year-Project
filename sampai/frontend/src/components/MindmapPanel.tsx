import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, RefreshCw, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { apiErrorDetail, mindmapApi, type MindChatMsg, type MindNode, type Mindmap } from '@/api/sampai'

const NODE_W = 200
const NODE_H = 56

function layout(root: MindNode): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 24, ranksep: 70 })
  g.setDefaultEdgeLabel(() => ({}))
  const nodes: Node[] = []
  const edges: Edge[] = []

  function walk(n: MindNode, parent: string | null) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H })
    nodes.push({
      id: n.id,
      data: { label: n.topic },
      position: { x: 0, y: 0 },
      style: {
        width: NODE_W,
        background: n.id === 'n_root' ? '#7c3aed' : '#1f1f23',
        color: '#fff',
        border: '1px solid #3f3f46',
        borderRadius: 10,
        fontSize: 12,
        padding: 8,
      },
    })
    if (parent) {
      g.setEdge(parent, n.id)
      edges.push({ id: `${parent}-${n.id}`, source: parent, target: n.id, style: { stroke: '#52525b' } })
    }
    n.children?.forEach((c) => walk(c, n.id))
  }
  walk(root, null)
  dagre.layout(g)
  for (const node of nodes) {
    const p = g.node(node.id)
    node.position = { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 }
  }
  return { nodes, edges }
}

export default function MindmapPanel({ fileId }: { fileId: number }) {
  const [mm, setMm] = useState<Mindmap | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeNode, setActiveNode] = useState<{ id: string; topic: string } | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await mindmapApi.get(fileId)
      setMm(data)
      if (data.status === 'pending' || data.status === 'generating') startPoll()
    } catch (e) {
      const code = (e as { response?: { status?: number } })?.response?.status
      if (code === 404) setMm(null)
    } finally {
      setLoading(false)
    }
  }, [fileId]) // eslint-disable-line react-hooks/exhaustive-deps

  function startPoll() {
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      const data = await mindmapApi.get(fileId)
      setMm(data)
      if (data.status === 'ready' || data.status === 'failed') { clearInterval(pollRef.current!); pollRef.current = null }
    }, 2500)
  }

  useEffect(() => {
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [load])

  async function generate(force = false) {
    try {
      setLoading(true)
      const r = await mindmapApi.generate(fileId, force)
      setMm(r.mindmap)
      setLoading(false)
      if (r.mindmap.status !== 'ready') startPoll()
    } catch (e) {
      setLoading(false)
      toast.error(apiErrorDetail(e, 'Could not generate mindmap'))
    }
  }

  const flow = useMemo(() => (mm?.tree_data?.root ? layout(mm.tree_data.root) : null), [mm])

  const onNodeClick: NodeMouseHandler = (_e, node) => {
    setActiveNode({ id: node.id, topic: String(node.data.label) })
  }

  if (loading && !mm) return <Centered><Loader2 className="h-7 w-7 animate-spin text-violet-400" /></Centered>

  if (!mm || mm.status === 'pending' || mm.status === 'generating') {
    if (!mm) {
      return (
        <Centered>
          <p className="mb-4 text-sm text-neutral-400">Build an interactive mind map of this document.</p>
          <button onClick={() => generate(false)} className="btn-primary">Generate mind map</button>
        </Centered>
      )
    }
    return <Centered><Loader2 className="h-7 w-7 animate-spin text-violet-400" /><p className="mt-3 text-sm text-neutral-400">Building mind map…</p></Centered>
  }

  if (mm.status === 'failed') {
    return (
      <Centered>
        <p className="text-sm text-red-300">{mm.error_message ?? 'Generation failed.'}</p>
        <button onClick={() => generate(true)} className="btn-ghost mt-4"><RefreshCw className="h-4 w-4" /> Retry</button>
      </Centered>
    )
  }

  return (
    <div className="flex h-[65vh]">
      <div className="min-w-0 flex-1" style={{ width: activeNode ? '60%' : '100%' }}>
        {flow && (
          <ReactFlow nodes={flow.nodes} edges={flow.edges} onNodeClick={onNodeClick} fitView proOptions={{ hideAttribution: true }}>
            <Background color="#27272a" gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
      {activeNode && mm && (
        <NodeChat mindmapId={mm.id} node={activeNode} onClose={() => setActiveNode(null)} />
      )}
    </div>
  )
}

function NodeChat({ mindmapId, node, onClose }: { mindmapId: number; node: { id: string; topic: string }; onClose: () => void }) {
  const [messages, setMessages] = useState<MindChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = useCallback(async () => {
    const r = await mindmapApi.chatHistory(mindmapId)
    setMessages(r.messages)
    const pending = r.messages.some((m) => m.role === 'assistant' && m.message_metadata?.pending === true)
    if (pending && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        const rr = await mindmapApi.chatHistory(mindmapId)
        setMessages(rr.messages)
        if (!rr.messages.some((m) => m.role === 'assistant' && m.message_metadata?.pending === true)) {
          clearInterval(pollRef.current!); pollRef.current = null
        }
      }, 1500)
    }
  }, [mindmapId])

  useEffect(() => {
    mindmapApi.explore(mindmapId, node.id).then(refresh).catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [mindmapId, node.id, refresh])

  async function ask() {
    const q = input.trim()
    if (!q || sending) return
    setInput(''); setSending(true)
    try {
      await mindmapApi.ask(mindmapId, q, node.id)
      await refresh()
    } catch (e) { toast.error(apiErrorDetail(e, 'Ask failed')) }
    finally { setSending(false) }
  }

  // show this node's summary + any subsequent Q&A (skip markers)
  const visible = messages.filter((m) => m.role !== 'marker')

  return (
    <div className="flex w-2/5 flex-col border-l border-neutral-800 bg-neutral-900/40">
      <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
        <span className="truncate text-sm font-medium text-violet-200">{node.topic}</span>
        <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300"><X className="h-4 w-4" /></button>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {visible.length === 0 && <p className="mt-6 text-center text-xs text-neutral-500"><Loader2 className="mx-auto h-4 w-4 animate-spin" /> Generating summary…</p>}
        {visible.map((m) => (
          <div key={m.id} className={`rounded-xl px-3 py-2 text-sm ${m.role === 'user' ? 'ml-6 bg-violet-600/25' : 'border border-neutral-800 bg-neutral-900/70'}`}>
            {m.content ? (
              <div className="prose prose-invert prose-sm max-w-none prose-p:my-1"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
            ) : (
              <span className="text-neutral-500"><Loader2 className="inline h-3 w-3 animate-spin" /> …</span>
            )}
          </div>
        ))}
      </div>
      <div className="flex items-end gap-2 border-t border-neutral-800 p-2">
        <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }} rows={1} placeholder="Ask about this topic…" className="max-h-24 flex-1 resize-none rounded-lg border border-neutral-700 bg-neutral-950/60 px-3 py-2 text-sm outline-none focus:border-violet-500" />
        <button onClick={ask} disabled={!input.trim() || sending} className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-600 text-white disabled:opacity-40">
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">{children}</div>
}
