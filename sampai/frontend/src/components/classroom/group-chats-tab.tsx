import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { Users } from "lucide-react"
import { groupChatApi } from "@/api/sampai"
import Folder from "@/components/backgrounds/folder"
import { useTheme } from "@/hooks/use-theme"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
import { useRealtime } from "@/stores/realtime"
import type { ThreadListItem } from "@/api/sampai"

type Props = {
  classroomId: number
}

export default function GroupChatsTab({ classroomId: _classroomId }: Props) {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const { unread } = useRealtime()
  const [threads, setThreads] = useState<ThreadListItem[]>([])
  const [loading, setLoading] = useState(true)

  const folderColor = theme === "dark" ? "#C4B5FD" : "#A78BFA"

  useEffect(() => {
    groupChatApi.threads()
      .then((data) => setThreads(data.filter((t) => !t.is_archived)))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const hasThreads = threads.length > 0

  return (
    <div className="p-4 sm:p-6 md:p-8 pt-20 sm:pt-24 md:pt-28 min-h-full w-full overflow-x-hidden">
      <div className="max-w-[1400px] mx-auto w-full">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 min-h-[60vh] gap-4">
            <LoadingOrb size={96} />
            <p className="text-sm text-muted-foreground">Loading group chats...</p>
          </div>
        ) : !hasThreads ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
            <Users className="w-12 h-12 text-muted-foreground/40" />
            <p className="text-muted-foreground text-sm">No group chats yet.</p>
            <p className="text-muted-foreground/60 text-xs text-center max-w-sm">
              Open a file and invite classmates to start a group study session.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 sm:gap-x-8 md:gap-x-10 gap-y-20 sm:gap-y-24">
            {threads.map((thread) => {
              const liveUnread = unread[thread.id] ?? thread.unread_count
              const displayName = thread.name ?? `Group Chat #${thread.id}`
              return (
                <div
                  key={thread.id}
                  className="group flex flex-col items-center cursor-pointer relative"
                  onClick={() => navigate(`/thread/${thread.id}`)}
                >
                  <div className="relative flex items-center justify-center w-full h-[150px] mb-2 overflow-visible">
                    <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-violet-500/30 to-purple-400/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="relative z-10 flex items-center justify-center">
                      <Folder color={folderColor} size={1.4} description="" showPapers className="cursor-pointer transition-transform" />
                    </div>
                    {liveUnread > 0 && (
                      <span className="absolute top-2 right-1/2 translate-x-12 z-20 min-w-6 h-6 px-1.5 rounded-full bg-violet-600 text-[11px] text-white font-bold flex items-center justify-center shadow-lg ring-2 ring-background">
                        {liveUnread > 99 ? "99+" : liveUnread}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 line-clamp-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                    {displayName}
                  </p>
                  {thread.last_message_preview && (
                    <p className="text-xs text-muted-foreground text-center px-2 line-clamp-1 mt-1 max-w-[200px]">
                      {thread.last_message_preview}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
