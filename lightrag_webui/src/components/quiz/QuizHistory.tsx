/**
 * QuizHistory — collapsible panel listing previously generated quizzes.
 *
 * Fetches GET /quiz/list on mount and whenever the user clicks Refresh.
 * Clicking a row calls onLoad(quiz_id) which triggers GET /quiz/{id} in the parent.
 */

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listQuizzes, QuizSummary } from '@/api/lightrag'
import { cn } from '@/lib/utils'
import {
  HistoryIcon,
  RefreshCwIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckCircleIcon,
} from 'lucide-react'

interface QuizHistoryProps {
  onLoad: (quizId: string) => void
  currentQuizId?: string
}

function PassRatePip({ rate }: { rate: number | undefined }) {
  if (rate === undefined) return null
  const pct = Math.round(rate * 100)
  const color = pct >= 80 ? 'text-emerald-500' : pct >= 50 ? 'text-amber-500' : 'text-red-500'
  return (
    <span className={cn('flex items-center gap-0.5 font-mono tabular-nums', color)}>
      <CheckCircleIcon className="size-2.5" />
      {pct}%
    </span>
  )
}

function difficultyColor(d: string) {
  return d === 'easy' ? 'text-emerald-600' : d === 'hard' ? 'text-red-500' : 'text-amber-500'
}

export default function QuizHistory({ onLoad, currentQuizId }: QuizHistoryProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(true)
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listQuizzes()
      setQuizzes(data)
    } catch (err: any) {
      setError(err?.message ?? 'Failed to load quiz history')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <div className="border-t border-border mt-2 pt-2 shrink-0">
      {/* Header row */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 px-1 py-0.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <HistoryIcon className="size-3" />
        <span className="flex-1 text-left">{t('quizPanel.history.title')}</span>
        {quizzes.length > 0 && (
          <span className="rounded-full bg-muted px-1.5 py-0 text-[10px]">{quizzes.length}</span>
        )}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); refresh() }}
          className="p-0.5 rounded hover:bg-muted"
          title={t('quizPanel.history.refresh')}
        >
          <RefreshCwIcon className={cn('size-3', loading && 'animate-spin')} />
        </button>
        {expanded ? <ChevronDownIcon className="size-3" /> : <ChevronRightIcon className="size-3" />}
      </button>

      {/* List */}
      {expanded && (
        <div className="mt-1 max-h-52 overflow-auto flex flex-col gap-0.5">
          {error && (
            <p className="text-[10px] text-red-500 px-1">{error}</p>
          )}
          {!loading && quizzes.length === 0 && !error && (
            <p className="text-[10px] text-muted-foreground px-1 py-2">
              {t('quizPanel.history.empty')}
            </p>
          )}
          {quizzes.map((q) => {
            const date = new Date(q.created_at).toLocaleString(undefined, {
              month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
            })
            const isActive = q.quiz_id === currentQuizId
            return (
              <button
                key={q.quiz_id}
                type="button"
                onClick={() => onLoad(q.quiz_id)}
                className={cn(
                  'flex flex-col gap-0.5 rounded px-2 py-1.5 text-left text-[10px] hover:bg-muted transition-colors w-full',
                  isActive && 'bg-emerald-50 dark:bg-emerald-950/30 ring-1 ring-emerald-300/50'
                )}
              >
                <div className="flex items-center gap-1.5 font-mono">
                  <span className="text-muted-foreground">{q.quiz_id.slice(0, 8)}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className={cn('font-medium', difficultyColor(q.difficulty))}>
                    {q.difficulty}
                  </span>
                  <span className="text-muted-foreground">·</span>
                  <span>{q.mode}</span>
                  <span className="ml-auto">
                    <PassRatePip rate={q.verifier_pass_rate} />
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <span>{q.question_count}q</span>
                  <span>·</span>
                  <span>{date}</span>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
