import { useCallback, useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { BookOpen, CheckCircle2, ChevronDown, ChevronRight, RotateCcw, Send, XCircle } from "lucide-react"
import { toast } from "sonner"
import {
  apiErrorDetail,
  quizApi,
  type QuizAnswerReview,
  type QuizDetail,
  type QuizHistoryItem,
  type QuizQuestionPublic,
  type SubmitAnswer,
} from "@/api/sampai"

type Count = 5 | 10 | 15
type Diff = "auto" | "easy" | "medium" | "hard"
type Answer = number | boolean
type State = "idle" | "generating" | "ready" | "submitting" | "submitted" | "failed"

const COUNTS: Count[] = [5, 10, 15]
const DIFFS: Diff[] = ["auto", "easy", "medium", "hard"]

// ── Pill ─────────────────────────────────────────────────────────────────────

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-all cursor-pointer ${
        active
          ? "border border-chart-1/60 bg-chart-1/20 text-foreground"
          : "border border-border/40 bg-card/20 text-muted-foreground hover:border-border/60 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  )
}

// ── InProgress ───────────────────────────────────────────────────────────────

function InProgress({
  quiz,
  answers,
  setAnswer,
  submitting,
  onSubmit,
}: {
  quiz: QuizDetail
  answers: Record<string, Answer>
  setAnswer: (id: string, a: Answer) => void
  submitting: boolean
  onSubmit: () => void
}) {
  const questions = quiz.questions ?? []
  const answeredCount = questions.filter((q) => answers[q.id] !== undefined).length
  const allAnswered = questions.length > 0 && answeredCount === questions.length

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="shrink-0 px-5 pt-4 pb-3 border-b border-border/30">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm capitalize text-muted-foreground">
            {quiz.difficulty} quiz
          </span>
          <span className="text-xs text-muted-foreground/60">
            {answeredCount} / {questions.length} answered
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-border/30">
          <div
            className="h-full bg-chart-1/60 transition-all duration-500"
            style={{ width: `${questions.length > 0 ? (answeredCount / questions.length) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Questions */}
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-4">
        {questions.map((q, i) => (
          <QuestionCard key={q.id} q={q} index={i} answer={answers[q.id]} onAnswer={(a) => setAnswer(q.id, a)} />
        ))}
      </div>

      {/* Footer */}
      <div className="shrink-0 px-5 py-3 border-t border-border/30 flex items-center justify-between bg-card/40 backdrop-blur-sm">
        <span className="text-xs text-muted-foreground/60">
          {allAnswered ? "All answered" : `${questions.length - answeredCount} left`}
        </span>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!allAnswered || submitting}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] text-sm font-medium text-white hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          <Send className="h-3.5 w-3.5" />
          {submitting ? "Submitting…" : "Submit"}
        </button>
      </div>
    </div>
  )
}

function QuestionCard({
  q,
  index,
  answer,
  onAnswer,
}: {
  q: QuizQuestionPublic
  index: number
  answer: Answer | undefined
  onAnswer: (a: Answer) => void
}) {
  return (
    <div className="rounded-2xl border border-border/50 bg-card/30 backdrop-blur-sm p-4">
      <p className="mb-3 text-sm font-medium text-foreground leading-relaxed">
        <span className="text-muted-foreground/50 mr-1">{index + 1}.</span>
        {q.question}
      </p>
      {q.type === "mcq" ? (
        <div className="space-y-2">
          {q.options.map((opt, idx) => {
            const sel = answer === idx
            return (
              <button
                key={idx}
                type="button"
                onClick={() => onAnswer(idx)}
                className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left text-sm transition-all cursor-pointer ${
                  sel
                    ? "border-chart-1/60 bg-chart-1/15 text-foreground"
                    : "border-border/40 text-muted-foreground hover:border-border/60 hover:text-foreground"
                }`}
              >
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-medium ${
                    sel ? "border-chart-1 bg-chart-1/80 text-white" : "border-border/60 text-muted-foreground/60"
                  }`}
                >
                  {String.fromCharCode(65 + idx)}
                </span>
                {opt}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="flex gap-2">
          {[true, false].map((b) => {
            const sel = answer === b
            return (
              <button
                key={String(b)}
                type="button"
                onClick={() => onAnswer(b)}
                className={`flex-1 rounded-xl border px-3 py-2 text-sm font-medium transition-all cursor-pointer ${
                  sel
                    ? "border-chart-1/60 bg-chart-1/15 text-foreground"
                    : "border-border/40 text-muted-foreground hover:border-border/60 hover:text-foreground"
                }`}
              >
                {b ? "True" : "False"}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── ReviewView ────────────────────────────────────────────────────────────────

function ReviewView({
  result,
  difficulty,
  onReset,
}: {
  result: { score: number; correct_count: number; total_count: number; answers: QuizAnswerReview[] }
  difficulty?: string
  onReset: () => void
}) {
  const pct = Math.round(result.score * 100)
  const good = pct >= 70

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Score header */}
      <div className="shrink-0 px-5 pt-4 pb-4 border-b border-border/30">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground/60 capitalize mb-0.5">
              {difficulty ?? ""} quiz · results
            </p>
            <p
              className={`text-3xl font-bold ${
                good ? "text-emerald-500" : pct >= 40 ? "text-amber-500" : "text-red-500"
              }`}
            >
              {pct}%
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {result.correct_count} of {result.total_count} correct
            </p>
          </div>
          <button
            type="button"
            onClick={onReset}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] text-sm font-medium text-white hover:opacity-90 transition-opacity cursor-pointer"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            New quiz
          </button>
        </div>
      </div>

      {/* Answer review */}
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3">
        {result.answers.map((a, i) => (
          <AnswerReviewCard key={a.id} a={a} index={i} />
        ))}
      </div>
    </div>
  )
}

function AnswerReviewCard({ a, index }: { a: QuizAnswerReview; index: number }) {
  return (
    <div
      className={`rounded-2xl border p-4 ${
        a.correct
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-red-500/30 bg-red-500/5"
      }`}
    >
      <div className="mb-2 flex items-start gap-2">
        {a.correct ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        ) : (
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
        )}
        <p className="text-sm font-medium text-foreground leading-relaxed">
          <span className="text-muted-foreground/50 mr-1">{index + 1}.</span>
          {a.question}
        </p>
      </div>
      <div className="space-y-1 pl-6 text-sm">
        {a.type === "mcq" ? (
          a.options.map((opt, idx) => {
            const isCorrect = idx === a.correct_answer
            const isUser = idx === a.user_answer
            return (
              <div
                key={idx}
                className={`rounded-lg px-2 py-1 ${
                  isCorrect
                    ? "bg-emerald-500/15 text-emerald-300"
                    : isUser
                    ? "bg-red-500/15 text-red-300"
                    : "text-muted-foreground"
                }`}
              >
                {String.fromCharCode(65 + idx)}. {opt}
                {isCorrect && " ✓"}
                {isUser && !isCorrect && " ← your answer"}
              </div>
            )
          })
        ) : (
          <p className="text-muted-foreground">
            Your answer:{" "}
            <b className="text-foreground">
              {a.user_answer === null ? "—" : a.user_answer ? "True" : "False"}
            </b>
            {" · "}Correct:{" "}
            <b className="text-emerald-400">
              {a.correct_answer ? "True" : "False"}
            </b>
          </p>
        )}
        {a.explanation && (
          <p className="mt-1.5 text-xs text-muted-foreground/70">
            <span className="text-muted-foreground/40">Why: </span>
            {a.explanation}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main Panel ────────────────────────────────────────────────────────────────

export default function QuizPanel({ fileId }: { fileId: number }) {
  const [state, setState] = useState<State>("idle")
  const [quizId, setQuizId] = useState<number | null>(null)
  const [quiz, setQuiz] = useState<QuizDetail | null>(null)
  const [count, setCount] = useState<Count>(10)
  const [diff, setDiff] = useState<Diff>("auto")
  const [answers, setAnswers] = useState<Record<string, Answer>>({})
  const [historyItems, setHistoryItems] = useState<QuizHistoryItem[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollStartRef = useRef<number>(0)

  const loadHistory = useCallback(() => {
    quizApi.history(fileId).then((h) => { setHistoryItems(h.items) }).catch(() => {})
  }, [fileId])

  useEffect(() => {
    quizApi.history(fileId)
      .then((h) => {
        setHistoryItems(h.items)
        if (h.has_open_quiz && h.open_quiz_id != null) {
          resumeQuiz(h.open_quiz_id)
        }
      })
      .catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId])

  async function resumeQuiz(id: number) {
    setQuizId(id)
    try {
      const detail = await quizApi.get(id)
      setQuiz(detail)
      if (detail.status === "ready") { setAnswers({}); setState("ready") }
      else if (detail.status === "submitted") setState("submitted")
      else if (detail.status === "failed") { setErrorMsg(detail.error_msg ?? "Generation failed."); setState("failed") }
      else { pollStartRef.current = Date.now(); setState("generating") }
    } catch { setState("idle") }
  }

  useEffect(() => {
    if (state !== "generating" || quizId == null) return
    const interval = setInterval(async () => {
      if (Date.now() - pollStartRef.current > 120_000) {
        clearInterval(interval); setErrorMsg("Timed out. Please try again."); setState("failed"); return
      }
      try {
        const detail = await quizApi.get(quizId)
        setQuiz(detail)
        if (detail.status === "ready") {
          clearInterval(interval); setAnswers({}); setState("ready"); loadHistory()
        } else if (detail.status === "failed") {
          clearInterval(interval); setErrorMsg(detail.error_msg ?? "Generation failed."); setState("failed")
        }
      } catch {}
    }, 2000)
    return () => clearInterval(interval)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, quizId])

  async function handleGenerate() {
    setErrorMsg(null)
    try {
      const body: Parameters<typeof quizApi.generate>[1] = {
        num_questions: count,
        ...(diff !== "auto" && { difficulty: diff }),
      }
      const res = await quizApi.generate(fileId, body)
      setQuizId(res.quiz_id); setQuiz(null); pollStartRef.current = Date.now(); setState("generating")
    } catch (e) {
      toast.error(apiErrorDetail(e, "Could not start quiz"))
    }
  }

  function setAnswer(id: string, a: Answer) {
    setAnswers((s) => ({ ...s, [id]: a }))
  }

  async function handleSubmit() {
    if (!quiz?.questions || !quizId) return
    setState("submitting")
    const payload: SubmitAnswer[] = quiz.questions.map((q) =>
      q.type === "mcq"
        ? { question_id: q.id, answer_index: answers[q.id] as number }
        : { question_id: q.id, answer_bool: answers[q.id] as boolean },
    )
    try {
      const result = await quizApi.submit(quizId, payload)
      setQuiz((prev) => prev ? { ...prev, status: "submitted", review: result } : prev)
      setState("submitted"); loadHistory()
    } catch (e) {
      toast.error(apiErrorDetail(e, "Could not submit quiz"))
      setState("ready")
    }
  }

  function handleReset() {
    setQuizId(null); setQuiz(null); setAnswers({}); setErrorMsg(null); setState("idle"); loadHistory()
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">

      {/* ── IDLE ── */}
      {state === "idle" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-7 px-8 py-6">
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl border border-border/40 bg-card/40 backdrop-blur-sm mb-1">
              <BookOpen className="w-7 h-7 text-chart-1" />
            </div>
            <p className="text-base font-semibold text-foreground">Quiz yourself</p>
            <p className="text-xs text-muted-foreground/70 max-w-xs leading-relaxed">
              Generate a quiz from this document. Difficulty controls how deeply it draws on the material — Auto adapts to your past scores.
            </p>
          </div>

          <div className="w-full max-w-xs space-y-4">
            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground/50 font-medium">Questions</p>
              <div className="flex gap-2">
                {COUNTS.map((c) => (
                  <Pill key={c} active={count === c} onClick={() => setCount(c)}>{c}</Pill>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground/50 font-medium">Difficulty</p>
              <div className="flex flex-wrap gap-2">
                {DIFFS.map((d) => (
                  <Pill key={d} active={diff === d} onClick={() => setDiff(d)}>
                    {d === "auto" ? "Auto" : d[0].toUpperCase() + d.slice(1)}
                  </Pill>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={handleGenerate}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] text-sm font-medium text-white hover:opacity-90 transition-opacity cursor-pointer"
            >
              <BookOpen className="h-4 w-4" />
              Generate quiz
            </button>

            {errorMsg && <p className="text-xs text-destructive text-center">{errorMsg}</p>}
          </div>

          {/* History */}
          {historyItems.length > 0 && (
            <div className="w-full max-w-xs">
              <button
                type="button"
                onClick={() => setShowHistory((v) => !v)}
                className="flex items-center gap-1 text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-pointer"
              >
                {showHistory ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                Past quizzes ({historyItems.length})
              </button>
              {showHistory && (
                <div className="mt-2 max-h-44 overflow-y-auto space-y-1.5">
                  {historyItems.map((h) => (
                    <button
                      key={h.quiz_id}
                      type="button"
                      onClick={() => h.status === "submitted" && resumeQuiz(h.quiz_id)}
                      disabled={h.status !== "submitted"}
                      className="flex w-full items-center justify-between rounded-xl border border-border/40 bg-card/30 px-3 py-2 text-left text-xs enabled:hover:border-border/60 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed transition-colors"
                    >
                      <span className="text-muted-foreground capitalize">{h.difficulty} · {h.num_questions} Qs</span>
                      <span className="text-muted-foreground/50">
                        {h.status === "submitted" && h.score != null
                          ? `${Math.round(h.score * 100)}%`
                          : h.status}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── GENERATING ── */}
      {(state === "generating") && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div className="flex gap-1.5 items-center">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="block w-2 h-2 rounded-full bg-chart-1/70"
                animate={{ y: [0, -6, 0] }}
                transition={{ duration: 0.9, delay: i * 0.18, repeat: Infinity, ease: "easeInOut" }}
              />
            ))}
          </div>
          <p className="text-sm text-muted-foreground">Generating your quiz…</p>
          <p className="text-xs text-muted-foreground/40">Difficulty drives how deeply it draws on the material.</p>
        </div>
      )}

      {/* ── READY / SUBMITTING ── */}
      {(state === "ready" || state === "submitting") && quiz && (
        <InProgress
          quiz={quiz}
          answers={answers}
          setAnswer={setAnswer}
          submitting={state === "submitting"}
          onSubmit={handleSubmit}
        />
      )}

      {/* ── SUBMITTED ── */}
      {state === "submitted" && quiz?.review && (
        <ReviewView
          result={quiz.review}
          difficulty={quiz.difficulty}
          onReset={handleReset}
        />
      )}

      {/* ── FAILED ── */}
      {state === "failed" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6">
          <XCircle className="h-7 w-7 text-destructive" />
          <p className="text-sm text-destructive text-center max-w-xs">{errorMsg || "Quiz generation failed."}</p>
          <button
            type="button"
            onClick={handleReset}
            className="flex items-center gap-1.5 px-5 py-2 rounded-xl border border-border/40 bg-card/30 text-sm text-foreground hover:bg-card/50 cursor-pointer transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Try again
          </button>
        </div>
      )}

    </div>
  )
}
