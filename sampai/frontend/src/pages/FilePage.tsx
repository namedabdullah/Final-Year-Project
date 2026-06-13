import { useState, useEffect, useRef, useCallback } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { motion } from "framer-motion"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Download, Send, Loader2, AlertCircle, RefreshCw, BookOpen, BrainCircuit, Map, MessageSquare } from "lucide-react"
import { classroomApi, folderApi, fileApi, chatApi, streamChat, normalizeErrorDetail, type ChatMessageDTO } from "@/api/sampai"
import type { FileItem } from "@/lib/types"
import { useAuth } from "@/stores/auth"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
import { InviteButton } from "@/components/group-chat/invite-button"
import QuizPanel from "@/components/QuizPanel"
import FlashcardsPanel from "@/components/FlashcardsPanel"
import MindmapPanel from "@/components/MindmapPanel"
import type { Classroom, Folder } from "@/lib/types"
import Plasma from "@/components/backgrounds/plasma"

type TabId = "chat" | "quiz" | "flashcards" | "mindmap"

// ── Markdown renderer ─────────────────────────────────────────────────────────

const mdComponents = {
  p: ({ children }: { children: React.ReactNode }) => (
    <p className="mb-1 last:mb-0 leading-relaxed">{children}</p>
  ),
  strong: ({ children }: { children: React.ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }: { children: React.ReactNode }) => <em className="italic">{children}</em>,
  ul: ({ children }: { children: React.ReactNode }) => (
    <ul className="list-disc pl-4 mb-1 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }: { children: React.ReactNode }) => (
    <ol className="list-decimal pl-4 mb-1 space-y-0.5">{children}</ol>
  ),
  li: ({ children }: { children: React.ReactNode }) => <li>{children}</li>,
  code: ({ children }: { children: React.ReactNode }) => (
    <code className="bg-black/20 dark:bg-white/10 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
  ),
  blockquote: ({ children }: { children: React.ReactNode }) => (
    <blockquote className="border-l-2 border-border/60 pl-3 italic text-foreground/70">{children}</blockquote>
  ),
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="text-sm text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents as never}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

function ThinkingDots() {
  return (
    <div className="flex justify-start px-1">
      <div className="rounded-2xl rounded-bl-sm bg-card/40 backdrop-blur-md border border-white/10 dark:border-white/10 px-4 py-3.5">
        <div className="flex gap-1.5 items-center h-4">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="block w-1.5 h-1.5 rounded-full bg-foreground/50"
              animate={{ y: [0, -5, 0] }}
              transition={{ duration: 0.9, delay: i * 0.18, repeat: Infinity, ease: "easeInOut" }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FilePage() {
  const { id, folderId, fileId } = useParams<{ id: string; folderId: string; fileId: string }>()
  const navigate = useNavigate()
  const classroomId = parseInt(id ?? "0", 10)
  const folderIdNum = parseInt(folderId ?? "0", 10)
  const fileIdNum = parseInt(fileId ?? "0", 10)
  const { user, logout } = useAuth()
  const { theme } = useTheme()
  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [folder, setFolder] = useState<Folder | null>(null)
  const [file, setFile] = useState<FileItem | null>(null)
  const [files, setFiles] = useState<FileItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>("chat")

  // Chat state
  const [messages, setMessages] = useState<ChatMessageDTO[]>([])
  const [question, setQuestion] = useState("")
  const [isAsking, setIsAsking] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamBuffer, setStreamBuffer] = useState("")
  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => () => { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current) }, [])

  const fetchFile = useCallback(async () => {
    try {
      const f = await fileApi.get(fileIdNum)
      setFile(f)
      return f
    } catch {
      return null
    }
  }, [fileIdNum])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await chatApi.history(fileIdNum)
      setMessages(res.messages)
    } catch {
      // non-fatal
    }
  }, [fileIdNum])

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return
    pollIntervalRef.current = setInterval(async () => {
      const updated = await fetchFile()
      if (updated && (updated.processing_status === "completed" || updated.processing_status === "failed")) {
        clearInterval(pollIntervalRef.current!)
        pollIntervalRef.current = null
        if (updated.processing_status === "completed") await fetchHistory()
      }
    }, 3000)
  }, [fetchFile, fetchHistory])

  useEffect(() => {
    if (!user) { navigate("/login"); return }
    if (!classroomId || !folderIdNum || !fileIdNum) return

    const load = async () => {
      try {
        const [cls, folders, f, fls] = await Promise.all([
          classroomApi.get(classroomId),
          folderApi.list(classroomId),
          fileApi.get(fileIdNum),
          fileApi.list(folderIdNum),
        ])
        setClassroom(cls)
        setFolder(folders.find((fo) => fo.id === folderIdNum) ?? null)
        setFile(f)
        setFiles(fls)
        if (f.processing_status === "completed" || f.processing_status === "naive_ready") {
          await fetchHistory()
        }
        if (f.processing_status === "pending" || f.processing_status === "processing" || f.processing_status === "naive_ready") {
          startPolling()
        }
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 401) { logout(); navigate("/login") }
        else if (status === 403) setError("You are not a member of this classroom")
        else setError("Failed to load. Please try again.")
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [user, classroomId, folderIdNum, fileIdNum]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isAsking, streamBuffer])

  // ── Actions ──────────────────────────────────────────────────────────────────

  const handleAsk = async () => {
    if (!question.trim() || isAsking || isStreaming || !canChat) return
    const q = question.trim()
    setQuestion("")
    setChatError(null)
    setIsAsking(true)

    const tempId = Date.now()
    setMessages((prev) => [...prev, { id: tempId, role: "user", content: q, timestamp: new Date().toISOString() }])

    try {
      abortRef.current = new AbortController()
      setIsStreaming(true)
      setStreamBuffer("")
      let accumulated = ""

      await streamChat(
        fileIdNum,
        q,
        (token) => {
          accumulated += token
          setStreamBuffer(accumulated)
        },
        abortRef.current.signal,
      )

      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "assistant", content: accumulated, timestamp: new Date().toISOString() },
      ])
      setStreamBuffer("")
    } catch (err: unknown) {
      if ((err as { name?: string })?.name === "AbortError") {
        // user cancelled
      } else {
        const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
        setChatError(normalizeErrorDetail(detail, "Failed to get an answer. Please try again."))
        setMessages((prev) => prev.filter((m) => m.id !== tempId))
      }
    } finally {
      setIsAsking(false)
      setIsStreaming(false)
      abortRef.current = null
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void handleAsk() }
  }

  const handleDownload = async () => {
    if (!fileIdNum || isDownloading) return
    setActionError(null)
    setIsDownloading(true)
    try {
      const res = await fileApi.download(fileIdNum)
      if (res?.download_url) window.open(res.download_url, "_blank")
      else setActionError("Failed to get download link.")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setActionError(normalizeErrorDetail(detail, "Failed to download."))
    } finally {
      setIsDownloading(false)
    }
  }

  const handleReprocess = async () => {
    try {
      await fileApi.reprocess(fileIdNum)
      setFile((prev) => prev ? { ...prev, processing_status: "pending" as const } : prev)
      setMessages([])
      startPolling()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setActionError(normalizeErrorDetail(detail, "Failed to start reprocessing."))
    }
  }

  const handleLogout = () => { logout(); navigate("/login") }

  // ── Derived ──────────────────────────────────────────────────────────────────

  const isOwner = !!(user && classroom && user.id === classroom.owner_id)
  const status = file?.processing_status ?? "pending"
  const isCompleted = status === "completed"
  const isNaiveReady = status === "naive_ready"
  const isFailed = status === "failed"
  const isInProgress = status === "pending" || status === "processing"
  const naiveReady = isNaiveReady || isCompleted
  const fullReady = isCompleted
  const canChat = naiveReady

  // Summary as first AI message
  const summaryMessage = file?.description
    ? { id: -1, role: "assistant" as const, content: file.description, timestamp: file.uploaded_at ?? "" }
    : null

  // Tab config
  const tabs: { id: TabId; label: string; icon: React.ReactNode; disabled?: boolean; loading?: boolean }[] = [
    { id: "chat", label: "Chat", icon: <MessageSquare className="h-3.5 w-3.5" /> },
    { id: "quiz", label: "Quiz", icon: <BookOpen className="h-3.5 w-3.5" />, disabled: !fullReady, loading: isNaiveReady },
    { id: "flashcards", label: "Flashcards", icon: <BrainCircuit className="h-3.5 w-3.5" /> },
    { id: "mindmap", label: "Mindmap", icon: <Map className="h-3.5 w-3.5" />, disabled: !fullReady, loading: isNaiveReady },
  ]

  // ── Loading / error ────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <LoadingOrb size={96} />
          <p className="text-sm text-muted-foreground">Loading file...</p>
        </div>
      </div>
    )
  }

  if (error || !classroom || !folder || !file) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "File not found"}</p>
          <button
            onClick={() => navigate(`/classroom/${classroomId}/folder/${folderIdNum}`)}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
          >
            Back to Folder
          </button>
        </div>
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <div className="fixed inset-0 z-0 pointer-events-none">
        <Plasma
          key={theme}
          color={plasmaColor}
          speed={0.35}
          direction="forward"
          scale={1.15}
          opacity={theme === "dark" ? 0.45 : 0.3}
          mouseInteractive={false}
        />
      </div>
      <ClassroomHeader
        classroomName={classroom.name}
        folderName={folder.name}
        fileName={file.filename}
        classroomId={classroomId}
        folderId={folderIdNum}
        username={user?.username ?? ""}
        onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        onLogout={handleLogout}
      />

      <div className="flex pt-16">
        <ClassroomSidebar
          collapsed={sidebarCollapsed}
          currentClassroomId={classroomId}
          mode="file"
          folderId={folderIdNum}
          files={files}
          currentFileId={fileIdNum}
          onFolderClick={() => navigate(`/classroom/${classroomId}/folder/${folderIdNum}`)}
          onFileSelect={(fid) => navigate(`/classroom/${classroomId}/folder/${folderIdNum}/file/${fid}`)}
          onHomeClick={() => navigate(isOwner ? "/created" : "/joined")}
        />

        <main
          className={`relative z-10 flex-1 flex flex-col h-[calc(100vh-4rem)] transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          {/* Top bar: tabs + action buttons */}
          <div className="shrink-0 flex items-center justify-between gap-3 px-4 pt-3 pb-2">
            {/* Tab pills */}
            <div className="flex items-center gap-1 bg-card/30 backdrop-blur-md border border-border/40 rounded-full p-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  disabled={tab.disabled}
                  onClick={() => {
                    if (tab.disabled) return
                    if (tab.id === "mindmap") setSidebarCollapsed(true)
                    setActiveTab(tab.id)
                  }}
                  title={tab.disabled ? "Available once full analysis finishes" : undefined}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer disabled:cursor-not-allowed ${
                    activeTab === tab.id
                      ? "bg-card/80 border border-border/60 text-foreground shadow-sm"
                      : tab.disabled
                      ? "text-muted-foreground/40"
                      : "text-muted-foreground hover:text-foreground hover:bg-card/40"
                  }`}
                >
                  {tab.loading ? <Loader2 className="h-3 w-3 animate-spin opacity-60" /> : tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2 shrink-0">
              {actionError && (
                <span className="text-xs text-destructive max-w-[160px] truncate">{actionError}</span>
              )}
              {isFailed && (
                <button
                  onClick={() => void handleReprocess()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-destructive/10 border border-destructive/30 text-destructive hover:bg-destructive/20 cursor-pointer transition-colors"
                >
                  <RefreshCw className="h-3 w-3" /> Retry
                </button>
              )}
              {isInProgress && (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs text-amber-500 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {status === "processing" ? "Processing…" : "Queued…"}
                </span>
              )}
              <InviteButton fileId={fileIdNum} classroomId={classroomId} />
              <button
                type="button"
                onClick={() => void handleDownload()}
                disabled={isDownloading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-card/50 backdrop-blur-sm border border-border/50 text-foreground hover:bg-card/70 disabled:opacity-50 cursor-pointer transition-colors"
              >
                {isDownloading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                {isDownloading ? "Preparing…" : "Download"}
              </button>
            </div>
          </div>

          {/* Tab content panels */}
          <div className={`flex-1 min-h-0 ${activeTab === "mindmap" ? "px-0 pb-0" : "px-4 pb-4"}`}>

            {/* CHAT */}
            <div className={`h-full flex flex-col gap-3 ${activeTab === "chat" ? "flex" : "hidden"}`}>
              <div className="flex-1 min-h-0 overflow-y-auto space-y-3 py-2 px-1">
                {summaryMessage && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35 }}
                    className="flex justify-start"
                  >
                    <div className="max-w-[82%] rounded-2xl rounded-bl-sm bg-card/40 backdrop-blur-md border border-white/10 dark:border-white/10 px-4 py-3">
                      <MarkdownContent content={summaryMessage.content} />
                    </div>
                  </motion.div>
                )}

                {!summaryMessage && messages.length === 0 && !isStreaming && (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
                    {isFailed ? (
                      <>
                        <AlertCircle className="h-6 w-6 text-destructive" />
                        <p className="text-sm text-destructive">Processing failed.</p>
                        <button
                          onClick={() => void handleReprocess()}
                          className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 border border-destructive/30 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/20 cursor-pointer"
                        >
                          <RefreshCw className="h-3.5 w-3.5" /> Retry
                        </button>
                      </>
                    ) : isInProgress ? (
                      <>
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        <p className="text-sm text-muted-foreground">Processing document…</p>
                        <p className="text-xs text-muted-foreground/60">Large files may take 2–5 minutes.</p>
                      </>
                    ) : (
                      <p className="text-sm text-muted-foreground">Ask anything about this document.</p>
                    )}
                  </div>
                )}

                {messages.map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25 }}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {msg.role === "user" ? (
                      <div className="max-w-[82%] rounded-2xl rounded-br-sm bg-chart-1/25 backdrop-blur-md border border-chart-1/20 px-4 py-3">
                        <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                      </div>
                    ) : (
                      <div className="max-w-[82%] rounded-2xl rounded-bl-sm bg-card/40 backdrop-blur-md border border-white/10 dark:border-white/10 px-4 py-3">
                        <MarkdownContent content={msg.content} />
                      </div>
                    )}
                  </motion.div>
                ))}

                {/* Streaming response */}
                {isStreaming && (
                  <div className="flex justify-start">
                    <div className="max-w-[82%] rounded-2xl rounded-bl-sm bg-card/40 backdrop-blur-md border border-white/10 dark:border-white/10 px-4 py-3">
                      {streamBuffer ? (
                        <MarkdownContent content={streamBuffer} />
                      ) : (
                        <ThinkingDots />
                      )}
                    </div>
                  </div>
                )}

                {isAsking && !isStreaming && <ThinkingDots />}

                {chatError && (
                  <p className="text-center text-xs text-destructive">{chatError}</p>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input bar */}
              <div className="shrink-0">
                <div className="flex items-end gap-2 bg-card/30 backdrop-blur-md border border-border/40 rounded-2xl p-2">
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isAsking || isStreaming || !canChat}
                    placeholder={
                      isFailed ? "Processing failed — click Retry"
                      : isInProgress ? "Processing document, check back shortly…"
                      : "Ask a question… (Enter to send, Shift+Enter for new line)"
                    }
                    rows={1}
                    className="flex-1 resize-none bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed max-h-32 overflow-y-auto"
                    style={{ fieldSizing: "content" } as React.CSSProperties}
                  />
                  <button
                    type="button"
                    onClick={() => void handleAsk()}
                    disabled={!question.trim() || isAsking || isStreaming || !canChat}
                    className="shrink-0 flex items-center justify-center rounded-xl bg-chart-1/80 hover:bg-chart-1 w-9 h-9 text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
                  >
                    {isAsking || isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground/50 px-2">
                  {canChat ? "Enter · send  ·  Shift+Enter · new line" : isInProgress ? "Processing in background…" : ""}
                </p>
              </div>
            </div>

            {/* QUIZ */}
            <div className={`h-full rounded-2xl border border-border/40 bg-card/30 backdrop-blur-md overflow-hidden ${activeTab === "quiz" ? "flex flex-col" : "hidden"}`}>
              <QuizPanel fileId={fileIdNum} />
            </div>

            {/* FLASHCARDS */}
            <div className={`h-full rounded-2xl border border-border/40 bg-card/30 backdrop-blur-md overflow-hidden ${activeTab === "flashcards" ? "flex flex-col" : "hidden"}`}>
              <FlashcardsPanel fileId={fileIdNum} />
            </div>

            {/* MINDMAP */}
            <div className={`h-full overflow-hidden ${activeTab === "mindmap" ? "flex flex-col" : "hidden"}`}>
              {activeTab === "mindmap" && fullReady ? (
                <MindmapPanel fileId={fileIdNum} />
              ) : (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Mindmap will be available once full document analysis finishes.
                </div>
              )}
            </div>

          </div>
        </main>
      </div>
    </div>
  )
}
