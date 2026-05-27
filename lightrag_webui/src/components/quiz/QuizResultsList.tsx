/**
 * QuizResultsList — displays generated questions with metadata badges.
 *
 * Each question card shows:
 *   - Question text
 *   - Reference answer (collapsed by default)
 *   - Metadata badges: arm, difficulty, claimed complexity, reasoning type
 *   - Verification badges (if available): answerable, complexity match, reasoning match
 *   - BFS path (mix arm only)
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { QuizQuestion, QuizGenerateResponse } from '@/api/lightrag'
import { cn } from '@/lib/utils'
import { ChevronDownIcon, ChevronUpIcon, CheckCircleIcon, XCircleIcon, AlertCircleIcon } from 'lucide-react'

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function Badge({ label, variant = 'default' }: { label: string; variant?: 'default' | 'success' | 'warn' | 'error' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium',
        variant === 'default' && 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
        variant === 'success' && 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300',
        variant === 'warn' && 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
        variant === 'error' && 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
      )}
    >
      {label}
    </span>
  )
}

function VerifyFlag({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? CheckCircleIcon : XCircleIcon
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-[10px]',
        ok ? 'text-emerald-600' : 'text-red-500'
      )}
    >
      <Icon className="size-3" />
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Single question card
// ---------------------------------------------------------------------------

function QuestionCard({ q, index }: { q: QuizQuestion; index: number }) {
  const [answerOpen, setAnswerOpen] = useState(false)
  const [metaOpen, setMetaOpen] = useState(false)

  const difficultyVariant: Record<string, 'success' | 'warn' | 'error'> = {
    easy: 'success',
    medium: 'warn',
    hard: 'error',
  }

  const armLabel: Record<string, string> = {
    graph: 'Mix/Graph',
    naive: 'Naive',
    other: 'Fallback',
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4 text-sm flex flex-col gap-3">
      {/* Question header */}
      <div className="flex items-start gap-2">
        <span className="shrink-0 mt-0.5 text-xs text-muted-foreground font-mono">Q{index + 1}.</span>
        <p className="flex-1 leading-relaxed font-medium">{q.generation.question || '(pending)'}</p>
      </div>

      {/* Badges row */}
      <div className="flex flex-wrap gap-1.5">
        <Badge label={armLabel[q.arm] ?? q.arm} />
        <Badge
          label={q.difficulty.charAt(0).toUpperCase() + q.difficulty.slice(1)}
          variant={difficultyVariant[q.difficulty]}
        />
        <Badge label={`Depth/k: ${q.claimed_retrieval_complexity}`} />
        <Badge label={q.claimed_reasoning_type} />
      </div>

      {/* Verification badges */}
      {q.verification && (
        <div className="flex flex-wrap gap-3 text-[10px] border-t pt-2">
          <VerifyFlag ok={q.verification.answerable_from_context} label="Answerable" />
          <VerifyFlag ok={q.verification.claimed_complexity_matches} label="Complexity ✓" />
          <VerifyFlag ok={q.verification.claimed_reasoning_matches} label="Reasoning ✓" />
          {q.verification.notes && (
            <span className="text-muted-foreground italic">{q.verification.notes}</span>
          )}
        </div>
      )}

      {/* Reference answer (toggle) */}
      <button
        type="button"
        onClick={() => setAnswerOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        {answerOpen ? <ChevronUpIcon className="size-3" /> : <ChevronDownIcon className="size-3" />}
        {answerOpen ? 'Hide answer' : 'Show reference answer'}
      </button>
      {answerOpen && (
        <p className="text-xs bg-muted rounded p-2 leading-relaxed">
          {q.generation.reference_answer || '(no answer generated yet)'}
        </p>
      )}

      {/* Retrieval metadata (toggle) */}
      <button
        type="button"
        onClick={() => setMetaOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        {metaOpen ? <ChevronUpIcon className="size-3" /> : <ChevronDownIcon className="size-3" />}
        {metaOpen ? 'Hide retrieval details' : 'Show retrieval details'}
      </button>
      {metaOpen && (
        <div className="text-[10px] bg-muted rounded p-2 leading-relaxed font-mono space-y-1">
          {q.retrieval.bfs_path.length > 0 && (
            <p><span className="text-muted-foreground">BFS path:</span> {q.retrieval.bfs_path.join(' → ')}</p>
          )}
          {q.retrieval.entities.length > 0 && (
            <p><span className="text-muted-foreground">Entities:</span> {q.retrieval.entities.slice(0, 5).join(', ')}{q.retrieval.entities.length > 5 ? ` +${q.retrieval.entities.length - 5}` : ''}</p>
          )}
          {q.retrieval.chunk_ids.length > 0 && (
            <p><span className="text-muted-foreground">Chunk IDs:</span> {q.retrieval.chunk_ids.slice(0, 3).join(', ')}{q.retrieval.chunk_ids.length > 3 ? ` +${q.retrieval.chunk_ids.length - 3}` : ''}</p>
          )}
          <p><span className="text-muted-foreground">Seed:</span> {q.retrieval.seed_query} <span className="text-muted-foreground">({q.retrieval.seed_strategy})</span></p>
          <p><span className="text-muted-foreground">Source docs:</span> {q.retrieval.source_documents.join(', ')}</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

interface QuizResultsListProps {
  result: QuizGenerateResponse | null
  loading: boolean
}

export default function QuizResultsList({ result, loading }: QuizResultsListProps) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center space-y-2">
          <div className="h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
          <p className="text-sm text-muted-foreground">{t('quizPanel.results.generating')}</p>
        </div>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('quizPanel.results.empty')}</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto flex flex-col gap-3 p-4">
      {/* Warnings */}
      {result.warnings.length > 0 && (
        <div className="rounded border border-amber-300 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs space-y-1">
          {result.warnings.map((w, i) => (
            <p key={i} className="flex items-start gap-1.5">
              <AlertCircleIcon className="size-3 shrink-0 mt-0.5 text-amber-500" />
              {w}
            </p>
          ))}
        </div>
      )}

      {/* Question cards */}
      {result.questions.map((q, i) => (
        <QuestionCard key={q.question_id} q={q} index={i} />
      ))}
    </div>
  )
}
