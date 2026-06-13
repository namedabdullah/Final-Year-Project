import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Eraser, Loader2, Send } from 'lucide-react'
import { toast } from 'sonner'
import { apiErrorDetail, chatApi, streamChat } from '@/api/sampai'

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export default function ChatPanel({ fileId, summary }: { fileId: number; summary?: string | null }) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatApi
      .history(fileId)
      .then((r) => setMessages(r.messages.map((m) => ({ id: String(m.id), role: m.role as 'user' | 'assistant', content: m.content }))))
      .catch(() => {})
  }, [fileId])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  async function send() {
    const q = input.trim()
    if (!q || sending) return
    setInput('')
    setSending(true)
    const userMsg: Msg = { id: `u-${Date.now()}`, role: 'user', content: q }
    const aId = `a-${Date.now()}`
    setMessages((m) => [...m, userMsg, { id: aId, role: 'assistant', content: '', streaming: true }])
    try {
      await streamChat(fileId, q, (tok) => {
        setMessages((m) => m.map((x) => (x.id === aId ? { ...x, content: x.content + tok } : x)))
      })
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Chat failed'))
      setMessages((m) => m.map((x) => (x.id === aId ? { ...x, content: x.content || '*Failed to get a response.*' } : x)))
    } finally {
      setMessages((m) => m.map((x) => (x.id === aId ? { ...x, streaming: false } : x)))
      setSending(false)
    }
  }

  async function clear() {
    try {
      await chatApi.clear(fileId)
      setMessages([])
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not clear chat'))
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <div className="flex h-[60vh] flex-col rounded-xl border border-neutral-800 bg-neutral-900/40">
      <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-2">
        <span className="text-sm font-medium text-neutral-300">Chat with this document</span>
        <button onClick={clear} className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300">
          <Eraser className="h-3.5 w-3.5" /> Clear
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {summary && (
          <Bubble role="assistant">
            <Markdown>{summary}</Markdown>
          </Bubble>
        )}
        {messages.length === 0 && !summary && (
          <p className="mt-8 text-center text-sm text-neutral-500">Ask anything about this document.</p>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} role={m.role}>
            {m.role === 'assistant' ? (
              m.content ? <Markdown>{m.content}</Markdown> : <span className="text-neutral-500">…</span>
            ) : (
              <span className="whitespace-pre-wrap">{m.content}</span>
            )}
          </Bubble>
        ))}
        <div ref={endRef} />
      </div>

      <div className="flex items-end gap-2 border-t border-neutral-800 p-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={1}
          placeholder="Ask a question… (Enter to send)"
          className="max-h-32 flex-1 resize-none rounded-lg border border-neutral-700 bg-neutral-950/60 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-violet-500"
        />
        <button
          onClick={send}
          disabled={!input.trim() || sending}
          className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-40"
        >
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

function Bubble({ role, children }: { role: 'user' | 'assistant'; children: ReactNode }) {
  const mine = role === 'user'
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
          mine ? 'bg-violet-600/25 text-neutral-100' : 'border border-neutral-800 bg-neutral-900/70 text-neutral-200'
        }`}
      >
        {children}
      </div>
    </div>
  )
}

function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-pre:my-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}
