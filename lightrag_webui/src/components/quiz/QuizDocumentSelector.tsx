/**
 * QuizDocumentSelector — left panel of the Quiz tab.
 *
 * Shows all processed documents as a checkbox list.  The user picks which
 * documents the quiz should be scoped to.  Selected document IDs are stored
 * in the quizSettings slice of the settings store.
 */

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DocStatusResponse, getDocumentsPaginated } from '@/api/lightrag'
import { useSettingsStore } from '@/stores/settings'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import Checkbox from '@/components/ui/Checkbox'
import { cn } from '@/lib/utils'

export default function QuizDocumentSelector() {
  const { t } = useTranslation()
  const quizSettings = useSettingsStore((s) => s.quizSettings)
  const updateQuizSettings = useSettingsStore.use.updateQuizSettings()

  const [docs, setDocs] = useState<DocStatusResponse[]>([])
  const [loading, setLoading] = useState(true)

  // Fetch processed documents
  useEffect(() => {
    let cancelled = false
    const fetchDocs = async () => {
      setLoading(true)
      try {
        const res = await getDocumentsPaginated({
          status_filter: 'processed',
          page: 1,
          page_size: 200,
          sort_field: 'created_at',
          sort_direction: 'desc',
        })
        if (!cancelled) setDocs(res.documents)
      } catch {
        // silently ignore; user can still type document IDs manually
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchDocs()
    return () => { cancelled = true }
  }, [])

  const selectedIds = new Set(quizSettings.selectedDocumentIds)

  const toggleDoc = useCallback(
    (id: string) => {
      const next = new Set(selectedIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      updateQuizSettings({ selectedDocumentIds: Array.from(next) })
    },
    [selectedIds, updateQuizSettings]
  )

  const toggleAll = useCallback(() => {
    if (selectedIds.size === docs.length) {
      updateQuizSettings({ selectedDocumentIds: [] })
    } else {
      updateQuizSettings({ selectedDocumentIds: docs.map((d) => d.id) })
    }
  }, [docs, selectedIds.size, updateQuizSettings])

  const allSelected = docs.length > 0 && selectedIds.size === docs.length
  const someSelected = selectedIds.size > 0 && !allSelected

  return (
    <Card className="flex shrink-0 flex-col flex-1 overflow-hidden min-h-0">
      <CardHeader className="px-4 pt-4 pb-2 shrink-0">
        <CardTitle className="text-sm">
          {t('quizPanel.documentSelector.title')}
        </CardTitle>
        {docs.length > 0 && (
          <div className="flex items-center gap-2 mt-1">
            <Checkbox
              id="quiz-select-all"
              checked={allSelected}
              // indeterminate state via data attribute
              data-indeterminate={someSelected ? 'true' : undefined}
              onCheckedChange={toggleAll}
              className="cursor-pointer"
            />
            <label htmlFor="quiz-select-all" className="text-xs cursor-pointer select-none">
              {someSelected
                ? t('quizPanel.documentSelector.selectedCount', { count: selectedIds.size })
                : t('quizPanel.documentSelector.selectAll')}
            </label>
          </div>
        )}
      </CardHeader>

      <CardContent className="flex-1 overflow-auto p-0 px-2 pb-2">
        {loading ? (
          <p className="text-xs text-muted-foreground px-2 py-4">Loading documents…</p>
        ) : docs.length === 0 ? (
          <p className="text-xs text-muted-foreground px-2 py-4">
            No processed documents found.
          </p>
        ) : (
          <ul className="flex flex-col gap-1 mt-1">
            {docs.map((doc) => {
              const isChecked = selectedIds.has(doc.id)
              const label = doc.file_path
                ? doc.file_path.split('/').pop() ?? doc.id
                : doc.content_summary?.slice(0, 30) ?? doc.id
              return (
                <li
                  key={doc.id}
                  className={cn(
                    'flex items-start gap-2 rounded px-2 py-1 text-xs cursor-pointer hover:bg-muted',
                    isChecked && 'bg-emerald-50 dark:bg-emerald-950/30'
                  )}
                  onClick={() => toggleDoc(doc.id)}
                >
                  <Checkbox
                    checked={isChecked}
                    onCheckedChange={() => toggleDoc(doc.id)}
                    className="mt-0.5 shrink-0 cursor-pointer"
                  />
                  <span
                    className="break-all leading-tight"
                    title={doc.file_path ?? doc.id}
                  >
                    {label}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
