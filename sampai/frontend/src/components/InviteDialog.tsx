import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, UserPlus, X } from 'lucide-react'
import { toast } from 'sonner'
import { apiErrorDetail, groupChatApi, type UserSummary } from '@/api/sampai'

/**
 * Invite classmates to discuss a file.
 * - `groupChatId` omitted → creates a new thread and returns its id via onDone.
 * - `groupChatId` set      → adds invitees to that existing thread.
 */
export default function InviteDialog({
  fileId,
  groupChatId,
  onClose,
  onDone,
}: {
  fileId: number
  groupChatId?: number
  onClose: () => void
  onDone?: (threadId: number) => void
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [sending, setSending] = useState(false)

  const { data: eligible = [], isLoading } = useQuery({
    queryKey: ['eligible', fileId, groupChatId ?? null],
    queryFn: () => groupChatApi.eligible(fileId, groupChatId),
  })

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function submit() {
    if (selected.size === 0 || sending) return
    setSending(true)
    try {
      const res = await groupChatApi.invite(fileId, [...selected], groupChatId)
      toast.success(`Invited ${selected.size} ${selected.size === 1 ? 'person' : 'people'}`)
      onDone?.(res.group_chat_id)
      onClose()
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not send invites'))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" onMouseDown={onClose}>
      <div
        className="w-full max-w-md overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-medium text-neutral-200">
            <UserPlus className="h-4 w-4 text-violet-400" />
            {groupChatId ? 'Invite to this discussion' : 'Start a group chat'}
          </h3>
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-72 overflow-y-auto p-2">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-neutral-500" />
            </div>
          ) : eligible.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-neutral-500">No classmates available to invite.</p>
          ) : (
            eligible.map((u: UserSummary) => (
              <label
                key={u.id}
                className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 hover:bg-neutral-800/50"
              >
                <input
                  type="checkbox"
                  checked={selected.has(u.id)}
                  onChange={() => toggle(u.id)}
                  className="h-4 w-4 accent-violet-600"
                />
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-600/25 text-xs font-semibold text-violet-200">
                  {u.username.slice(0, 2).toUpperCase()}
                </span>
                <span className="text-sm text-neutral-200">{u.username}</span>
              </label>
            ))
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-neutral-800 px-4 py-3">
          <button onClick={onClose} className="btn-ghost">
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={selected.size === 0 || sending}
            className="btn-primary disabled:opacity-40"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            {groupChatId ? 'Invite' : 'Create chat'}
          </button>
        </div>
      </div>
    </div>
  )
}
