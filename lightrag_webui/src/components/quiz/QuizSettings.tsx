/**
 * QuizSettings — right sidebar of the Quiz tab.
 *
 * Mirrors QuerySettings.tsx structure but replaces some retrieval-specific
 * fields with quiz-specific ones:
 *   - Difficulty selector (easy / medium / hard)
 *   - Number of questions (10 / 25 / 50)
 *   - Run verification toggle (Claude Sonnet)
 *   - Mode selector (with tooltip warning for non-rigorous modes)
 * Plus it forwards the shared retrieval params (top_k, chunk_top_k, tokens)
 * to the quizSettings store so they're available when building the request.
 */

import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsStore, QuizSettings } from '@/stores/settings'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import Checkbox from '@/components/ui/Checkbox'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/Tooltip'
import { AlertTriangleIcon } from 'lucide-react'

type QuizMode = 'local' | 'global' | 'hybrid' | 'mix' | 'naive'
type QuizDifficulty = 'easy' | 'medium' | 'hard'
type QuizNumQuestions = 10 | 25 | 50

// Modes that use thesis-rigorous difficulty mechanics
const RIGOROUS_MODES: QuizMode[] = ['mix', 'naive']

export default function QuizSettings() {
  const { t } = useTranslation()
  const quizSettings = useSettingsStore((s) => s.quizSettings)
  const querySettings = useSettingsStore((s) => s.querySettings)
  const updateQuizSettings = useSettingsStore.use.updateQuizSettings()
  const updateQuerySettings = useSettingsStore.use.updateQuerySettings()

  const mode = (querySettings.mode as QuizMode) ?? 'mix'
  const isNonRigorous = !RIGOROUS_MODES.includes(mode)

  const handleModeChange = useCallback(
    (v: string) => updateQuerySettings({ mode: v as any }),
    [updateQuerySettings]
  )

  const handleDifficultyChange = useCallback(
    (v: string) => updateQuizSettings({ difficulty: v as QuizDifficulty }),
    [updateQuizSettings]
  )

  const handleNumQuestionsChange = useCallback(
    (v: string) => updateQuizSettings({ numQuestions: parseInt(v) as QuizNumQuestions }),
    [updateQuizSettings]
  )

  const handleVerificationChange = useCallback(
    (checked: boolean | 'indeterminate') => {
      if (typeof checked === 'boolean') updateQuizSettings({ runVerification: checked })
    },
    [updateQuizSettings]
  )

  return (
    <Card className="flex shrink-0 flex-col w-[280px]">
      <CardHeader className="px-4 pt-4 pb-2">
        <CardTitle>{t('quizPanel.settings.title')}</CardTitle>
        <CardDescription className="sr-only">
          {t('quizPanel.settings.description')}
        </CardDescription>
      </CardHeader>

      <CardContent className="m-0 flex grow flex-col p-0 text-xs">
        <div className="relative size-full">
          <div className="absolute inset-0 flex flex-col gap-2 overflow-auto px-2 pr-2 pb-4">

            {/* ── Retrieval Mode ──────────────────────────────────────── */}
            <>
              <div className="flex items-center gap-1 mt-2">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <label htmlFor="quiz_mode_select" className="ml-1 flex-1 cursor-help">
                        {t('quizPanel.settings.modeLabel')}
                      </label>
                    </TooltipTrigger>
                    <TooltipContent side="left" className="max-w-[220px]">
                      <p>{t('quizPanel.settings.modeTooltip')}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                {isNonRigorous && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <AlertTriangleIcon className="size-3 text-amber-500 shrink-0" />
                      </TooltipTrigger>
                      <TooltipContent side="left" className="max-w-[240px]">
                        <p>{t('quizPanel.settings.modeWarning')}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
              </div>
              <Select value={mode} onValueChange={handleModeChange}>
                <SelectTrigger
                  id="quiz_mode_select"
                  className="hover:bg-primary/5 h-9 cursor-pointer focus:ring-0 focus:ring-offset-0 focus:outline-0 flex-1 text-left"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="mix">Mix (graph — rigorous)</SelectItem>
                    <SelectItem value="naive">Naive (chunks — rigorous)</SelectItem>
                    <SelectItem value="local">Local (coarse proxy)</SelectItem>
                    <SelectItem value="global">Global (coarse proxy)</SelectItem>
                    <SelectItem value="hybrid">Hybrid (coarse proxy)</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </>

            {/* ── Difficulty ──────────────────────────────────────────── */}
            <>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <label htmlFor="quiz_difficulty_select" className="ml-1 cursor-help mt-1">
                      {t('quizPanel.settings.difficultyTitle')}
                    </label>
                  </TooltipTrigger>
                  <TooltipContent side="left" className="max-w-[240px]">
                    <p>{t('quizPanel.settings.difficultyTooltip')}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <Select value={quizSettings.difficulty} onValueChange={handleDifficultyChange}>
                <SelectTrigger
                  id="quiz_difficulty_select"
                  className="hover:bg-primary/5 h-9 cursor-pointer focus:ring-0 focus:ring-offset-0 focus:outline-0 flex-1 text-left"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="easy">{t('quizPanel.settings.difficultyEasy')}</SelectItem>
                    <SelectItem value="medium">{t('quizPanel.settings.difficultyMedium')}</SelectItem>
                    <SelectItem value="hard">{t('quizPanel.settings.difficultyHard')}</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </>

            {/* ── Number of questions ─────────────────────────────────── */}
            <>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <label htmlFor="quiz_num_questions_select" className="ml-1 cursor-help mt-1">
                      {t('quizPanel.settings.numQuestionsTitle')}
                    </label>
                  </TooltipTrigger>
                  <TooltipContent side="left">
                    <p>{t('quizPanel.settings.numQuestionsTooltip')}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <Select
                value={String(quizSettings.numQuestions)}
                onValueChange={handleNumQuestionsChange}
              >
                <SelectTrigger
                  id="quiz_num_questions_select"
                  className="hover:bg-primary/5 h-9 cursor-pointer focus:ring-0 focus:ring-offset-0 focus:outline-0 flex-1 text-left"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="25">25</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </>

            {/* ── Run verification ────────────────────────────────────── */}
            <div className="flex items-center gap-2 mt-2">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <label htmlFor="quiz_run_verification" className="flex-1 ml-1 cursor-help">
                      {t('quizPanel.settings.runVerification')}
                    </label>
                  </TooltipTrigger>
                  <TooltipContent side="left" className="max-w-[240px]">
                    <p>{t('quizPanel.settings.runVerificationTooltip')}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <Checkbox
                id="quiz_run_verification"
                className="mr-10 cursor-pointer"
                checked={quizSettings.runVerification}
                onCheckedChange={handleVerificationChange}
              />
            </div>

            {/* ── Divider ─────────────────────────────────────────────── */}
            <hr className="my-1 border-border" />
            <p className="ml-1 text-muted-foreground text-[10px] uppercase tracking-wide">
              Advanced Retrieval Params
            </p>

            {/* ── Top K ───────────────────────────────────────────────── */}
            <>
              <label htmlFor="quiz_top_k" className="ml-1">
                {t('retrievePanel.querySettings.topK')}
              </label>
              <input
                id="quiz_top_k"
                type="number"
                min={1}
                value={querySettings.top_k ?? ''}
                onChange={(e) =>
                  updateQuerySettings({ top_k: e.target.value === '' ? undefined : parseInt(e.target.value) })
                }
                className="h-9 w-full rounded border border-input bg-background px-3 text-xs focus:outline-none"
              />
            </>

            {/* ── Chunk Top K ─────────────────────────────────────────── */}
            <>
              <label htmlFor="quiz_chunk_top_k" className="ml-1">
                {t('retrievePanel.querySettings.chunkTopK')}
              </label>
              <input
                id="quiz_chunk_top_k"
                type="number"
                min={1}
                value={querySettings.chunk_top_k ?? ''}
                onChange={(e) =>
                  updateQuerySettings({
                    chunk_top_k: e.target.value === '' ? undefined : parseInt(e.target.value),
                  })
                }
                className="h-9 w-full rounded border border-input bg-background px-3 text-xs focus:outline-none"
              />
            </>

          </div>
        </div>
      </CardContent>
    </Card>
  )
}
