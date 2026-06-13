import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Handle,
  Panel,
  Position,
  useReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ChevronRight,
  ListTree,
  Loader2,
  RefreshCw,
  Send,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { toast } from 'sonner'
import { apiErrorDetail, mindmapApi, type MindChatMsg, type MindNode, type Mindmap } from '@/api/sampai'

const NODE_W = 300
const NODE_H = 92
const exploredNodeKeys = new Set<string>()
const exploreInFlight = new Map<string, Promise<void>>()

type MindNodeData = {
  label: string
  description?: string
  hasChildren: boolean
  expanded: boolean
  isRoot: boolean
  onToggle: (id: string) => void
}

const nodeTypes = { mindNode: MindNodeCard }

function collectExpandableIds(root: MindNode): string[] {
  const ids: string[] = []
  function walk(node: MindNode) {
    if (node.children?.length) ids.push(node.id)
    node.children?.forEach(walk)
  }
  walk(root)
  return ids
}

function messageNodeId(message: MindChatMsg): string | null {
  const metaNodeId =
    typeof message.message_metadata?.node_id === 'string'
      ? message.message_metadata.node_id
      : typeof message.message_metadata?.active_node_id === 'string'
        ? message.message_metadata.active_node_id
        : null
  return message.node_id ?? metaNodeId
}

function messagesForNode(messages: MindChatMsg[], nodeId: string): MindChatMsg[] {
  return messages.filter((message) => message.role !== 'marker' && messageNodeId(message) === nodeId)
}

function layout(root: MindNode, expanded: Set<string>, onToggle: (id: string) => void): { nodes: Node<MindNodeData>[]; edges: Edge[] } {
  const graph = new dagre.graphlib.Graph()
  graph.setGraph({ rankdir: 'LR', nodesep: 48, ranksep: 150, marginx: 72, marginy: 56 })
  graph.setDefaultEdgeLabel(() => ({}))

  const nodes: Node<MindNodeData>[] = []
  const edges: Edge[] = []

  function walk(node: MindNode, parent: string | null, depth: number) {
    const hasChildren = (node.children?.length ?? 0) > 0
    graph.setNode(node.id, { width: NODE_W, height: NODE_H })
    nodes.push({
      id: node.id,
      type: 'mindNode',
      data: {
        label: node.topic,
        description: node.description,
        hasChildren,
        expanded: expanded.has(node.id),
        isRoot: depth === 0,
        onToggle,
      },
      targetPosition: Position.Left,
      sourcePosition: Position.Right,
      position: { x: 0, y: 0 },
    })

    if (parent) {
      graph.setEdge(parent, node.id)
      edges.push({
        id: `${parent}-${node.id}`,
        source: parent,
        target: node.id,
        type: 'smoothstep',
        style: { stroke: 'color-mix(in oklab, var(--chart-1), transparent 38%)', strokeWidth: 1.7 },
      })
    }

    if (hasChildren && expanded.has(node.id)) {
      node.children.forEach((child) => walk(child, node.id, depth + 1))
    }
  }

  walk(root, null, 0)
  dagre.layout(graph)
  for (const node of nodes) {
    const point = graph.node(node.id)
    node.position = { x: point.x - NODE_W / 2, y: point.y - NODE_H / 2 }
  }
  return { nodes, edges }
}

function MindNodeCard({ id, data, selected }: NodeProps<Node<MindNodeData>>) {
  return (
    <div
      className={`relative min-h-[92px] w-[300px] rounded-xl border px-5 py-4 shadow-sm backdrop-blur-md transition ${
        selected
          ? 'border-chart-1 bg-chart-1/18 shadow-[0_0_28px_rgba(99,102,241,0.22)]'
          : data.isRoot
            ? 'border-chart-1/45 bg-chart-1/20'
            : 'border-border/65 bg-card/85'
      }`}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-chart-1 !bg-background" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-chart-1 !bg-background" />

      {data.hasChildren && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            data.onToggle(id)
          }}
          className="absolute -right-6 top-1/2 z-20 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-chart-1/45 bg-background/95 text-chart-1 shadow-lg shadow-background/35 transition hover:scale-105 hover:border-chart-1 hover:bg-card"
          aria-label={data.expanded ? 'Collapse node' : 'Expand node'}
        >
          <ChevronRight className={`h-6 w-6 transition-transform ${data.expanded ? 'rotate-90' : ''}`} />
        </button>
      )}

      <div className="flex items-start gap-2 pr-6">
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-[17px] font-semibold leading-snug text-foreground">{data.label}</p>
          {data.description && (
            <p className="mt-1.5 line-clamp-2 text-sm leading-snug text-muted-foreground">{data.description}</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default function MindmapPanel({ fileId }: { fileId: number }) {
  const [mm, setMm] = useState<Mindmap | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeNode, setActiveNode] = useState<{ id: string; topic: string } | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const initializedMindmapRef = useRef<number | null>(null)

  const startPoll = useCallback(() => {
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      const data = await mindmapApi.get(fileId)
      setMm(data)
      if (data.status === 'ready' || data.status === 'failed') {
        clearInterval(pollRef.current!)
        pollRef.current = null
      }
    }, 2500)
  }, [fileId])

  const load = useCallback(async () => {
    try {
      const data = await mindmapApi.get(fileId)
      setMm(data)
      if (data.status === 'pending' || data.status === 'generating') startPoll()
    } catch (error) {
      const code = (error as { response?: { status?: number } })?.response?.status
      if (code === 404) setMm(null)
    } finally {
      setLoading(false)
    }
  }, [fileId, startPoll])

  useEffect(() => {
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [load])

  useEffect(() => {
    const root = mm?.tree_data?.root
    if (!root || mm.status !== 'ready') return
    if (initializedMindmapRef.current === mm.id) return
    initializedMindmapRef.current = mm.id
    setExpanded(new Set(collectExpandableIds(root)))
    setActiveNode(null)
  }, [mm])

  async function generate(force = false) {
    try {
      setLoading(true)
      const response = await mindmapApi.generate(fileId, force)
      setMm(response.mindmap)
      setLoading(false)
      if (response.mindmap.status !== 'ready') startPoll()
    } catch (error) {
      setLoading(false)
      toast.error(apiErrorDetail(error, 'Could not generate mindmap'))
    }
  }

  const toggleNode = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const root = mm?.tree_data?.root ?? null
  const expandableIds = useMemo(() => (root ? collectExpandableIds(root) : []), [root])
  const effectiveExpanded = useMemo(() => {
    if (root && mm?.status === 'ready' && initializedMindmapRef.current !== mm.id && expanded.size === 0) {
      return new Set(expandableIds)
    }
    return expanded
  }, [root, mm?.id, mm?.status, expanded, expandableIds])
  const allExpanded = expandableIds.length > 0 && expandableIds.every((id) => effectiveExpanded.has(id))
  const flow = useMemo(() => (root ? layout(root, effectiveExpanded, toggleNode) : null), [root, effectiveExpanded, toggleNode])

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    setActiveNode({ id: node.id, topic: String(node.data.label) })
  }

  if (loading && !mm) return <Centered><Loader2 className="h-7 w-7 animate-spin text-chart-1" /></Centered>

  if (!mm || mm.status === 'pending' || mm.status === 'generating') {
    if (!mm) {
      return (
        <Centered>
          <p className="mb-4 text-sm text-muted-foreground">Build an interactive mind map of this document.</p>
          <button
            type="button"
            onClick={() => generate(false)}
            className="rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
          >
            Generate mind map
          </button>
        </Centered>
      )
    }
    return <Centered><Loader2 className="h-7 w-7 animate-spin text-chart-1" /><p className="mt-3 text-sm text-muted-foreground">Building mind map...</p></Centered>
  }

  if (mm.status === 'failed') {
    return (
      <Centered>
        <p className="text-sm text-red-500">{mm.error_message ?? 'Generation failed.'}</p>
        <button
          type="button"
          onClick={() => generate(true)}
          className="mt-4 inline-flex items-center gap-2 rounded-xl border border-border/60 bg-card/60 px-4 py-2 text-sm text-foreground transition hover:bg-card/80"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </Centered>
    )
  }

  return (
    <div
      className={`grid h-full min-h-[calc(100vh-9rem)] grid-cols-1 overflow-hidden bg-background/35 ${
        activeNode ? 'lg:grid-cols-[minmax(0,1fr)_minmax(360px,42vw)]' : 'lg:grid-cols-1'
      }`}
    >
      <div className="min-h-[520px] min-w-0">
        {flow && root && (
          <ReactFlowProvider>
            <MindmapFlow
              nodes={flow.nodes}
              edges={flow.edges}
              onNodeClick={onNodeClick}
              allExpanded={allExpanded}
              fitSignal={activeNode?.id ?? 'no-chat'}
              onToggleAll={() => setExpanded(allExpanded ? new Set() : new Set(expandableIds))}
            />
          </ReactFlowProvider>
        )}
      </div>
      {activeNode && (
        <NodeChat mindmapId={mm.id} node={activeNode} onClose={() => setActiveNode(null)} />
      )}
    </div>
  )
}

function MindmapFlow({
  nodes,
  edges,
  onNodeClick,
  allExpanded,
  fitSignal,
  onToggleAll,
}: {
  nodes: Node<MindNodeData>[]
  edges: Edge[]
  onNodeClick: NodeMouseHandler
  allExpanded: boolean
  fitSignal: string
  onToggleAll: () => void
}) {
  const { setViewport, zoomIn, zoomOut } = useReactFlow()
  const containerRef = useRef<HTMLDivElement>(null)

  const centerGraph = useCallback((duration = 420) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect || rect.width < 120 || rect.height < 120 || nodes.length === 0) return

    const margin = 130
    const minX = Math.min(...nodes.map((node) => node.position.x)) - 72
    const minY = Math.min(...nodes.map((node) => node.position.y)) - 72
    const maxX = Math.max(...nodes.map((node) => node.position.x + NODE_W)) + 72
    const maxY = Math.max(...nodes.map((node) => node.position.y + NODE_H)) + 72
    const graphWidth = Math.max(1, maxX - minX)
    const graphHeight = Math.max(1, maxY - minY)
    const availableWidth = Math.max(160, rect.width - margin)
    const availableHeight = Math.max(160, rect.height - margin)
    const fitZoom = Math.min(availableWidth / graphWidth, availableHeight / graphHeight)
    const zoom = Math.max(0.16, Math.min(0.76, fitZoom * 1.08))
    const centerX = minX + graphWidth / 2
    const centerY = minY + graphHeight / 2

    setViewport(
      {
        x: rect.width / 2 - centerX * zoom,
        y: rect.height / 2 - centerY * zoom,
        zoom,
      },
      { duration },
    )
  }, [nodes, setViewport])

  useEffect(() => {
    const id = window.requestAnimationFrame(() => centerGraph(450))
    return () => window.cancelAnimationFrame(id)
  }, [nodes, edges, fitSignal, centerGraph])

  useEffect(() => {
    const first = window.setTimeout(() => centerGraph(320), 80)
    const second = window.setTimeout(() => centerGraph(320), 260)
    const third = window.setTimeout(() => centerGraph(320), 680)
    const fourth = window.setTimeout(() => centerGraph(320), 1100)
    return () => {
      window.clearTimeout(first)
      window.clearTimeout(second)
      window.clearTimeout(third)
      window.clearTimeout(fourth)
    }
  }, [fitSignal, centerGraph])

  return (
    <div ref={containerRef} className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onInit={() => {
          window.setTimeout(() => centerGraph(350), 80)
          window.setTimeout(() => centerGraph(350), 300)
          window.setTimeout(() => centerGraph(350), 760)
        }}
        minZoom={0.08}
        maxZoom={1.6}
        nodesDraggable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="color-mix(in oklab, var(--muted-foreground), transparent 70%)" gap={22} />
        <Panel position="top-left" className="!m-3 flex overflow-hidden rounded-xl border border-border/60 bg-background/85 shadow-lg backdrop-blur-xl">
          <button
            type="button"
            onClick={() => zoomIn({ duration: 180 })}
            className="flex h-10 w-10 items-center justify-center border-r border-border/50 text-foreground transition hover:bg-muted"
            aria-label="Zoom in"
            title="Zoom in"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => zoomOut({ duration: 180 })}
            className="flex h-10 w-10 items-center justify-center border-r border-border/50 text-foreground transition hover:bg-muted"
            aria-label="Zoom out"
            title="Zoom out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onToggleAll}
            className="flex h-10 items-center justify-center gap-2 px-3 text-xs font-medium text-foreground transition hover:bg-muted"
            aria-label={allExpanded ? 'Collapse all nodes' : 'Expand all nodes'}
            title={allExpanded ? 'Collapse all nodes' : 'Expand all nodes'}
          >
            <ListTree className="h-4 w-4" />
            {allExpanded ? 'Collapse' : 'Expand'}
          </button>
        </Panel>
      </ReactFlow>
    </div>
  )
}

function NodeChat({ mindmapId, node, onClose }: { mindmapId: number; node: { id: string; topic: string }; onClose: () => void }) {
  const [messages, setMessages] = useState<MindChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [bootstrapping, setBootstrapping] = useState(true)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async (): Promise<MindChatMsg[]> => {
    const response = await mindmapApi.chatHistory(mindmapId)
    setMessages(response.messages)
    const pending = response.messages.some((message) => message.role === 'assistant' && message.message_metadata?.pending === true)
    if (pending && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        const next = await mindmapApi.chatHistory(mindmapId)
        setMessages(next.messages)
        if (!next.messages.some((message) => message.role === 'assistant' && message.message_metadata?.pending === true)) {
          clearInterval(pollRef.current!)
          pollRef.current = null
        }
      }, 1500)
    }
    return response.messages
  }, [mindmapId])

  useEffect(() => {
    let cancelled = false
    const key = `${mindmapId}:${node.id}`
    setBootstrapping(true)

    async function ensureExplored() {
      try {
        const existing = await refresh()
        if (cancelled) return
        const existingNodeMessages = messagesForNode(existing, node.id)
        const hasReusableThread = existingNodeMessages.some((message) => message.content.trim().length > 0)

        if (hasReusableThread) {
          exploredNodeKeys.add(key)
          setBootstrapping(false)
          return
        }

        if (!exploredNodeKeys.has(key)) {
          let promise = exploreInFlight.get(key)
          if (!promise) {
            promise = mindmapApi
              .explore(mindmapId, node.id)
              .then(() => { exploredNodeKeys.add(key) })
              .finally(() => { exploreInFlight.delete(key) })
            exploreInFlight.set(key, promise)
          }
          await promise
        }
      } catch {
        /* non-fatal; chat history still refreshes */
      }
      if (!cancelled) {
        await refresh()
        setBootstrapping(false)
      }
    }

    void ensureExplored()
    return () => {
      cancelled = true
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [mindmapId, node.id, refresh])

  async function ask() {
    const question = input.trim()
    if (!question || sending) return
    setInput('')
    setSending(true)
    const optimisticId = -Date.now()
    const optimistic: MindChatMsg = {
      id: optimisticId,
      node_id: node.id,
      role: 'user',
      content: question,
      message_metadata: { active_node_id: node.id, optimistic: true },
    } as MindChatMsg
    setMessages((prev) => [...prev, optimistic])
    try {
      await mindmapApi.ask(mindmapId, question, node.id)
      await refresh()
    } catch (error) {
      setMessages((prev) => prev.filter((message) => message.id !== optimisticId))
      toast.error(apiErrorDetail(error, 'Ask failed'))
    } finally {
      setSending(false)
    }
  }

  const visible = messagesForNode(messages, node.id)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [visible.length, sending, bootstrapping])

  return (
    <div className="flex min-h-[420px] flex-col border-l border-border/60 bg-card/80 backdrop-blur-xl">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{node.topic}</p>
          <p className="text-xs text-muted-foreground">Node chat</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
          aria-label="Close node chat"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {visible.length === 0 && bootstrapping && (
          <p className="mt-6 text-center text-xs text-muted-foreground">
            <Loader2 className="mx-auto mb-2 h-4 w-4 animate-spin" />
            Generating summary...
          </p>
        )}
        {visible.length === 0 && !bootstrapping && (
          <p className="mt-6 text-center text-xs text-muted-foreground">No messages for this node yet.</p>
        )}
        {visible.map((message) => (
          <motion.div
            key={message.id}
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.18 }}
            className={`rounded-xl px-3 py-2 text-sm ${
              message.role === 'user'
                ? 'ml-8 bg-chart-1/20 text-foreground'
                : 'border border-border/50 bg-background/65 text-foreground'
            }`}
          >
            {message.content ? (
              <div className="prose prose-sm max-w-none prose-p:my-1 dark:prose-invert">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              </div>
            ) : (
              <span className="text-muted-foreground"><Loader2 className="inline h-3 w-3 animate-spin" /> ...</span>
            )}
          </motion.div>
        ))}
        {sending && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mr-8 rounded-xl border border-border/50 bg-background/65 px-3 py-2 text-sm text-muted-foreground shadow-sm"
          >
            <Loader2 className="mr-2 inline h-3.5 w-3.5 animate-spin" />
            SAMpai is thinking...
          </motion.div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="flex items-end gap-2 border-t border-border/60 p-3">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void ask()
            }
          }}
          rows={1}
          placeholder="Ask about this topic..."
          className="max-h-28 flex-1 resize-none rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-chart-1"
        />
        <button
          type="button"
          onClick={() => void ask()}
          disabled={!input.trim() || sending}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-chart-1 text-white transition hover:opacity-90 disabled:opacity-40"
          aria-label="Send"
        >
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex min-h-[calc(100vh-12rem)] flex-col items-center justify-center p-8 text-center">{children}</div>
}
