/**
 * FolderQuizPanel — cross-file (folder-level) quiz.
 *
 * Take flow: generate → poll → each question has its own Submit button. Submitting
 * a question grades it 0–5 against its reference and reveals the reference answer +
 * SAMpai's critique (what's missing / wrong). When every question is submitted the
 * quiz completes; the aggregate score (and per-file topic breakdown) drive the next
 * quiz's auto-difficulty. Past quizzes are clickable to revisit.
 */
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  MinusCircle,
  RotateCcw,
  Send,
  Sparkles,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  apiErrorDetail,
  folderQuizApi,
  type FolderQuizQuestionView,
  type TopicScore,
} from '@/api/sampai'

type Diff = 'auto' | 'easy' | 'medium' | 'hard'

const DIFFS: Diff[] = ['auto', 'easy', 'medium', 'hard']
const DIFF_LABEL: Record<Diff, string> = { auto: 'Auto', easy: 'Easy', medium: 'Medium', hard: 'Hard' }

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
        active
          ? 'border-violet-500 bg-violet-500/20 text-violet-300'
          : 'border-neutral-700 text-neutral-400 hover:border-neutral-500 hover:text-neutral-200'
      }`}
    >
      {children}
    </button>
  )
}

function FileSourceBadge({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
      <FileText className="h-2.5 w-2.5" /> {name}
    </span>
  )
}

function ReasoningChip({ type }: { type: string }) {
  const col: Record<string, string> = {
    factual: 'text-sky-400 bg-sky-500/10',
    comparative: 'text-amber-400 bg-amber-500/10',
    causal: 'text-red-400 bg-red-500/10',
    inferential: 'text-purple-400 bg-purple-500/10',
    analytical: 'text-emerald-400 bg-emerald-500/10',
  }
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] capitalize ${col[type] ?? 'text-neutral-400 bg-neutral-800'}`}>
      {type || 'question'}
    </span>
  )
}

function scoreTone(frac: number) {
  return frac >= 0.8
    ? 'text-emerald-300 border-emerald-600/40 bg-emerald-500/15'
    : frac >= 0.4
    ? 'text-amber-300 border-amber-600/40 bg-amber-500/15'
    : 'text-red-300 border-red-600/40 bg-red-500/15'
}

function ScorePill({ score }: { score: number }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${scoreTone(score / 5)}`}>
      <Sparkles className="h-3 w-3" /> {score}/5
    </span>
  )
}

/** Reference answer + critique shown once a question is submitted. */
function GradeBlock({ q }: { q: FolderQuizQuestionView }) {
  return (
    <>
      <div className="mt-3 rounded-lg border border-neutral-700/60 bg-neutral-800/60 p-3">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-neutral-500">Your answer</p>
        <p className="text-sm text-neutral-300 whitespace-pre-wrap">
          {q.user_answer?.trim() ? q.user_answer : <em className="text-neutral-600">No answer given</em>}
        </p>
      </div>
      <div className="mt-2 rounded-lg border border-violet-900/40 bg-violet-950/30 p-3">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-violet-400">Reference answer</p>
        <p className="text-sm text-neutral-300 whitespace-pre-wrap">{q.reference_answer}</p>
      </div>
      <div className="mt-2 rounded-lg border border-sky-900/50 bg-sky-950/30 p-3">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-[10px] font-medium uppercase tracking-wide text-sky-400">SAMpai's critique</span>
          {q.score != null && <ScorePill score={q.score} />}
        </div>
        {q.verdict && <p className="mb-2 text-sm text-neutral-300">{q.verdict}</p>}
        {q.missing.length > 0 && (
          <div className="mb-1.5">
            <p className="mb-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-amber-400">
              <MinusCircle className="h-3 w-3" /> Missing
            </p>
            <ul className="ml-4 list-disc space-y-0.5 text-xs text-neutral-400">
              {q.missing.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        )}
        {q.incorrect.length > 0 && (
          <div>
            <p className="mb-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-red-400">
              <AlertTriangle className="h-3 w-3" /> Incorrect
            </p>
            <ul className="ml-4 list-disc space-y-0.5 text-xs text-neutral-400">
              {q.incorrect.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        )}
        {q.missing.length === 0 && q.incorrect.length === 0 && (q.score ?? 0) >= 4 && (
          <p className="text-xs text-emerald-400">Nothing missing or incorrect — well done.</p>
        )}
      </div>
    </>
  )
}

function TopicBreakdown({ topics }: { topics: TopicScore[] }) {
  if (!topics.length) return null
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
      <p className="mb-3 text-sm font-medium text-neutral-300">Performance by file</p>
      <div className="space-y-2.5">
        {topics.map((t) => {
          const pct = Math.round(t.mean_score * 100)
          return (
            <div key={`${t.file_id}-${t.filename}`}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-neutral-300">
                  <FileText className="h-3 w-3 text-violet-400" /> {t.filename}
                </span>
                <span className="text-neutral-400">
                  {pct}% · {t.correct_count}/{t.question_count} mastered
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-800">
                <div
                  className={`h-full rounded-full ${pct >= 80 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500'}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function FolderQuizPanel({
  folderId,
  completedFiles,
}: {
  folderId: number
  completedFiles: { id: number; filename: string }[]
}) {
  const qc = useQueryClient()
  const completedCount = completedFiles.length
  const [quizId, setQuizId] = useState<number | null>(null)
  const [diff, setDiff] = useState<Diff>('auto')
  const [selected, setSelected] = useState<Set<number>>(() => new Set(completedFiles.map((f) => f.id)))
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [showHistory, setShowHistory] = useState(false)
  const topRef = useRef<HTMLDivElement>(null)
  const seenRef = useRef<Set<number>>(new Set())

  // Keep the selection in sync with the live completed-files list: newly-completed
  // files are selected by default (select-all spirit), removed files are dropped,
  // and the user's explicit deselections are preserved across status polls.
  const availIds = completedFiles.map((f) => f.id).join(',')
  useEffect(() => {
    const ids = completedFiles.map((f) => f.id)
    setSelected((prev) => {
      const next = new Set<number>()
      for (const id of ids) {
        if (prev.has(id) || !seenRef.current.has(id)) next.add(id)
      }
      return next
    })
    seenRef.current = new Set(ids)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availIds])

  const allSelected = completedFiles.length > 0 && completedFiles.every((f) => selected.has(f.id))
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(completedFiles.map((f) => f.id)))
  }
  function toggleFile(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const { data: history } = useQuery({
    queryKey: ['fq-history', folderId],
    queryFn: () => folderQuizApi.history(folderId),
  })

  // Resume an open (in-progress) quiz on mount.
  useEffect(() => {
    if (quizId == null && history?.has_open_quiz && history.open_quiz_id != null) {
      setQuizId(history.open_quiz_id)
    }
  }, [history, quizId])

  useEffect(() => {
    setDrafts({})
  }, [quizId])

  const { data: quiz } = useQuery({
    queryKey: ['fq', quizId],
    queryFn: () => folderQuizApi.get(quizId as number),
    enabled: quizId != null,
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === 'pending' || s === 'generating' ? 2000 : false
    },
  })

  const generate = useMutation({
    mutationFn: () =>
      folderQuizApi.generate(folderId, {
        difficulty: diff === 'auto' ? undefined : diff,
        file_ids: [...selected],
      }),
    onSuccess: (r) => {
      setQuizId(r.quiz_id)
      qc.invalidateQueries({ queryKey: ['fq-history', folderId] })
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not start quiz')),
  })

  const submitQ = useMutation({
    mutationFn: (questionId: string) =>
      folderQuizApi.submitQuestion(quizId as number, questionId, drafts[questionId] ?? ''),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['fq', quizId] })
      qc.invalidateQueries({ queryKey: ['fq-history', folderId] })
      if (r.finished) setTimeout(() => topRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Grading is unavailable right now — please retry')),
  })

  function reset() {
    setQuizId(null)
    setDrafts({})
    qc.invalidateQueries({ queryKey: ['fq-history', folderId] })
  }

  const status = quiz?.status

  // ── Idle (no active quiz / failed) ─────────────────────────────────────────
  if (!quizId || status === 'failed') {
    return (
      <div className="space-y-4">
        {status === 'failed' && (
          <div className="flex items-start gap-2 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-medium">Generation failed</p>
              {quiz?.error_msg && <p className="mt-0.5 text-xs text-red-400">{quiz.error_msg}</p>}
              <button onClick={reset} className="mt-1 text-xs underline">Back</button>
            </div>
          </div>
        )}

        <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
          <div className="mb-4 flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-violet-400" />
            <h3 className="font-medium">Cross-file quiz</h3>
            <span className="ml-auto text-xs text-neutral-500">
              {completedCount} completed file{completedCount !== 1 ? 's' : ''}
            </span>
          </div>

          {completedCount < 1 ? (
            <p className="text-sm text-neutral-500">No files are ready yet. Upload and process at least one file.</p>
          ) : (
            <>
              {/* File selection */}
              <div className="mb-4">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs text-neutral-500">Files to include</p>
                  <button
                    onClick={toggleAll}
                    className="text-[11px] font-medium text-violet-400 hover:text-violet-300"
                  >
                    {allSelected ? 'Deselect all' : 'Select all'}
                  </button>
                </div>
                <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-900/40 p-1.5">
                  {completedFiles.map((f) => {
                    const on = selected.has(f.id)
                    return (
                      <button
                        key={f.id}
                        onClick={() => toggleFile(f.id)}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-neutral-800/60"
                      >
                        <span
                          className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                            on ? 'border-violet-500 bg-violet-500 text-white' : 'border-neutral-600'
                          }`}
                        >
                          {on && <Check className="h-3 w-3" />}
                        </span>
                        <FileText className="h-3.5 w-3.5 shrink-0 text-violet-400" />
                        <span className={`flex-1 truncate ${on ? 'text-neutral-200' : 'text-neutral-500'}`}>{f.filename}</span>
                      </button>
                    )
                  })}
                </div>
                <p className="mt-1.5 text-[10px] text-neutral-600">
                  {selected.size} of {completedCount} file{completedCount !== 1 ? 's' : ''} selected · the quiz draws only from these
                </p>
              </div>

              <div className="mb-5">
                <p className="mb-2 text-xs text-neutral-500">Difficulty</p>
                <div className="flex flex-wrap gap-2">
                  {DIFFS.map((d) => <Pill key={d} active={diff === d} onClick={() => setDiff(d)}>{DIFF_LABEL[d]}</Pill>)}
                </div>
                <p className="mt-1.5 text-[10px] text-neutral-600">
                  Auto adapts to your last quiz's score · deeper difficulty = more cross-file BFS hops
                </p>
              </div>
              <p className="mb-3 rounded-lg bg-neutral-800/40 px-3 py-2 text-[11px] text-neutral-500">
                SAMpai picks the most worthwhile questions from your selection (up to 30) — thinner
                selections produce shorter quizzes.
              </p>
              <button
                disabled={generate.isPending || selected.size < 1}
                onClick={() => generate.mutate()}
                className="btn-primary w-full disabled:opacity-50"
              >
                {generate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                {selected.size < 1
                  ? 'Select at least one file'
                  : `Generate quiz (${selected.size} file${selected.size !== 1 ? 's' : ''})`}
              </button>
            </>
          )}
        </div>

        {/* Clickable history */}
        {(history?.items ?? []).length > 0 && (
          <div className="rounded-xl border border-neutral-800 bg-neutral-900/40">
            <button
              onClick={() => setShowHistory((v) => !v)}
              className="flex w-full items-center gap-2 px-4 py-3 text-sm text-neutral-400 hover:text-neutral-200"
            >
              {showHistory ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              Past quizzes ({history!.items.length})
            </button>
            {showHistory && (
              <div className="divide-y divide-neutral-800 border-t border-neutral-800">
                {history!.items.map((item) => {
                  const done = item.status === 'submitted'
                  const inProgress = item.status === 'ready'
                  return (
                    <button
                      key={item.quiz_id}
                      onClick={() => setQuizId(item.quiz_id)}
                      className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-xs transition hover:bg-neutral-800/50"
                    >
                      <span className="capitalize text-neutral-300">{item.difficulty}</span>
                      <span className="text-neutral-600">·</span>
                      <span className="text-neutral-400">{item.total_count > 0 ? `${item.total_count} Qs` : '…'}</span>
                      <span className="text-neutral-600">·</span>
                      <span className="text-neutral-400">{item.n_files} files</span>
                      <span className="ml-auto flex items-center gap-2">
                        {done && item.score != null ? (
                          <span className={`rounded-full border px-2 py-0.5 font-semibold ${scoreTone(item.score)}`}>
                            {Math.round(item.score * 100)}%
                          </span>
                        ) : inProgress ? (
                          <span className="text-amber-400">In progress {item.graded_count}/{item.total_count}</span>
                        ) : (
                          <span className="capitalize text-neutral-500">{item.status}</span>
                        )}
                        <ChevronRight className="h-3.5 w-3.5 text-neutral-600" />
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // ── Generating ─────────────────────────────────────────────────────────────
  if (status === 'pending' || status === 'generating') {
    return (
      <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-8 text-center">
        <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-violet-400" />
        <p className="font-medium text-neutral-200">Generating cross-file quiz…</p>
        <p className="mt-1.5 text-xs text-neutral-500">
          {quiz?.difficulty === 'hard'
            ? 'Hard mode: deep cross-document BFS synthesis — takes a bit longer.'
            : 'Selecting the most worthwhile concepts from your files.'}
        </p>
        <p className="mt-1 text-xs text-neutral-600">{quiz?.difficulty} difficulty</p>
      </div>
    )
  }

  // ── In-progress (ready) or completed (submitted) ───────────────────────────
  if (!quiz) return null
  const questions = quiz.questions
  const total = quiz.total_count || questions.length
  const graded = quiz.graded_count
  const pct = quiz.score != null ? Math.round(quiz.score * 100) : null
  const complete = status === 'submitted'

  return (
    <div ref={topRef} className="space-y-4">
      {/* Header */}
      {complete ? (
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-neutral-400">Quiz score</p>
              <p className="text-3xl font-bold text-neutral-100">{pct != null ? `${pct}%` : '—'}</p>
              <p className="mt-0.5 text-xs text-neutral-500">
                {quiz.correct_count ?? 0}/{total} mastered · {quiz.difficulty} · this score sets your next Auto difficulty
              </p>
            </div>
            <button onClick={reset} className="flex items-center gap-1 rounded-lg border border-neutral-700 px-3 py-2 text-xs text-neutral-400 hover:text-neutral-200">
              <RotateCcw className="h-3.5 w-3.5" /> New quiz
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-neutral-300">
            Answer each question and submit it for feedback
          </p>
          <span className="text-xs text-neutral-500">
            {graded}/{total} graded{pct != null ? ` · ${pct}% so far` : ''}
          </span>
        </div>
      )}

      {/* Sparse-selection notice (e.g. "only 3 worthwhile questions found") */}
      {(quiz.warnings ?? []).length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-300/90">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div className="space-y-0.5">
            {quiz.warnings.map((w, i) => <p key={i}>{w}</p>)}
          </div>
        </div>
      )}

      {complete && <TopicBreakdown topics={quiz.topic_scores} />}

      {/* Question list */}
      <div className="space-y-4">
        {questions.map((q, i) => {
          const busy = submitQ.isPending && submitQ.variables === q.id
          return (
            <div key={q.id} className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-neutral-500">Q{i + 1}</span>
                <ReasoningChip type={q.reasoning_type} />
                {q.source_file_names.map((n) => <FileSourceBadge key={n} name={n} />)}
                {q.submitted && q.score != null && <span className="ml-auto"><ScorePill score={q.score} /></span>}
              </div>
              <p className="mb-3 text-sm text-neutral-200">{q.question}</p>

              {q.submitted ? (
                <GradeBlock q={q} />
              ) : (
                <>
                  <textarea
                    rows={3}
                    placeholder="Write your answer…"
                    value={drafts[q.id] ?? ''}
                    onChange={(e) => setDrafts((p) => ({ ...p, [q.id]: e.target.value }))}
                    disabled={busy}
                    className="w-full resize-none rounded-lg border border-neutral-700 bg-neutral-800/70 px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:border-violet-500 focus:outline-none disabled:opacity-60"
                  />
                  <div className="mt-2 flex items-center gap-3">
                    <button
                      onClick={() => submitQ.mutate(q.id)}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-violet-500 disabled:opacity-50"
                    >
                      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                      {busy ? 'Grading…' : 'Submit'}
                    </button>
                    <span className="text-[11px] text-neutral-600">Reveals the reference answer + your score</span>
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>

      {!complete && (
        <p className="text-center text-xs text-neutral-600">
          Submit every question to finish — blank answers score 0.
        </p>
      )}
    </div>
  )
}
