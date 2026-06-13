import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2, MessagesSquare } from 'lucide-react'
import { groupChatApi, type ThreadListItem } from '@/api/sampai'
import { useRealtime } from '@/stores/realtime'

/** Lists the current user's group-chat threads, filtered (e.g. by classroom or file). */
export default function GroupChatList({
  filter,
  emptyText,
}: {
  filter: (t: ThreadListItem) => boolean
  emptyText: string
}) {
  const navigate = useNavigate()
  const unread = useRealtime((s) => s.unread)
  const { data: threads = [], isLoading } = useQuery({
    queryKey: ['threads'],
    queryFn: () => groupChatApi.threads(),
  })

  const items = threads.filter(filter)

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-neutral-500" />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-neutral-800 p-12 text-center text-neutral-500">
        {emptyText}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {items.map((t) => {
        const badge = (t.unread_count || 0) + (unread[t.id] || 0)
        return (
          <button
            key={t.id}
            onClick={() => navigate(`/thread/${t.id}`)}
            className="flex w-full items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-900/50 px-4 py-3 text-left transition hover:border-violet-600/60"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-600/20 text-violet-300">
              <MessagesSquare className="h-4.5 w-4.5" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-neutral-100">{t.name || 'Group chat'}</span>
                {t.is_archived && <span className="text-xs text-neutral-600">archived</span>}
              </div>
              <p className="truncate text-xs text-neutral-500">{t.last_message_preview || 'No messages yet'}</p>
            </div>
            {badge > 0 && (
              <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-violet-600 px-1.5 text-xs font-semibold text-white">
                {badge > 99 ? '99+' : badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
