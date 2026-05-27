/**
 * QuizForm — bottom action bar of the Quiz tab.
 *
 * Contains:
 *   - Generate Quiz button
 *   - Status / error display
 *   - Download JSON button (when a result exists)
 *   - Copy questions-only button (when a result exists)
 *   - Re-verify button (when a result exists)
 */

import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { QuizGenerateResponse } from '@/api/lightrag'
import Button from '@/components/ui/Button'
import { DownloadIcon, ClipboardCopyIcon, RefreshCwIcon, ZapIcon } from 'lucide-react'

interface QuizFormProps {
  onGenerate: () => Promise<void>
  onReverify: () => Promise<void>
  result: QuizGenerateResponse | null
  loading: boolean
  error: string | null
}

export default function QuizForm({ onGenerate, onReverify, result, loading, error }: QuizFormProps) {
  const { t } = useTranslation()
  const [copying, setCopying] = useState(false)

  const handleDownload = useCallback(() => {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `quiz-${result.quiz_id.slice(0, 8)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [result])

  const handleCopyQuestions = useCallback(async () => {
    if (!result) return
    const text = result.questions
      .map((q, i) => `Q${i + 1}. ${q.generation.question}\n\nAnswer: ${q.generation.reference_answer}`)
      .join('\n\n---\n\n')
    setCopying(true)
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // fallback
    } finally {
      setTimeout(() => setCopying(false), 1200)
    }
  }, [result])

  return (
    <div className="shrink-0 border-t border-border p-3 flex flex-col gap-2">
      {/* Error display */}
      {error && (
        <p className="text-xs text-red-500 px-1">{error}</p>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        {/* Generate */}
        <Button
          onClick={onGenerate}
          disabled={loading}
          className="gap-1.5"
        >
          <ZapIcon className="size-3.5" />
          {loading ? t('quizPanel.results.generating') : t('quizPanel.form.generate')}
        </Button>

        {/* Post-generation actions */}
        {result && !loading && (
          <>
            <Button
              variant="outline"
              onClick={handleDownload}
              className="gap-1.5"
            >
              <DownloadIcon className="size-3.5" />
              {t('quizPanel.results.downloadJson')}
            </Button>

            <Button
              variant="outline"
              onClick={handleCopyQuestions}
              className="gap-1.5"
            >
              <ClipboardCopyIcon className="size-3.5" />
              {copying ? 'Copied!' : t('quizPanel.results.copyQuestions')}
            </Button>

            <Button
              variant="outline"
              onClick={onReverify}
              className="gap-1.5"
            >
              <RefreshCwIcon className="size-3.5" />
              {t('quizPanel.results.reverify')}
            </Button>
          </>
        )}
      </div>

      {/* Quiz ID & path (for archival reference) */}
      {result && (
        <p className="text-[10px] text-muted-foreground font-mono">
          quiz_id: {result.quiz_id} — {result.questions.length} questions
          {result.metadata_path && ` — saved: ${result.metadata_path}`}
        </p>
      )}
    </div>
  )
}
