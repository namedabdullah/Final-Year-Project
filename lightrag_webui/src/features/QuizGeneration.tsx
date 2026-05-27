/**
 * QuizGeneration — top-level Quiz tab page.
 *
 * Layout (mirrors RetrievalTesting):
 *
 *   ┌──────────────────┬────────────────────────────┬──────────────┐
 *   │ QuizDocument-    │  QuizResultsList            │ QuizSettings │
 *   │ Selector         │  (questions + metadata)     │ (right       │
 *   │ (left panel,     │                             │  sidebar)    │
 *   │  doc checkboxes) │  QuizForm (action bar)      │              │
 *   │                  │                             │              │
 *   │ QuizHistory      │                             │              │
 *   │ (stored quizzes) │                             │              │
 *   └──────────────────┴────────────────────────────┴──────────────┘
 */

import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from '@/stores/settings'
import {
  generateQuiz,
  reverifyQuiz,
  getQuiz,
  QuizGenerateResponse,
  QuizGenerateRequest,
  QuizMode,
  QuizNumQuestions,
} from '@/api/lightrag'

import QuizDocumentSelector from '@/components/quiz/QuizDocumentSelector'
import QuizHistory from '@/components/quiz/QuizHistory'
import QuizResultsList from '@/components/quiz/QuizResultsList'
import QuizForm from '@/components/quiz/QuizForm'
import QuizSettings from '@/components/quiz/QuizSettings'

export default function QuizGeneration() {
  const { t } = useTranslation()
  const quizSettings = useSettingsStore((s) => s.quizSettings)
  const querySettings = useSettingsStore((s) => s.querySettings)

  const [result, setResult] = useState<QuizGenerateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── Generate ──────────────────────────────────────────────────────────────

  const handleGenerate = useCallback(async () => {
    if (quizSettings.selectedDocumentIds.length === 0) {
      setError(t('quizPanel.errors.noDocuments'))
      return
    }
    setError(null)
    setLoading(true)
    try {
      const req: QuizGenerateRequest = {
        document_ids: quizSettings.selectedDocumentIds,
        mode: (querySettings.mode as QuizMode) ?? 'mix',
        difficulty: quizSettings.difficulty,
        num_questions: quizSettings.numQuestions as QuizNumQuestions,
        run_verification: quizSettings.runVerification,
        top_k: querySettings.top_k,
        chunk_top_k: querySettings.chunk_top_k,
        max_entity_tokens: querySettings.max_entity_tokens,
        max_relation_tokens: querySettings.max_relation_tokens,
        max_total_tokens: querySettings.max_total_tokens,
      }
      const response = await generateQuiz(req)
      setResult(response)
    } catch (err: any) {
      setError(err?.message ?? t('quizPanel.errors.generateFailed'))
    } finally {
      setLoading(false)
    }
  }, [quizSettings, querySettings, t])

  // ── Re-verify ─────────────────────────────────────────────────────────────

  const handleReverify = useCallback(async () => {
    if (!result) return
    setError(null)
    setLoading(true)
    try {
      const reverified = await reverifyQuiz(result.quiz_id)
      setResult(reverified)
    } catch (err: any) {
      setError(err?.message ?? t('quizPanel.errors.reverifyFailed'))
    } finally {
      setLoading(false)
    }
  }, [result, t])

  // ── Load stored quiz ──────────────────────────────────────────────────────

  const handleLoad = useCallback(async (quizId: string) => {
    setError(null)
    setLoading(true)
    try {
      const stored = await getQuiz(quizId)
      setResult(stored)
    } catch (err: any) {
      setError(err?.message ?? t('quizPanel.errors.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full gap-4 p-4 overflow-hidden">

      {/* Left: document selector + history */}
      <div className="flex shrink-0 flex-col w-[240px] overflow-hidden gap-0">
        <QuizDocumentSelector />
        <QuizHistory onLoad={handleLoad} currentQuizId={result?.quiz_id} />
      </div>

      {/* Middle: results + form */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <QuizResultsList result={result} loading={loading} />
        <QuizForm
          onGenerate={handleGenerate}
          onReverify={handleReverify}
          result={result}
          loading={loading}
          error={error}
        />
      </div>

      {/* Right: settings sidebar */}
      <QuizSettings />
    </div>
  )
}
