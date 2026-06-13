import { useState, type KeyboardEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Loader2, Megaphone, Plus, Send, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import RichTextEditor from '@/components/RichTextEditor'
import { announcementApi, apiErrorDetail, type AnnComment, type Announcement } from '@/api/sampai'
import { useAuth } from '@/stores/auth'

function timeAgo(iso: string): string {
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`
  return d.toLocaleDateString()
}

function Avatar({ name }: { name: string }) {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-600/25 text-xs font-semibold text-violet-200">
      {name.slice(0, 2).toUpperCase()}
    </span>
  )
}

export default function AnnouncementsPanel({ classroomId, isOwner }: { classroomId: number; isOwner: boolean }) {
  const qc = useQueryClient()
  const [composing, setComposing] = useState(false)
  const [html, setHtml] = useState('')
  const [resetSignal, setResetSignal] = useState(0)

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['announcements', classroomId],
    queryFn: () => announcementApi.list(classroomId),
  })

  const create = useMutation({
    mutationFn: () => announcementApi.create(classroomId, html),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['announcements', classroomId] })
      setHtml('')
      setResetSignal((n) => n + 1)
      setComposing(false)
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not post announcement')),
  })

  const isEmpty = !html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, '').trim()

  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-medium">
          <Megaphone className="h-5 w-5 text-violet-400" /> Announcements
        </h2>
        {isOwner && !composing && (
          <button onClick={() => setComposing(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New
          </button>
        )}
      </div>

      {composing && (
        <div className="mb-4 rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
          <RichTextEditor onChange={setHtml} resetSignal={resetSignal} />
          <div className="mt-2 flex justify-end gap-2">
            <button
              className="btn-ghost"
              onClick={() => {
                setComposing(false)
                setHtml('')
                setResetSignal((n) => n + 1)
              }}
            >
              Cancel
            </button>
            <button
              className="btn-primary disabled:opacity-40"
              disabled={isEmpty || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Post
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-neutral-500" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-800 p-10 text-center text-sm text-neutral-500">
          No announcements yet{isOwner ? ' — post one to keep your class in the loop.' : '.'}
        </div>
      ) : (
        <div className="max-h-[440px] space-y-3 overflow-y-auto pr-1">
          {items.map((a) => (
            <AnnouncementCard key={a.id} ann={a} classroomId={classroomId} isOwner={isOwner} />
          ))}
        </div>
      )}
    </section>
  )
}

function AnnouncementCard({
  ann,
  classroomId,
  isOwner,
}: {
  ann: Announcement
  classroomId: number
  isOwner: boolean
}) {
  const qc = useQueryClient()
  const myId = useAuth((s) => s.user?.id)
  const [showComments, setShowComments] = useState(false)
  const [comment, setComment] = useState('')

  const invalidate = () => qc.invalidateQueries({ queryKey: ['announcements', classroomId] })

  const del = useMutation({
    mutationFn: () => announcementApi.remove(ann.id),
    onSuccess: invalidate,
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not delete')),
  })
  const addComment = useMutation({
    mutationFn: () => announcementApi.addComment(ann.id, comment.trim()),
    onSuccess: () => {
      setComment('')
      invalidate()
    },
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not comment')),
  })
  const delComment = useMutation({
    mutationFn: (commentId: number) => announcementApi.removeComment(ann.id, commentId),
    onSuccess: invalidate,
    onError: (e) => toast.error(apiErrorDetail(e, 'Could not delete comment')),
  })

  function onCommentKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && comment.trim()) {
      e.preventDefault()
      addComment.mutate()
    }
  }

  const authorName = ann.author?.username ?? 'Unknown'
  const n = ann.comments.length

  return (
    <article className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div className="flex items-start gap-3">
        <Avatar name={authorName} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <span className="font-medium text-neutral-100">{authorName}</span>
              <span className="ml-2 text-xs text-neutral-500">{timeAgo(ann.created_at)}</span>
            </div>
            {isOwner && (
              <button
                onClick={() => del.mutate()}
                className="text-neutral-500 hover:text-red-400"
                title="Delete announcement"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
          {/* Content is sanitized server-side with nh3 before storage. */}
          <div
            className="prose prose-invert prose-sm mt-1 max-w-none break-words prose-p:my-1 prose-a:text-violet-300"
            dangerouslySetInnerHTML={{ __html: ann.content }}
          />
        </div>
      </div>

      <button
        onClick={() => setShowComments((s) => !s)}
        className="mt-2 flex items-center gap-1 pl-11 text-xs text-neutral-400 hover:text-neutral-200"
      >
        {showComments ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {n} comment{n !== 1 ? 's' : ''}
      </button>

      {showComments && (
        <div className="mt-2 space-y-2 pl-11">
          {ann.comments.map((cm: AnnComment) => {
            const name = cm.author?.username ?? 'Unknown'
            const canDelete = cm.created_by_id === myId || isOwner
            return (
              <div key={cm.id} className="group flex items-start gap-2 rounded-lg bg-neutral-950/40 px-3 py-2">
                <Avatar name={name} />
                <div className="min-w-0 flex-1">
                  <div className="text-xs">
                    <span className="font-medium text-neutral-200">{name}</span>
                    <span className="ml-2 text-neutral-500">{timeAgo(cm.created_at)}</span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-sm text-neutral-300">{cm.content}</p>
                </div>
                {canDelete && (
                  <button
                    onClick={() => delComment.mutate(cm.id)}
                    className="text-neutral-600 opacity-0 transition hover:text-red-400 group-hover:opacity-100"
                    title="Delete comment"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            )
          })}

          <div className="flex items-center gap-2">
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              onKeyDown={onCommentKey}
              placeholder="Write a comment… (Enter to post)"
              className="input flex-1"
            />
            <button
              onClick={() => addComment.mutate()}
              disabled={!comment.trim() || addComment.isPending}
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </article>
  )
}
