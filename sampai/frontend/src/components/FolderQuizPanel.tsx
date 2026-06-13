import { useEffect, useRef, useState, type ReactNode } from 'react'
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
  type FolderQuizDetail,
  type FolderQuizQuestionView,
  type TopicScore,
} from '@/api/sampai'

type Diff = 'auto' | 'easy' | 'medium' | 'hard'

const DIFFS: Diff[] = ['auto', 'easy', 'medium', 'hard']
const DIFF_LABEL: Record<Diff, string> = { auto: 'Auto', easy: 'Easy', medium: 'Medium', hard: 'Hard' }

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
        active
          ? 'border-chart-1/60 bg-chart-1/15 text-foreground shadow-[0_0_18px_rgba(99,102,241,0.16)]'
          : 'border-border/60 bg-background/40 text-muted-foreground hover:border-chart-1/40 hover:text-foreground'
      }`}
    >
      {children}
    </button>
  )
}

function FileSourceBadge({ name }: { name: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded-md border border-border/50 bg-background/45 px-1.5 py-0.5 text-[10px] text-muted-foreground">
      <FileText className="h-2.5 w-2.5 shrink-0" />
      <span className="truncate">{name}</span>
    </span>
  )
}

function ReasoningChip({ type }: { type: string }) {
  const tone: Record<string, string> = {
    factual: 'text-sky-500 bg-sky-500/10 border-sky-500/20',
    comparative: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
    causal: 'text-red-500 bg-red-500/10 border-red-500/20',
    inferential: 'text-purple-500 bg-purple-500/10 border-purple-500/20',
    analytical: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  }

  return (
    <span className={`rounded-md border px-1.5 py-0.5 text-[10px] capitalize ${tone[type] ?? 'border-border/50 bg-muted/40 text-muted-foreground'}`}>
      {type || 'question'}
    </span>
  )
}

function scoreTone(frac: number) {
  return frac >= 0.8
    ? 'text-emerald-500 border-emerald-500/35 bg-emerald-500/10'
    : frac >= 0.4
    ? 'text-amber-500 border-amber-500/35 bg-amber-500/10'
    : 'text-red-500 border-red-500/35 bg-red-500/10'
}

function ScorePill({ score }: { score: number }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${scoreTone(score / 5)}`}>
      <Sparkles className="h-3 w-3" />
      {score}/5
    </span>
  )
}

function GradeBlock({ q }: { q: FolderQuizQuestionView }) {
  return (
    <>
      <div className="mt-3 rounded-lg border border-border/50 bg-background/45 p-3">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Your answer</p>
        <p className="whitespace-pre-wrap text-sm text-foreground/80">
          {q.user_answer?.trim() ? q.user_answer : <em className="text-muted-foreground">No answer given</em>}
        </p>
      </div>
      <div className="mt-2 rounded-lg border border-chart-1/25 bg-chart-1/10 p-3">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-chart-1">Reference answer</p>
        <p className="whitespace-pre-wrap text-sm text-foreground/80">{q.reference_answer}</p>
      </div>
      <div className="mt-2 rounded-lg border border-chart-2/25 bg-chart-2/10 p-3">
        <div className="mb-1.5 flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-medium uppercase tracking-wide text-chart-2">SAMpai critique</span>
          {q.score != null && <ScorePill score={q.score} />}
        </div>
        {q.verdict && <p className="mb-2 text-sm text-foreground/80">{q.verdict}</p>}
        {q.missing.length > 0 && (
          <div className="mb-1.5">
            <p className="mb-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-amber-500">
              <MinusCircle className="h-3 w-3" />
              Missing
            </p>
            <ul className="ml-4 list-disc space-y-0.5 text-xs text-muted-foreground">
              {q.missing.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        )}
        {q.incorrect.length > 0 && (
          <div>
            <p className="mb-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-red-500">
              <AlertTriangle className="h-3 w-3" />
              Incorrect
            </p>
            <ul className="ml-4 list-disc space-y-0.5 text-xs text-muted-foreground">
              {q.incorrect.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        )}
        {q.missing.length === 0 && q.incorrect.length === 0 && (q.score ?? 0) >= 4 && (
          <p className="text-xs text-emerald-500">Nothing missing or incorrect. Nicely done.</p>
        )}
      </div>
    </>
  )
}

function TopicBreakdown({ topics }: { topics: TopicScore[] }) {
  if (!topics.length) return null

  return (
    <div className="rounded-xl border border-border/50 bg-background/35 p-4">
      <p className="mb-3 text-sm font-medium text-foreground">Performance by file</p>
      <div className="space-y-2.5">
        {topics.map((topic) => {
          const pct = Math.round(topic.mean_score * 100)
          return (
            <div key={`${topic.file_id}-${topic.filename}`}>
              <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                <span className="flex min-w-0 items-center gap-1.5 text-foreground/80">
                  <FileText className="h-3 w-3 shrink-0 text-chart-1" />
                  <span className="truncate">{topic.filename}</span>
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {pct}% · {topic.correct_count}/{topic.question_count} mastered
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
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

function isGenerating(quiz: FolderQuizDetail | undefined) {
  return quiz?.status === 'pending' || quiz?.status === 'generating'
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
  const [selected, setSelected] = useState<Set<number>>(() => new Set(completedFiles.map((file) => file.id)))
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [showHistory, setShowHistory] = useState(false)
  const topRef = useRef<HTMLDivElement>(null)
  const seenRef = useRef<Set<number>>(new Set())

  const availableIds = completedFiles.map((file) => file.id).join(',')
  useEffect(() => {
    const ids = completedFiles.map((file) => file.id)
    setSelected((prev) => {
      const next = new Set<number>()
      for (const id of ids) {
        if (prev.has(id) || !seenRef.current.has(id)) next.add(id)
      }
      return next
    })
    seenRef.current = new Set(ids)
  }, [availableIds]) // eslint-disable-line react-hooks/exhaustive-deps

  const allSelected = completedFiles.length > 0 && completedFiles.every((file) => selected.has(file.id))
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(completedFiles.map((file) => file.id)))
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
    refetchInterval: (query) => isGenerating(query.state.data as FolderQuizDetail | undefined) ? 2000 : false,
  })

  const generate = useMutation({
    mutationFn: () =>
      folderQuizApi.generate(folderId, {
        difficulty: diff === 'auto' ? undefined : diff,
        file_ids: [...selected],
      }),
    onSuccess: (res) => {
      setQuizId(res.quiz_id)
      qc.invalidateQueries({ queryKey: ['fq-history', folderId] })
    },
    onError: (error) => toast.error(apiErrorDetail(error, 'Could not start quiz')),
  })

  const submitQ = useMutation({
    mutationFn: ({ questionId, answer }: { questionId: string; answer: string }) =>
      folderQuizApi.submitQuestion(quizId as number, questionId, answer),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['fq', quizId] })
      qc.invalidateQueries({ queryKey: ['fq-history', folderId] })
      if (res.finished) setTimeout(() => topRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    },
    onError: (error) => toast.error(apiErrorDetail(error, 'Grading is unavailable right now. Please retry.')),
  })

  function reset() {
    setQuizId(null)
    setDrafts({})
    qc.invalidateQueries({ queryKey: ['fq-history', folderId] })
  }

  const status = quiz?.status

  if (!quizId || status === 'failed') {
    return (
      <div className="space-y-4">
        {status === 'failed' && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-500">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-medium">Generation failed</p>
              {quiz?.error_msg && <p className="mt-0.5 text-xs text-red-500/80">{quiz.error_msg}</p>}
              <button type="button" onClick={reset} className="mt-1 text-xs underline">Back</button>
            </div>
          </div>
        )}

        <div className="rounded-xl border border-border/50 bg-background/35 p-5">
          <div className="mb-4 flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-chart-1" />
            <h3 className="font-medium text-foreground">Cross-file quiz</h3>
            <span className="ml-auto text-xs text-muted-foreground">
              {completedCount} completed file{completedCount !== 1 ? 's' : ''}
            </span>
          </div>

          {completedCount < 1 ? (
            <p className="text-sm text-muted-foreground">No files are ready yet. Upload and process at least one file.</p>
          ) : (
            <>
              <div className="mb-4">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">Files to include</p>
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="text-[11px] font-medium text-chart-1 hover:opacity-80"
                  >
                    {allSelected ? 'Deselect all' : 'Select all'}
                  </button>
                </div>
                <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-border/50 bg-card/45 p-1.5">
                  {completedFiles.map((file) => {
                    const on = selected.has(file.id)
                    return (
                      <button
                        key={file.id}
                        type="button"
                        onClick={() => toggleFile(file.id)}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition hover:bg-muted/50"
                      >
                        <span
                          className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                            on ? 'border-chart-1 bg-chart-1 text-white' : 'border-border bg-background/40'
                          }`}
                        >
                          {on && <Check className="h-3 w-3" />}
                        </span>
                        <FileText className="h-3.5 w-3.5 shrink-0 text-chart-1" />
                        <span className={`flex-1 truncate ${on ? 'text-foreground' : 'text-muted-foreground'}`}>{file.filename}</span>
                      </button>
                    )
                  })}
                </div>
                <p className="mt-1.5 text-[10px] text-muted-foreground">
                  {selected.size} of {completedCount} file{completedCount !== 1 ? 's' : ''} selected · the quiz draws only from these
                </p>
              </div>

              <div className="mb-5">
                <p className="mb-2 text-xs text-muted-foreground">Difficulty</p>
                <div className="flex flex-wrap gap-2">
                  {DIFFS.map((item) => (
                    <Pill key={item} active={diff === item} onClick={() => setDiff(item)}>
                      {DIFF_LABEL[item]}
                    </Pill>
                  ))}
                </div>
                <p className="mt-1.5 text-[10px] text-muted-foreground">
                  Auto adapts to your last quiz score. Higher difficulty asks for deeper cross-file reasoning.
                </p>
              </div>

              <p className="mb-3 rounded-lg border border-border/40 bg-card/40 px-3 py-2 text-[11px] text-muted-foreground">
                SAMpai picks the most worthwhile questions from your selection, up to 30. Thinner selections produce shorter quizzes.
              </p>

              <button
                type="button"
                disabled={generate.isPending || selected.size < 1}
                onClick={() => generate.mutate()}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
              >
                {generate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                {selected.size < 1
                  ? 'Select at least one file'
                  : `Generate quiz (${selected.size} file${selected.size !== 1 ? 's' : ''})`}
              </button>
            </>
          )}
        </div>

        {(history?.items ?? []).length > 0 && (
          <div className="rounded-xl border border-border/50 bg-background/35">
            <button
              type="button"
              onClick={() => setShowHistory((open) => !open)}
              className="flex w-full items-center gap-2 px-4 py-3 text-sm text-muted-foreground transition hover:text-foreground"
            >
              {showHistory ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              Past quizzes ({history!.items.length})
            </button>
            {showHistory && (
              <div className="divide-y divide-border/40 border-t border-border/40">
                {history!.items.map((item) => {
                  const done = item.status === 'submitted'
                  const inProgress = item.status === 'ready'
                  return (
                    <button
                      key={item.quiz_id}
                      type="button"
                      onClick={() => setQuizId(item.quiz_id)}
                      className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-xs transition hover:bg-muted/40"
                    >
                      <span className="capitalize text-foreground">{item.difficulty}</span>
                      <span className="text-muted-foreground">·</span>
                      <span className="text-muted-foreground">{item.total_count > 0 ? `${item.total_count} Qs` : '...'}</span>
                      <span className="text-muted-foreground">·</span>
                      <span className="text-muted-foreground">{item.n_files} files</span>
                      <span className="ml-auto flex items-center gap-2">
                        {done && item.score != null ? (
                          <span className={`rounded-full border px-2 py-0.5 font-semibold ${scoreTone(item.score)}`}>
                            {Math.round(item.score * 100)}%
                          </span>
                        ) : inProgress ? (
                          <span className="text-amber-500">In progress {item.graded_count}/{item.total_count}</span>
                        ) : (
                          <span className="capitalize text-muted-foreground">{item.status}</span>
                        )}
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
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

  if (status === 'pending' || status === 'generating') {
    return (
      <div className="rounded-xl border border-border/50 bg-background/35 p-8 text-center">
        <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-chart-1" />
        <p className="font-medium text-foreground">Generating cross-file quiz...</p>
        <p className="mt-1.5 text-xs text-muted-foreground">
          {quiz?.difficulty === 'hard'
            ? 'Hard mode asks for deeper cross-document synthesis, so it can take a bit longer.'
            : 'Selecting the most worthwhile concepts from your files.'}
        </p>
        <p className="mt-1 text-xs capitalize text-muted-foreground">{quiz?.difficulty} difficulty</p>
      </div>
    )
  }

  if (!quiz) return null

  const questions = quiz.questions
  const total = quiz.total_count || questions.length
  const graded = quiz.graded_count
  const pct = quiz.score != null ? Math.round(quiz.score * 100) : null
  const complete = status === 'submitted'

  return (
    <div ref={topRef} className="space-y-4">
      {complete ? (
        <div className="rounded-xl border border-border/50 bg-background/35 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm text-muted-foreground">Quiz score</p>
              <p className="text-3xl font-bold text-foreground">{pct != null ? `${pct}%` : '-'}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {quiz.correct_count ?? 0}/{total} mastered · {quiz.difficulty} · this score sets your next Auto difficulty
              </p>
            </div>
            <button
              type="button"
              onClick={reset}
              className="flex items-center gap-1 rounded-lg border border-border/60 bg-card/45 px-3 py-2 text-xs text-muted-foreground transition hover:text-foreground"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              New quiz
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium text-foreground">Answer each question and submit it for feedback</p>
          <span className="text-xs text-muted-foreground">
            {graded}/{total} graded{pct != null ? ` · ${pct}% so far` : ''}
          </span>
        </div>
      )}

      {(quiz.warnings ?? []).length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div className="space-y-0.5">
            {quiz.warnings.map((warning, i) => <p key={i}>{warning}</p>)}
          </div>
        </div>
      )}

      {complete && <TopicBreakdown topics={quiz.topic_scores} />}

      <div className="space-y-4">
        {questions.map((q, i) => {
          const busy = submitQ.isPending && submitQ.variables?.questionId === q.id
          return (
            <div key={q.id} className="rounded-xl border border-border/50 bg-background/35 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-muted-foreground">Q{i + 1}</span>
                <ReasoningChip type={q.reasoning_type} />
                {q.source_file_names.map((name) => <FileSourceBadge key={name} name={name} />)}
                {q.submitted && q.score != null && <span className="ml-auto"><ScorePill score={q.score} /></span>}
              </div>
              <p className="mb-3 text-sm text-foreground">{q.question}</p>

              {q.submitted ? (
                <GradeBlock q={q} />
              ) : (
                <>
                  <textarea
                    rows={3}
                    placeholder="Write your answer..."
                    value={drafts[q.id] ?? ''}
                    onChange={(event) => setDrafts((prev) => ({ ...prev, [q.id]: event.target.value }))}
                    disabled={busy}
                    className="w-full resize-none rounded-lg border border-border/60 bg-card/50 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-chart-1 focus:outline-none disabled:opacity-60"
                  />
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => submitQ.mutate({ questionId: q.id, answer: drafts[q.id] ?? '' })}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-chart-1 px-4 py-1.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
                    >
                      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                      {busy ? 'Grading...' : 'Submit'}
                    </button>
                    <span className="text-[11px] text-muted-foreground">Reveals the reference answer and your score</span>
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>

      {!complete && (
        <p className="text-center text-xs text-muted-foreground">
          Submit every question to finish. Blank answers score 0.
        </p>
      )}
    </div>
  )
}
