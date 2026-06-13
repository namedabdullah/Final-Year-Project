import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import {
  ArrowLeft,
  BrainCircuit,
  Check,
  CheckSquare,
  ChevronDown,
  ChevronUp,
  FileText,
  Layers,
  Square,
} from "lucide-react"
import { toast } from "sonner"
import ClassroomHeader from "@/components/classroom/header"
import ClassroomSidebar from "@/components/classroom/sidebar"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
import {
  apiErrorDetail,
  classroomApi,
  fileApi,
  folderApi,
  folderQuizApi,
  type FileItem,
  type FolderQuizDetail,
  type FolderQuizQuestionView,
} from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import type { Classroom, Folder } from "@/lib/types"

type Difficulty = "auto" | "easy" | "medium" | "hard"
type Stage = "select" | "generating" | "answering" | "done"

// ── Score chip ────────────────────────────────────────────────────────────────

function ScoreChip({ score }: { score: number }) {
  const pct = Math.round((score / 5) * 100)
  const cls =
    score >= 4
      ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-400"
      : score >= 2
      ? "border-amber-400/40 bg-amber-500/15 text-amber-400"
      : "border-red-400/40 bg-red-500/15 text-red-400"
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium ${cls}`}>
      {score}/5 · {pct}%
    </span>
  )
}

// ── File badge ────────────────────────────────────────────────────────────────

function FileBadge({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-border/40 bg-card/40 text-[11px] text-muted-foreground">
      <FileText className="w-3 h-3 shrink-0" />
      {name}
    </span>
  )
}

// ── Question card ─────────────────────────────────────────────────────────────

function QuestionCard({
  q,
  index,
  total,
  onSubmit,
}: {
  q: FolderQuizQuestionView
  index: number
  total: number
  onSubmit: (questionId: string, answer: string) => Promise<void>
}) {
  const [draft, setDraft] = useState(q.user_answer ?? "")
  const [submitting, setSubmitting] = useState(false)
  const [showRef, setShowRef] = useState(false)

  const scoreColor =
    q.score == null
      ? ""
      : q.score >= 4
      ? "border-emerald-500/30 bg-emerald-500/5"
      : q.score >= 2
      ? "border-amber-500/30 bg-amber-500/5"
      : "border-red-500/30 bg-red-500/5"

  async function handleSubmit() {
    if (!draft.trim() || submitting) return
    setSubmitting(true)
    try {
      await onSubmit(q.id, draft.trim())
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.3 }}
      className={`rounded-2xl border p-5 transition-colors ${
        q.submitted ? scoreColor : "border-border/50 bg-card/30"
      } backdrop-blur-sm`}
    >
      {/* Question header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-muted-foreground/50">
            Q{index + 1}/{total}
          </span>
          <span className="text-[11px] px-2 py-0.5 rounded-full border border-border/40 bg-card/30 text-muted-foreground capitalize">
            {q.reasoning_type?.replace(/_/g, " ")}
          </span>
          {q.hop_depth != null && q.hop_depth > 1 && (
            <span className="text-[11px] px-2 py-0.5 rounded-full border border-chart-1/30 bg-chart-1/10 text-chart-1">
              {q.hop_depth}-hop
            </span>
          )}
        </div>
        {q.submitted && q.score != null && <ScoreChip score={q.score} />}
      </div>

      {/* Source files */}
      {q.source_file_names.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {q.source_file_names.map((name) => (
            <FileBadge key={name} name={name} />
          ))}
        </div>
      )}

      {/* Question text */}
      <p className="text-sm font-medium text-foreground leading-relaxed mb-4">{q.question}</p>

      {/* Answer area */}
      {!q.submitted ? (
        <div className="space-y-2.5">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={4}
            placeholder="Type your answer here…"
            className="w-full rounded-xl border border-border/50 bg-background/60 px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:ring-2 focus:ring-chart-1/40 resize-none"
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!draft.trim() || submitting}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] text-sm font-medium text-white hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <Check className="w-3.5 h-3.5" />
            {submitting ? "Submitting…" : "Submit answer"}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Your answer */}
          <div className="rounded-xl border border-border/30 bg-background/40 px-3 py-2.5">
            <p className="text-[11px] text-muted-foreground/50 mb-1">Your answer</p>
            <p className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap">{q.user_answer}</p>
          </div>

          {/* Verdict */}
          {q.verdict && (
            <p className="text-xs text-muted-foreground italic">{q.verdict}</p>
          )}

          {/* Missing / Incorrect points */}
          {(q.missing.length > 0 || q.incorrect.length > 0) && (
            <div className="space-y-1.5">
              {q.missing.length > 0 && (
                <div>
                  <p className="text-[11px] text-amber-500/70 mb-0.5">Missing points</p>
                  <ul className="space-y-0.5">
                    {q.missing.map((m, i) => (
                      <li key={i} className="text-xs text-muted-foreground/70 flex items-start gap-1.5">
                        <span className="text-amber-500/50 mt-0.5">•</span>{m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {q.incorrect.length > 0 && (
                <div>
                  <p className="text-[11px] text-red-500/70 mb-0.5">Incorrect points</p>
                  <ul className="space-y-0.5">
                    {q.incorrect.map((m, i) => (
                      <li key={i} className="text-xs text-muted-foreground/70 flex items-start gap-1.5">
                        <span className="text-red-500/50 mt-0.5">•</span>{m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Reference answer (collapsible) */}
          {q.reference_answer && (
            <div>
              <button
                type="button"
                onClick={() => setShowRef((v) => !v)}
                className="flex items-center gap-1 text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-pointer"
              >
                {showRef ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                {showRef ? "Hide" : "Show"} reference answer
              </button>
              {showRef && (
                <div className="mt-1.5 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5">
                  <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">{q.reference_answer}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CrossFileQuizPage() {
  const { id, folderId } = useParams<{ id: string; folderId: string }>()
  const navigate = useNavigate()
  const { user, logout } = useAuth()

  const classroomId = parseInt(id ?? "0", 10)
  const folderIdNum = parseInt(folderId ?? "0", 10)

  // ── page data ──
  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [folder, setFolder] = useState<Folder | null>(null)
  const [files, setFiles] = useState<FileItem[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [pageError, setPageError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  useEffect(() => {
    if (!user) { navigate("/login"); return }
    const load = async () => {
      try {
        const [cls, folders, fileList] = await Promise.all([
          classroomApi.get(classroomId),
          folderApi.list(classroomId),
          fileApi.list(folderIdNum),
        ])
        setClassroom(cls)
        const found = folders.find((f) => f.id === folderIdNum) ?? null
        setFolder(found)
        setFiles(fileList)
      } catch (e) {
        const status = (e as { response?: { status?: number } })?.response?.status
        if (status === 401) { logout(); navigate("/login") }
        else setPageError(apiErrorDetail(e, "Failed to load folder."))
      } finally {
        setPageLoading(false)
      }
    }
    void load()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── quiz state ──
  const [stage, setStage] = useState<Stage>("select")
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [difficulty, setDifficulty] = useState<Difficulty>("auto")
  const [quizId, setQuizId] = useState<number | null>(null)
  const [quiz, setQuiz] = useState<FolderQuizDetail | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollStartRef = useRef(0)

  // resume open quiz on mount (after files loaded)
  const resumeChecked = useRef(false)
  useEffect(() => {
    if (pageLoading || resumeChecked.current) return
    resumeChecked.current = true
    folderQuizApi.history(folderIdNum)
      .then(async (h) => {
        if (h.has_open_quiz && h.open_quiz_id != null) {
          const detail = await folderQuizApi.get(h.open_quiz_id)
          setQuizId(h.open_quiz_id)
          setQuiz(detail)
          if (detail.status === "ready") setStage("answering")
          else if (detail.status === "submitted") setStage("done")
          else if (detail.status === "pending" || detail.status === "generating") {
            pollStartRef.current = Date.now(); setStage("generating")
          }
        }
      })
      .catch(() => {})
  }, [pageLoading]) // eslint-disable-line react-hooks/exhaustive-deps

  // poll while generating
  useEffect(() => {
    if (stage !== "generating" || quizId == null) return
    const interval = setInterval(async () => {
      if (Date.now() - pollStartRef.current > 180_000) {
        clearInterval(interval)
        toast.error("Quiz generation timed out. Please try again.")
        setStage("select")
        return
      }
      try {
        const detail = await folderQuizApi.get(quizId)
        setQuiz(detail)
        if (detail.status === "ready") { clearInterval(interval); setStage("answering") }
        else if (detail.status === "failed") {
          clearInterval(interval)
          toast.error(detail.error_msg ?? "Generation failed.")
          setStage("select")
        }
      } catch {}
    }, 2500)
    return () => clearInterval(interval)
  }, [stage, quizId])

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  // ── file selection ──
  const completedFiles = files.filter((f) => f.processing_status === "completed")

  const toggleFile = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const allSelected = completedFiles.length > 0 && selectedIds.size === completedFiles.length
  const toggleAll = () => {
    if (allSelected) setSelectedIds(new Set())
    else setSelectedIds(new Set(completedFiles.map((f) => f.id)))
  }

  // ── generate ──
  async function handleGenerate() {
    if (selectedIds.size === 0) return
    try {
      const body: Parameters<typeof folderQuizApi.generate>[1] = {
        file_ids: [...selectedIds],
        ...(difficulty !== "auto" && { difficulty }),
      }
      const res = await folderQuizApi.generate(folderIdNum, body)
      setQuizId(res.quiz_id)
      setQuiz(null)
      pollStartRef.current = Date.now()
      setStage("generating")
    } catch (e) {
      toast.error(apiErrorDetail(e, "Could not start quiz generation."))
    }
  }

  // ── submit a single question ──
  const submitQuestion = useCallback(async (questionId: string, answer: string) => {
    if (!quizId) return
    try {
      const res = await folderQuizApi.submitQuestion(quizId, questionId, answer)
      setQuiz((prev) => {
        if (!prev) return prev
        const updatedQs = prev.questions.map((q) =>
          q.id === questionId
            ? {
                ...q,
                submitted: true,
                user_answer: answer,
                score: res.score,
                missing: res.missing,
                incorrect: res.incorrect,
                verdict: res.verdict,
                reference_answer: res.reference_answer,
              }
            : q,
        )
        return {
          ...prev,
          questions: updatedQs,
          graded_count: res.graded_count,
          score: res.aggregate_score,
          correct_count: res.correct_count,
          status: res.finished ? "submitted" : prev.status,
        }
      })
      if (res.finished) setStage("done")
    } catch (e) {
      toast.error(apiErrorDetail(e, "Could not submit answer."))
      throw e
    }
  }, [quizId])

  // ── helpers ──
  const isOwner = !!(user && classroom && user.id === classroom.owner_id)
  const handleLogout = () => { logout(); navigate("/login") }
  const backToFolder = () => navigate(`/classroom/${classroomId}/folder/${folderIdNum}`)

  // ── derived ──
  const questions = quiz?.questions ?? []
  const submittedCount = questions.filter((q) => q.submitted).length
  const progressPct = questions.length > 0 ? (submittedCount / questions.length) * 100 : 0
  const aggregateScore = quiz?.score != null ? Math.round(quiz.score * 100) : null

  // ── loading / error states ──
  if (pageLoading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <LoadingOrb size={96} />
          <p className="text-sm text-muted-foreground">Loading…</p>
        </div>
      </div>
    )
  }

  if (pageError || !classroom || !folder) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{pageError ?? "Folder not found"}</p>
          <button onClick={backToFolder} className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer">
            Back to Folder
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <ClassroomHeader
        classroomName={classroom.name}
        folderName={folder.name}
        classroomId={classroomId}
        username={user?.username ?? ""}
        onMenuClick={() => setSidebarCollapsed((v) => !v)}
        onLogout={handleLogout}
      />

      <div className="flex pt-16">
        <ClassroomSidebar
          collapsed={sidebarCollapsed}
          currentClassroomId={classroomId}
          onHomeClick={() => navigate(isOwner ? "/created" : "/joined")}
        />

        <main
          className={`flex-1 flex flex-col min-h-[calc(100vh-4rem)] transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          <div className="max-w-3xl mx-auto w-full px-6 py-8">

            {/* Back + title */}
            <div className="flex items-center gap-3 mb-8">
              <button
                type="button"
                onClick={stage === "select" ? backToFolder : () => { setStage("select"); setQuiz(null); setQuizId(null) }}
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
                {stage === "select" ? "Back to folder" : "Start over"}
              </button>
            </div>

            <div className="flex items-center gap-3 mb-8">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl border border-border/40 bg-card/40">
                <Layers className="w-5 h-5 text-chart-1" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-foreground">Cross-File Quiz</h1>
                <p className="text-xs text-muted-foreground/70">{folder.name}</p>
              </div>
            </div>

            <AnimatePresence mode="wait">

              {/* ── SELECT stage ── */}
              {stage === "select" && (
                <motion.div
                  key="select"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.25 }}
                  className="space-y-6"
                >
                  {/* File picker */}
                  <div className="rounded-2xl border border-border/50 bg-card/30 backdrop-blur-sm overflow-hidden">
                    <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/30">
                      <div>
                        <p className="text-sm font-medium text-foreground">Select files</p>
                        <p className="text-xs text-muted-foreground/60 mt-0.5">
                          {completedFiles.length} completed · {selectedIds.size} selected
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={toggleAll}
                        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer px-3 py-1.5 rounded-lg border border-border/40 hover:bg-card/50"
                      >
                        {allSelected
                          ? <><CheckSquare className="w-3.5 h-3.5" /> Deselect all</>
                          : <><Square className="w-3.5 h-3.5" /> Select all</>}
                      </button>
                    </div>

                    {files.length === 0 ? (
                      <div className="px-5 py-10 text-center">
                        <p className="text-sm text-muted-foreground">No files in this folder yet.</p>
                      </div>
                    ) : (
                      <ul className="divide-y divide-border/20">
                        {files.map((file) => {
                          const ready = file.processing_status === "completed"
                          const checked = selectedIds.has(file.id)
                          return (
                            <li key={file.id}>
                              <button
                                type="button"
                                onClick={() => ready && toggleFile(file.id)}
                                disabled={!ready}
                                className={`w-full flex items-center gap-3 px-5 py-3.5 text-left transition-colors ${
                                  ready
                                    ? "hover:bg-card/40 cursor-pointer"
                                    : "opacity-45 cursor-not-allowed"
                                } ${checked ? "bg-chart-1/5" : ""}`}
                              >
                                {/* Checkbox */}
                                <div
                                  className={`flex-none w-4 h-4 rounded border flex items-center justify-center transition-all ${
                                    checked
                                      ? "border-chart-1 bg-chart-1"
                                      : "border-border/60 bg-transparent"
                                  }`}
                                >
                                  {checked && <Check className="w-2.5 h-2.5 text-white" />}
                                </div>

                                <FileText className="flex-none w-4 h-4 text-muted-foreground/60" />

                                <div className="flex-1 min-w-0">
                                  <p className="text-sm text-foreground truncate">{file.filename}</p>
                                </div>

                                <span
                                  className={`flex-none text-[11px] px-2 py-0.5 rounded-full border capitalize ${
                                    ready
                                      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-500"
                                      : file.processing_status === "failed"
                                      ? "border-red-400/30 bg-red-500/10 text-red-500"
                                      : "border-border/40 bg-card/20 text-muted-foreground"
                                  }`}
                                >
                                  {ready ? "Ready" : file.processing_status}
                                </span>
                              </button>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </div>

                  {/* Difficulty */}
                  <div className="space-y-2.5">
                    <p className="text-[11px] uppercase tracking-wider text-muted-foreground/50 font-medium">Difficulty</p>
                    <div className="flex flex-wrap gap-2">
                      {(["auto", "easy", "medium", "hard"] as Difficulty[]).map((d) => (
                        <button
                          key={d}
                          type="button"
                          onClick={() => setDifficulty(d)}
                          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer border ${
                            difficulty === d
                              ? "border-chart-1/60 bg-chart-1/20 text-foreground"
                              : "border-border/40 bg-card/20 text-muted-foreground hover:border-border/60 hover:text-foreground"
                          }`}
                        >
                          {d === "auto" ? "Auto" : d[0].toUpperCase() + d.slice(1)}
                        </button>
                      ))}
                    </div>
                    {difficulty !== "auto" && (
                      <p className="text-xs text-muted-foreground/50">
                        {difficulty === "easy" && "Shallow BFS — direct, single-document questions."}
                        {difficulty === "medium" && "Moderate BFS — some cross-file synthesis required."}
                        {difficulty === "hard" && "Deep BFS — questions span multiple files with multi-hop reasoning."}
                      </p>
                    )}
                  </div>

                  {/* Generate button */}
                  <button
                    type="button"
                    onClick={handleGenerate}
                    disabled={selectedIds.size === 0}
                    className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] text-sm font-medium text-white hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  >
                    <BrainCircuit className="w-4 h-4" />
                    Generate quiz from {selectedIds.size} file{selectedIds.size !== 1 ? "s" : ""}
                  </button>
                </motion.div>
              )}

              {/* ── GENERATING stage ── */}
              {stage === "generating" && (
                <motion.div
                  key="generating"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-center gap-5 py-24"
                >
                  <div className="flex gap-1.5 items-center">
                    {[0, 1, 2].map((i) => (
                      <motion.span
                        key={i}
                        className="block w-2.5 h-2.5 rounded-full bg-chart-1/70"
                        animate={{ y: [0, -8, 0] }}
                        transition={{ duration: 0.9, delay: i * 0.18, repeat: Infinity, ease: "easeInOut" }}
                      />
                    ))}
                  </div>
                  <div className="text-center space-y-1">
                    <p className="text-sm font-medium text-foreground">Generating cross-file quiz…</p>
                    <p className="text-xs text-muted-foreground/60">
                      SAMpai is drawing connections across your selected files. This may take a minute.
                    </p>
                  </div>
                </motion.div>
              )}

              {/* ── ANSWERING stage ── */}
              {stage === "answering" && quiz && (
                <motion.div
                  key="answering"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="space-y-5"
                >
                  {/* Progress header */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        <span className="capitalize">{quiz.difficulty} quiz</span>
                        {quiz.files.length > 0 && (
                          <span className="text-muted-foreground/50">· {quiz.files.length} file{quiz.files.length !== 1 ? "s" : ""}</span>
                        )}
                      </span>
                      <span>{submittedCount} / {questions.length} answered</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-border/30 overflow-hidden">
                      <div
                        className="h-full bg-chart-1/60 rounded-full transition-all duration-500"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  </div>

                  {/* File contributions */}
                  {quiz.files.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {quiz.files.map((f) => (
                        <span
                          key={f.filename}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-border/40 bg-card/30 text-[11px] text-muted-foreground"
                        >
                          <FileText className="w-3 h-3" />
                          {f.filename}
                          <span className="text-muted-foreground/40 ml-0.5">·{f.seed_count}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Questions */}
                  <div className="space-y-4">
                    {questions.map((q, i) => (
                      <QuestionCard
                        key={q.id}
                        q={q}
                        index={i}
                        total={questions.length}
                        onSubmit={submitQuestion}
                      />
                    ))}
                  </div>
                </motion.div>
              )}

              {/* ── DONE stage ── */}
              {stage === "done" && quiz && (
                <motion.div
                  key="done"
                  initial={{ opacity: 0, scale: 0.97 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  className="space-y-6"
                >
                  {/* Score card */}
                  <div className="rounded-2xl border border-border/50 bg-card/30 backdrop-blur-sm p-6 text-center space-y-3">
                    <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl border border-border/40 bg-card/40 mb-1">
                      <BrainCircuit className="w-7 h-7 text-chart-1" />
                    </div>
                    <p className="text-sm text-muted-foreground">Quiz complete</p>
                    {aggregateScore != null ? (
                      <p
                        className={`text-4xl font-bold ${
                          aggregateScore >= 70
                            ? "text-emerald-500"
                            : aggregateScore >= 40
                            ? "text-amber-500"
                            : "text-red-500"
                        }`}
                      >
                        {aggregateScore}%
                      </p>
                    ) : (
                      <p className="text-4xl font-bold text-muted-foreground">—</p>
                    )}
                    <p className="text-xs text-muted-foreground/70">
                      {quiz.correct_count ?? submittedCount} of {questions.length} questions answered
                    </p>
                  </div>

                  {/* Per-file scores */}
                  {quiz.topic_scores.length > 0 && (
                    <div className="rounded-2xl border border-border/50 bg-card/30 backdrop-blur-sm overflow-hidden">
                      <p className="text-xs font-medium text-muted-foreground/60 px-5 py-3 border-b border-border/30 uppercase tracking-wider">
                        Per-file breakdown
                      </p>
                      <ul className="divide-y divide-border/20">
                        {quiz.topic_scores.map((ts) => {
                          const pct = Math.round(ts.mean_score * 100)
                          return (
                            <li key={ts.filename} className="flex items-center gap-3 px-5 py-3">
                              <FileText className="w-4 h-4 text-muted-foreground/40 flex-none" />
                              <span className="flex-1 text-sm text-foreground truncate">{ts.filename}</span>
                              <span className="text-xs text-muted-foreground/60">
                                {ts.question_count} Q{ts.question_count !== 1 ? "s" : ""}
                              </span>
                              <span
                                className={`text-sm font-semibold ${
                                  pct >= 70 ? "text-emerald-500" : pct >= 40 ? "text-amber-500" : "text-red-500"
                                }`}
                              >
                                {pct}%
                              </span>
                            </li>
                          )
                        })}
                      </ul>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => { setStage("select"); setQuiz(null); setQuizId(null); setSelectedIds(new Set()) }}
                      className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] text-sm font-medium text-white hover:opacity-90 transition-opacity cursor-pointer"
                    >
                      New quiz
                    </button>
                    <button
                      type="button"
                      onClick={backToFolder}
                      className="px-5 py-2.5 rounded-xl border border-border/40 bg-card/30 text-sm text-foreground hover:bg-card/50 cursor-pointer transition-colors"
                    >
                      Back to folder
                    </button>
                  </div>
                </motion.div>
              )}

            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  )
}
