import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { motion } from "framer-motion"
import {
  AlertTriangle,
  ArrowLeft,
  BrainCircuit,
  Check,
  ChevronRight,
  FileText,
  History,
  Loader2,
  Play,
  RotateCcw,
  Sparkles,
  Trophy,
} from "lucide-react"
import { toast } from "sonner"
import Squares from "@/components/backgrounds/squares"
import File from "@/components/backgrounds/file"
import ClassroomHeader from "@/components/classroom/header"
import ClassroomSidebar from "@/components/classroom/sidebar"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
import {
  apiErrorDetail,
  classroomApi,
  fileApi,
  folderApi,
  folderQuizApi,
  type FolderQuizDetail,
  type FolderQuizHistoryItem,
  type FolderQuizHistoryResponse,
  type FolderQuizQuestionView,
} from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import { useTheme } from "@/hooks/use-theme"
import type { Classroom, FileItem, Folder } from "@/lib/types"

type Difficulty = "auto" | "easy" | "medium" | "hard"

const DIFFICULTIES: Difficulty[] = ["auto", "easy", "medium", "hard"]

function ScoreTone({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const cls =
    pct >= 70
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-500"
      : pct >= 40
        ? "border-amber-500/30 bg-amber-500/10 text-amber-500"
        : "border-red-500/30 bg-red-500/10 text-red-500"

  return <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>{pct}%</span>
}

function QuestionScore({ score }: { score: number }) {
  const pct = Math.round((score / 5) * 100)
  const cls =
    score >= 4
      ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-500"
      : score >= 2
        ? "border-amber-500/35 bg-amber-500/10 text-amber-500"
        : "border-red-500/35 bg-red-500/10 text-red-500"

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      <Sparkles className="h-3 w-3" />
      {score}/5 · {pct}%
    </span>
  )
}

function FileBadge({ name }: { name: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded-md border border-border/50 bg-background/45 px-2 py-1 text-[11px] text-muted-foreground">
      <FileText className="h-3 w-3 shrink-0" />
      <span className="truncate">{name}</span>
    </span>
  )
}

function FolderTabs({
  active,
  classroomId,
  folderId,
  navigate,
}: {
  active: "files" | "quiz"
  classroomId: number
  folderId: number
  navigate: ReturnType<typeof useNavigate>
}) {
  return (
    <div className="z-20 flex shrink-0 border-b border-border bg-background/80 backdrop-blur-sm">
      <button
        type="button"
        onClick={() => navigate(`/classroom/${classroomId}/folder/${folderId}`)}
        className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
          active === "files"
            ? "border-violet-500 text-foreground"
            : "border-transparent text-muted-foreground hover:text-foreground"
        }`}
      >
        Files
      </button>
      <button
        type="button"
        onClick={() => navigate(`/classroom/${classroomId}/folder/${folderId}/cross-quiz`)}
        className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
          active === "quiz"
            ? "border-violet-500 text-foreground"
            : "border-transparent text-muted-foreground hover:text-foreground"
        }`}
      >
        Cross-file quiz
      </button>
    </div>
  )
}

function SelectableFileCard({
  file,
  selected,
  onToggle,
  color,
}: {
  file: FileItem
  selected: boolean
  onToggle: () => void
  color: string
}) {
  const ready = file.processing_status === "completed"

  return (
    <button
      type="button"
      disabled={!ready}
      onClick={onToggle}
      className={`group relative flex min-h-[230px] flex-col items-center rounded-2xl border p-4 transition-all ${
        ready
          ? "cursor-pointer border-transparent hover:border-chart-1/25 hover:bg-card/35"
          : "cursor-not-allowed border-transparent opacity-45"
      } ${selected ? "border-emerald-500/35 bg-emerald-500/10" : ""}`}
    >
      <span
        className={`absolute right-4 top-4 z-20 flex h-8 w-8 items-center justify-center rounded-full border transition-all ${
          selected
            ? "border-emerald-500 bg-emerald-500 text-white shadow-[0_0_24px_rgba(16,185,129,0.35)]"
            : ready
              ? "border-border/60 bg-background/70 text-transparent group-hover:text-muted-foreground"
              : "border-border/50 bg-background/50 text-muted-foreground"
        }`}
      >
        {selected ? <Check className="h-4 w-4" /> : ready ? <Check className="h-4 w-4 opacity-0 group-hover:opacity-60" /> : null}
      </span>

      <div className="relative mb-2 flex h-[150px] w-full items-center justify-center overflow-visible">
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-chart-1/25 to-chart-2/25 opacity-0 blur-2xl transition-opacity group-hover:opacity-100" />
        <div className={`relative z-10 transition-transform ${selected ? "scale-105" : "group-hover:scale-105"}`}>
          <File color={color} size={1.4} className="cursor-pointer" />
        </div>
      </div>

      <p className="line-clamp-2 min-h-[2.5rem] px-2 text-center text-sm font-semibold leading-tight tracking-wide text-foreground">
        {file.filename}
      </p>
      <span
        className={`mt-2 rounded-full border px-2.5 py-1 text-[11px] capitalize ${
          ready
            ? selected
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"
              : "border-border/50 bg-card/45 text-muted-foreground"
            : file.processing_status === "failed"
              ? "border-red-500/30 bg-red-500/10 text-red-500"
              : "border-border/50 bg-card/35 text-muted-foreground"
        }`}
      >
        {ready ? (selected ? "Selected" : "Ready") : file.processing_status}
      </span>
    </button>
  )
}

function HistoryCard({
  item,
  onOpen,
}: {
  item: FolderQuizHistoryItem
  onOpen: () => void
}) {
  const done = item.status === "submitted"
  const inProgress = item.status === "ready"
  const generating = item.status === "pending" || item.status === "generating"

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-4 rounded-xl border border-border/50 bg-card/45 px-4 py-3 text-left backdrop-blur-sm transition hover:border-chart-1/30 hover:bg-card/65"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border/50 bg-background/50">
        {done ? <Trophy className="h-5 w-5 text-amber-500" /> : <BrainCircuit className="h-5 w-5 text-chart-1" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
          <span className="capitalize">{item.difficulty}</span>
          <span className="text-muted-foreground">·</span>
          <span>{item.total_count || item.num_questions} questions</span>
          <span className="text-muted-foreground">·</span>
          <span>{item.n_files} files</span>
        </span>
        <span className="mt-1 block text-xs text-muted-foreground">
          {done
            ? "Completed quiz"
            : inProgress
              ? `In progress · ${item.graded_count}/${item.total_count} graded`
              : generating
                ? "Generating now"
                : item.status}
        </span>
      </span>
      {done && item.score != null && <ScoreTone score={item.score} />}
      {!done && <span className="rounded-full border border-chart-1/30 bg-chart-1/10 px-2 py-0.5 text-xs text-chart-1">Resume</span>}
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  )
}

function QuestionCard({
  question,
  index,
  total,
  onSubmit,
}: {
  question: FolderQuizQuestionView
  index: number
  total: number
  onSubmit: (questionId: string, answer: string) => Promise<void>
}) {
  const [answer, setAnswer] = useState(question.user_answer ?? "")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setAnswer(question.user_answer ?? "")
  }, [question.id, question.user_answer])

  async function submit() {
    if (submitting || question.submitted) return
    setSubmitting(true)
    try {
      await onSubmit(question.id, answer)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25 }}
      className={`rounded-2xl border p-5 backdrop-blur-sm ${
        question.submitted ? "border-chart-1/25 bg-card/45" : "border-border/50 bg-card/35"
      }`}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Q{index + 1}/{total}</span>
          <span className="rounded-full border border-border/50 bg-background/45 px-2 py-0.5 text-[11px] capitalize text-muted-foreground">
            {question.reasoning_type?.replace(/_/g, " ") || "question"}
          </span>
          {question.hop_depth != null && question.hop_depth > 1 && (
            <span className="rounded-full border border-chart-1/30 bg-chart-1/10 px-2 py-0.5 text-[11px] text-chart-1">
              {question.hop_depth}-hop
            </span>
          )}
        </div>
        {question.submitted && question.score != null && <QuestionScore score={question.score} />}
      </div>

      {question.source_file_names.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {question.source_file_names.map((name) => <FileBadge key={name} name={name} />)}
        </div>
      )}

      <p className="mb-4 text-sm font-medium leading-relaxed text-foreground">{question.question}</p>

      {question.submitted ? (
        <div className="space-y-3">
          <div className="rounded-xl border border-border/40 bg-background/45 px-3 py-2.5">
            <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">Your answer</p>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/80">
              {question.user_answer?.trim() || <span className="text-muted-foreground">No answer given</span>}
            </p>
          </div>

          {question.reference_answer && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2.5">
              <p className="mb-1 text-[11px] uppercase tracking-wide text-emerald-500">Reference answer</p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/80">{question.reference_answer}</p>
            </div>
          )}

          {question.verdict && <p className="text-xs italic text-muted-foreground">{question.verdict}</p>}

          {(question.missing.length > 0 || question.incorrect.length > 0) && (
            <div className="grid gap-2 md:grid-cols-2">
              {question.missing.length > 0 && (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2.5">
                  <p className="mb-1 text-[11px] uppercase tracking-wide text-amber-500">Missing points</p>
                  <ul className="ml-4 list-disc space-y-1 text-xs text-muted-foreground">
                    {question.missing.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                </div>
              )}
              {question.incorrect.length > 0 && (
                <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2.5">
                  <p className="mb-1 text-[11px] uppercase tracking-wide text-red-500">Incorrect points</p>
                  <ul className="ml-4 list-disc space-y-1 text-xs text-muted-foreground">
                    {question.incorrect.map((item, i) => <li key={i}>{item}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <textarea
            rows={4}
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Write your answer..."
            className="w-full resize-none rounded-xl border border-border/60 bg-background/65 px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:ring-2 focus:ring-chart-1/35"
          />
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-55"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            {submitting ? "Grading..." : "Submit answer"}
          </button>
        </div>
      )}
    </motion.div>
  )
}

export default function CrossFileQuizPage() {
  const { id, folderId, quizId } = useParams<{ id: string; folderId: string; quizId?: string }>()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { theme } = useTheme()

  const classroomId = parseInt(id ?? "0", 10)
  const folderIdNum = parseInt(folderId ?? "0", 10)
  const quizIdNum = quizId ? parseInt(quizId, 10) : null
  const baseQuizPath = `/classroom/${classroomId}/folder/${folderIdNum}/cross-quiz`

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [folder, setFolder] = useState<Folder | null>(null)
  const [files, setFiles] = useState<FileItem[]>([])
  const [history, setHistory] = useState<FolderQuizHistoryResponse | null>(null)
  const [quiz, setQuiz] = useState<FolderQuizDetail | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [difficulty, setDifficulty] = useState<Difficulty>("auto")
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const borderColor = theme === "dark" ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)"
  const hoverFillColor = theme === "dark" ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.05)"
  const fileColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  const completedFiles = useMemo(() => files.filter((file) => file.processing_status === "completed"), [files])
  const selectedCompletedCount = completedFiles.filter((file) => selectedIds.has(file.id)).length
  const allSelected = completedFiles.length > 0 && selectedCompletedCount === completedFiles.length

  const refreshHistory = useCallback(async () => {
    const nextHistory = await folderQuizApi.history(folderIdNum)
    setHistory(nextHistory)
  }, [folderIdNum])

  useEffect(() => {
    if (!user) { navigate("/login"); return }
    if (!classroomId || !folderIdNum || isNaN(classroomId) || isNaN(folderIdNum)) return

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [cls, folders, fileList, quizHistory] = await Promise.all([
          classroomApi.get(classroomId),
          folderApi.list(classroomId),
          fileApi.list(folderIdNum),
          folderQuizApi.history(folderIdNum),
        ])
        setClassroom(cls)
        setFiles(fileList)
        setHistory(quizHistory)
        const found = folders.find((item) => item.id === folderIdNum) ?? null
        setFolder(found)
        setSelectedIds(new Set(fileList.filter((file) => file.processing_status === "completed").map((file) => file.id)))
        if (!found) setError("Folder not found")
      } catch (err) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 401) { logout(); navigate("/login") }
        else setError(apiErrorDetail(err, "Failed to load cross-file quiz."))
      } finally {
        setLoading(false)
      }
    }

    void load()
  }, [user, classroomId, folderIdNum]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!quizIdNum || Number.isNaN(quizIdNum)) {
      setQuiz(null)
      return
    }

    let cancelled = false
    let timer: ReturnType<typeof setInterval> | null = null

    const loadQuiz = async () => {
      try {
        const detail = await folderQuizApi.get(quizIdNum)
        if (cancelled) return
        setQuiz(detail)
        if (detail.status === "failed") {
          toast.error(detail.error_msg ?? "Quiz generation failed.")
        }
      } catch (err) {
        if (!cancelled) toast.error(apiErrorDetail(err, "Could not load quiz."))
      }
    }

    void loadQuiz()
    timer = setInterval(async () => {
      try {
        const detail = await folderQuizApi.get(quizIdNum)
        if (cancelled) return
        setQuiz(detail)
        if (detail.status !== "pending" && detail.status !== "generating" && timer) {
          clearInterval(timer)
          timer = null
          void refreshHistory()
        }
      } catch {
        /* keep polling quietly */
      }
    }, 2500)

    return () => {
      cancelled = true
      if (timer) clearInterval(timer)
    }
  }, [quizIdNum, refreshHistory])

  const isOwner = !!(user && classroom && user.id === classroom.owner_id)
  const handleLogout = () => { logout(); navigate("/login") }

  function toggleFile(fileId: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
  }

  function toggleAll() {
    setSelectedIds(allSelected ? new Set() : new Set(completedFiles.map((file) => file.id)))
  }

  async function generateQuiz() {
    if (selectedCompletedCount === 0 || generating) return
    setGenerating(true)
    try {
      const response = await folderQuizApi.generate(folderIdNum, {
        file_ids: [...selectedIds],
        ...(difficulty !== "auto" && { difficulty }),
      })
      await refreshHistory()
      navigate(`${baseQuizPath}/${response.quiz_id}`)
    } catch (err) {
      toast.error(apiErrorDetail(err, "Could not start quiz generation."))
    } finally {
      setGenerating(false)
    }
  }

  const submitQuestion = useCallback(async (questionId: string, answer: string) => {
    if (!quizIdNum) return
    try {
      const res = await folderQuizApi.submitQuestion(quizIdNum, questionId, answer)
      setQuiz((prev) => {
        if (!prev) return prev
        const questions = prev.questions.map((question) =>
          question.id === questionId
            ? {
                ...question,
                submitted: true,
                user_answer: answer,
                score: res.score,
                missing: res.missing,
                incorrect: res.incorrect,
                verdict: res.verdict,
                reference_answer: res.reference_answer,
              }
            : question,
        )
        return {
          ...prev,
          questions,
          graded_count: res.graded_count,
          score: res.aggregate_score,
          correct_count: res.correct_count,
          status: res.finished ? "submitted" : prev.status,
        }
      })
      if (res.finished) void refreshHistory()
    } catch (err) {
      toast.error(apiErrorDetail(err, "Could not submit answer."))
      throw err
    }
  }, [quizIdNum, refreshHistory])

  if (loading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <LoadingOrb size={96} />
          <p className="text-sm text-muted-foreground">Loading cross-file quiz...</p>
        </div>
      </div>
    )
  }

  if (error || !classroom || !folder) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "Folder not found"}</p>
          <button
            type="button"
            onClick={() => navigate(`/classroom/${classroomId}/folder/${folderIdNum}`)}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
          >
            Back to folder
          </button>
        </div>
      </div>
    )
  }

  const questions = quiz?.questions ?? []
  const answered = questions.filter((question) => question.submitted).length
  const progress = questions.length ? (answered / questions.length) * 100 : 0
  const aggregateScore = quiz?.score != null ? Math.round(quiz.score * 100) : null
  const activeOpenQuiz = history?.items.find((item) => item.quiz_id === history.open_quiz_id)

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <ClassroomHeader
        classroomName={classroom.name}
        folderName={folder.name}
        classroomId={classroomId}
        username={user?.username ?? ""}
        onMenuClick={() => setSidebarCollapsed((value) => !value)}
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
          <FolderTabs
            active="quiz"
            classroomId={classroomId}
            folderId={folderIdNum}
            navigate={navigate}
          />

          <div className="relative flex-1 overflow-hidden">
            <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
              <Squares speed={0.5} squareSize={40} direction="diagonal" borderColor={borderColor} hoverFillColor={hoverFillColor} />
            </div>
            <div className="relative z-10 h-full overflow-y-auto overflow-x-hidden">
              {!quizIdNum ? (
                <div className="mx-auto max-w-[1400px] px-4 pb-10 pt-10 sm:px-6 md:px-8">
                  <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
                    <div>
                      <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-chart-1/30 bg-chart-1/10 px-3 py-1 text-xs text-chart-1">
                        <BrainCircuit className="h-3.5 w-3.5" />
                        Folder-level synthesis
                      </div>
                      <h1 className="text-2xl font-semibold tracking-tight text-foreground">Cross-file quiz</h1>
                      <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                        Select the completed files you want SAMpai to connect, choose a difficulty, then generate a quiz on its own page.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={toggleAll}
                      disabled={completedFiles.length === 0}
                      className="rounded-xl border border-border/60 bg-card/55 px-4 py-2 text-sm font-medium text-foreground transition hover:bg-card/75 disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      {allSelected ? "Deselect all" : "Select all ready files"}
                    </button>
                  </div>

                  {activeOpenQuiz && (
                    <div className="mb-8 rounded-2xl border border-chart-1/30 bg-card/65 p-4 backdrop-blur-xl">
                      <div className="flex flex-wrap items-center gap-4">
                        <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-chart-1/30 bg-chart-1/10">
                          <History className="h-5 w-5 text-chart-1" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-foreground">You have a quiz in progress</p>
                          <p className="text-xs text-muted-foreground">
                            {activeOpenQuiz.graded_count}/{activeOpenQuiz.total_count} graded · {activeOpenQuiz.n_files} files
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => navigate(`${baseQuizPath}/${activeOpenQuiz.quiz_id}`)}
                          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
                        >
                          Resume quiz
                          <ChevronRight className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
                    <section>
                      <div className="mb-4 flex items-center justify-between gap-3">
                        <div>
                          <h2 className="text-sm font-semibold text-foreground">Choose files</h2>
                          <p className="text-xs text-muted-foreground">
                            {completedFiles.length} ready · {selectedCompletedCount} selected
                          </p>
                        </div>
                      </div>

                      {files.length === 0 ? (
                        <div className="rounded-2xl border border-border/50 bg-card/45 px-5 py-12 text-center text-sm text-muted-foreground">
                          No files in this folder yet.
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
                          {files.map((file) => (
                            <SelectableFileCard
                              key={file.id}
                              file={file}
                              selected={selectedIds.has(file.id)}
                              onToggle={() => file.processing_status === "completed" && toggleFile(file.id)}
                              color={fileColor}
                            />
                          ))}
                        </div>
                      )}
                    </section>

                    <aside className="space-y-5">
                      <div className="rounded-2xl border border-border/50 bg-card/65 p-5 backdrop-blur-xl">
                        <h2 className="text-sm font-semibold text-foreground">Difficulty</h2>
                        <div className="mt-4 grid grid-cols-2 gap-2">
                          {DIFFICULTIES.map((item) => (
                            <button
                              key={item}
                              type="button"
                              onClick={() => setDifficulty(item)}
                              className={`rounded-xl border px-3 py-2 text-sm font-medium capitalize transition ${
                                difficulty === item
                                  ? "border-chart-1/60 bg-chart-1/15 text-foreground"
                                  : "border-border/60 bg-background/45 text-muted-foreground hover:text-foreground"
                              }`}
                            >
                              {item}
                            </button>
                          ))}
                        </div>
                        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                          Auto adapts from your recent scores. Harder quizzes ask for deeper cross-file reasoning.
                        </p>
                        <button
                          type="button"
                          onClick={generateQuiz}
                          disabled={selectedCompletedCount === 0 || generating}
                          className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] px-4 py-3 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                          {generating ? "Starting..." : `Generate quiz (${selectedCompletedCount} files)`}
                        </button>
                      </div>

                      <div className="rounded-2xl border border-border/50 bg-card/55 p-5 backdrop-blur-xl">
                        <div className="mb-4 flex items-center gap-2">
                          <History className="h-4 w-4 text-chart-1" />
                          <h2 className="text-sm font-semibold text-foreground">Past quizzes</h2>
                        </div>
                        {(history?.items ?? []).length === 0 ? (
                          <p className="text-sm text-muted-foreground">Generated quizzes will appear here.</p>
                        ) : (
                          <div className="space-y-3">
                            {history!.items.slice(0, 6).map((item) => (
                              <HistoryCard
                                key={item.quiz_id}
                                item={item}
                                onOpen={() => navigate(`${baseQuizPath}/${item.quiz_id}`)}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    </aside>
                  </div>
                </div>
              ) : (
                <div className="mx-auto w-full max-w-4xl px-4 pb-10 pt-10 sm:px-6 md:px-8">
                  <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
                    <button
                      type="button"
                      onClick={() => navigate(baseQuizPath)}
                      className="inline-flex items-center gap-2 text-sm text-muted-foreground transition hover:text-foreground"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      Back to cross-file quiz
                    </button>
                    {quiz?.status === "submitted" && (
                      <button
                        type="button"
                        onClick={() => navigate(baseQuizPath)}
                        className="inline-flex items-center gap-2 rounded-xl border border-border/60 bg-card/55 px-4 py-2 text-sm font-medium text-foreground transition hover:bg-card/75"
                      >
                        <RotateCcw className="h-4 w-4" />
                        New quiz
                      </button>
                    )}
                  </div>

                  {!quiz || quiz.status === "pending" || quiz.status === "generating" ? (
                    <div className="rounded-2xl border border-border/50 bg-card/55 px-6 py-20 text-center backdrop-blur-xl">
                      <LoadingOrb size={92} />
                      <p className="mt-5 text-sm font-semibold text-foreground">Generating your cross-file quiz...</p>
                      <p className="mx-auto mt-2 max-w-md text-xs text-muted-foreground">
                        SAMpai is building questions from the selected files. This page will update automatically.
                      </p>
                    </div>
                  ) : quiz.status === "failed" ? (
                    <div className="rounded-2xl border border-red-500/25 bg-red-500/10 px-5 py-4">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="mt-0.5 h-5 w-5 text-red-500" />
                        <div>
                          <p className="text-sm font-semibold text-foreground">Generation failed</p>
                          <p className="mt-1 text-sm text-muted-foreground">{quiz.error_msg ?? "Please try again with a different selection."}</p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      <div className="rounded-2xl border border-border/50 bg-card/55 p-5 backdrop-blur-xl">
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div>
                            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-chart-1/30 bg-chart-1/10 px-3 py-1 text-xs capitalize text-chart-1">
                              <BrainCircuit className="h-3.5 w-3.5" />
                              {quiz.difficulty} quiz
                            </div>
                            <h1 className="text-xl font-semibold text-foreground">
                              {quiz.status === "submitted" ? "Quiz complete" : "Answer the questions"}
                            </h1>
                            <p className="mt-1 text-sm text-muted-foreground">
                              {quiz.files.length} files · {answered}/{questions.length} answered
                            </p>
                          </div>
                          {quiz.status === "submitted" && aggregateScore != null && (
                            <div className="text-right">
                              <p className="text-xs text-muted-foreground">Score</p>
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
                            </div>
                          )}
                        </div>
                        <div className="mt-4 h-2 overflow-hidden rounded-full bg-border/40">
                          <div className="h-full rounded-full bg-chart-1 transition-all duration-500" style={{ width: `${progress}%` }} />
                        </div>
                      </div>

                      {(quiz.warnings ?? []).length > 0 && (
                        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3">
                          <div className="flex items-start gap-2">
                            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                            <div className="space-y-1 text-xs text-muted-foreground">
                              {quiz.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
                            </div>
                          </div>
                        </div>
                      )}

                      {quiz.files.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {quiz.files.map((file) => (
                            <FileBadge key={`${file.file_id}-${file.filename}`} name={file.filename} />
                          ))}
                        </div>
                      )}

                      {quiz.status === "submitted" && quiz.topic_scores.length > 0 && (
                        <div className="rounded-2xl border border-border/50 bg-card/55 backdrop-blur-xl">
                          <p className="border-b border-border/40 px-5 py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                            Performance by file
                          </p>
                          <div className="space-y-3 p-5">
                            {quiz.topic_scores.map((topic) => {
                              const pct = Math.round(topic.mean_score * 100)
                              return (
                                <div key={`${topic.file_id}-${topic.filename}`}>
                                  <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                                    <span className="min-w-0 truncate text-foreground">{topic.filename}</span>
                                    <span className="shrink-0 text-muted-foreground">
                                      {pct}% · {topic.correct_count}/{topic.question_count}
                                    </span>
                                  </div>
                                  <div className="h-1.5 overflow-hidden rounded-full bg-border/40">
                                    <div
                                      className={`h-full rounded-full ${pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500"}`}
                                      style={{ width: `${pct}%` }}
                                    />
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )}

                      <div className="space-y-4">
                        {questions.map((question, index) => (
                          <QuestionCard
                            key={question.id}
                            question={question}
                            index={index}
                            total={questions.length}
                            onSubmit={submitQuestion}
                          />
                        ))}
                      </div>

                      {quiz.status === "submitted" && (
                        <div className="rounded-2xl border border-border/50 bg-card/55 p-5 text-center backdrop-blur-xl">
                          <Trophy className="mx-auto h-8 w-8 text-amber-500" />
                          <p className="mt-3 text-sm font-semibold text-foreground">Nice, this quiz is saved.</p>
                          <p className="mt-1 text-xs text-muted-foreground">Return to the cross-file quiz page to start another one or revisit past attempts.</p>
                          <button
                            type="button"
                            onClick={() => navigate(baseQuizPath)}
                            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] px-5 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
                          >
                            Back to cross-file quiz
                            <ChevronRight className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
