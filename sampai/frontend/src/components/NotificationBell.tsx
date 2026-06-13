import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Bell, Check, Megaphone, MessageSquare, X } from 'lucide-react'
import { toast } from 'sonner'
import { apiErrorDetail, groupChatApi } from '@/api/sampai'
import { useRealtime } from '@/stores/realtime'

export default function NotificationBell() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const invites = useRealtime((s) => s.invites)
  const unread = useRealtime((s) => s.unread)
  const announcements = useRealtime((s) => s.announcements)
  const removeInvite = useRealtime((s) => s.removeInvite)
  const clearClassroomAnnouncements = useRealtime((s) => s.clearClassroomAnnouncements)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const unreadThreads = Object.entries(unread).filter(([, n]) => n > 0)
  const count = invites.length + unreadThreads.length + announcements.length

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  async function accept(id: number) {
    try {
      const gc = await groupChatApi.accept(id)
      removeInvite(id)
      qc.invalidateQueries({ queryKey: ['threads'] })
      setOpen(false)
      navigate(`/thread/${gc.id}`)
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not accept invite'))
    }
  }

  async function reject(id: number) {
    try {
      await groupChatApi.reject(id)
      removeInvite(id)
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Could not reject invite'))
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative flex h-8 w-8 items-center justify-center rounded-md text-neutral-300 hover:bg-neutral-800"
        title="Notifications"
      >
        <Bell className="h-4.5 w-4.5" />
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-violet-600 px-1 text-[10px] font-semibold text-white">
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900 shadow-xl">
          <div className="border-b border-neutral-800 px-4 py-2.5 text-sm font-medium text-neutral-200">
            Notifications
          </div>
          <div className="max-h-96 overflow-y-auto">
            {count === 0 && (
              <p className="px-4 py-6 text-center text-sm text-neutral-500">You're all caught up.</p>
            )}

            {invites.map((inv) => (
              <div key={inv.id} className="flex items-start gap-2 border-b border-neutral-800/60 px-4 py-3">
                <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-violet-400" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-neutral-200">
                    <span className="font-medium">{inv.inviter.username}</span> invited you to a group chat
                  </p>
                  <div className="mt-1.5 flex gap-2">
                    <button onClick={() => accept(inv.id)} className="inline-flex items-center gap-1 rounded-md bg-violet-600 px-2 py-1 text-xs font-medium text-white hover:bg-violet-500">
                      <Check className="h-3 w-3" /> Accept
                    </button>
                    <button onClick={() => reject(inv.id)} className="inline-flex items-center gap-1 rounded-md border border-neutral-700 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800">
                      <X className="h-3 w-3" /> Decline
                    </button>
                  </div>
                </div>
              </div>
            ))}

            {unreadThreads.map(([tid, n]) => (
              <button
                key={tid}
                onClick={() => {
                  setOpen(false)
                  navigate(`/thread/${tid}`)
                }}
                className="flex w-full items-center gap-2 border-b border-neutral-800/60 px-4 py-3 text-left hover:bg-neutral-800/40"
              >
                <Bell className="h-4 w-4 shrink-0 text-amber-400" />
                <span className="flex-1 text-sm text-neutral-200">
                  {n} new mention{n !== 1 ? 's' : ''} in a discussion
                </span>
              </button>
            ))}

            {announcements.map((a) => (
              <button
                key={`${a.kind}-${a.announcementId}-${a.by}`}
                onClick={() => {
                  setOpen(false)
                  clearClassroomAnnouncements(a.classroomId)
                  navigate(`/classroom/${a.classroomId}`)
                }}
                className="flex w-full items-center gap-2 border-b border-neutral-800/60 px-4 py-3 text-left hover:bg-neutral-800/40"
              >
                <Megaphone className="h-4 w-4 shrink-0 text-violet-400" />
                <span className="flex-1 text-sm text-neutral-200">
                  <span className="font-medium">{a.by}</span>{' '}
                  {a.kind === 'announcement' ? 'posted an announcement' : 'commented on your announcement'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
