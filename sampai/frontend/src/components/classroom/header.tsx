import { Link, useNavigate } from "react-router-dom"
import { Menu, ChevronRight, Bell, MessageSquare } from "lucide-react"
import ThemeToggle from "@/components/theme/theme-toggle"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { useRealtime } from "@/stores/realtime"
import { groupChatApi } from "@/api/sampai"

type ClassroomHeaderProps = {
  classroomName: string
  username: string
  onMenuClick: () => void
  onLogout: () => void
  folderName?: string
  fileName?: string
  topicName?: string
  classroomId?: number
  folderId?: number
  fileId?: number
}

export default function ClassroomHeader({
  classroomName,
  username,
  onMenuClick,
  onLogout,
  folderName,
  fileName,
  topicName,
  classroomId,
  folderId,
  fileId,
}: ClassroomHeaderProps) {
  const navigate = useNavigate()
  const { invites, unread, removeInvite } = useRealtime()
  const inviteCount = invites.length
  const unreadEntries = Object.entries(unread).filter(([, count]) => count > 0)
  const totalNotifications = inviteCount + unreadEntries.length

  const acceptInvite = async (id: number) => {
    try {
      await groupChatApi.accept(id)
      removeInvite(id)
    } catch {
      /* non-fatal */
    }
  }

  const rejectInvite = async (id: number) => {
    try {
      await groupChatApi.reject(id)
      removeInvite(id)
    } catch {
      /* non-fatal */
    }
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 h-16 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="flex items-center justify-between h-full px-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={onMenuClick}
            className="p-2 rounded-md hover:bg-card/50 cursor-pointer transition-colors"
            aria-label="Toggle sidebar"
          >
            <Menu className="size-5 text-foreground" />
          </button>
          {topicName ? (
            <div className="flex items-center gap-2">
              {classroomId && (
                <Link
                  to={`/classroom/${classroomId}`}
                  className="text-lg font-semibold text-foreground hover:underline transition-all cursor-pointer"
                >
                  {classroomName}
                </Link>
              )}
              <ChevronRight className="size-4 text-muted-foreground" />
              {classroomId && folderId && (
                <Link
                  to={`/classroom/${classroomId}/folder/${folderId}`}
                  className="text-lg font-semibold text-foreground hover:underline transition-all cursor-pointer"
                >
                  {folderName}
                </Link>
              )}
              <ChevronRight className="size-4 text-muted-foreground" />
              {classroomId && folderId && fileId && (
                <Link
                  to={`/classroom/${classroomId}/folder/${folderId}/file/${fileId}`}
                  className="text-lg font-semibold text-foreground hover:underline transition-all cursor-pointer"
                >
                  {fileName}
                </Link>
              )}
              <ChevronRight className="size-4 text-muted-foreground" />
              <span className="text-lg font-semibold text-foreground">{topicName}</span>
            </div>
          ) : fileName ? (
            <div className="flex items-center gap-2">
              {classroomId && (
                <Link
                  to={`/classroom/${classroomId}`}
                  className="text-lg font-semibold text-foreground hover:underline transition-all cursor-pointer"
                >
                  {classroomName}
                </Link>
              )}
              <ChevronRight className="size-4 text-muted-foreground" />
              {classroomId && folderId && (
                <Link
                  to={`/classroom/${classroomId}/folder/${folderId}`}
                  className="text-lg font-semibold text-foreground hover:underline transition-all cursor-pointer"
                >
                  {folderName}
                </Link>
              )}
              <ChevronRight className="size-4 text-muted-foreground" />
              <span className="text-lg font-semibold text-foreground">{fileName}</span>
            </div>
          ) : folderName ? (
            <div className="flex items-center gap-2">
              {classroomId && (
                <Link
                  to={`/classroom/${classroomId}`}
                  className="text-lg font-semibold text-foreground hover:underline transition-all cursor-pointer"
                >
                  {classroomName}
                </Link>
              )}
              <ChevronRight className="size-4 text-muted-foreground" />
              <span className="text-lg font-semibold text-foreground">{folderName}</span>
            </div>
          ) : (
            <h1 className="text-lg font-semibold text-foreground">{classroomName}</h1>
          )}
        </div>

        <div className="flex items-center space-x-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="relative p-2 rounded-md hover:bg-card/50 transition-colors cursor-pointer"
                aria-label={`${totalNotifications} notification${totalNotifications !== 1 ? "s" : ""}`}
              >
                <Bell className="size-5 text-foreground" />
                {totalNotifications > 0 && (
                  <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-violet-600 text-[10px] text-white font-bold flex items-center justify-center">
                    {totalNotifications > 9 ? "9+" : totalNotifications}
                  </span>
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80 max-h-96 overflow-y-auto">
              {totalNotifications === 0 ? (
                <div className="px-4 py-3 text-sm text-muted-foreground">No notifications</div>
              ) : (
                <>
                  {invites.map((inv) => (
                    <div key={`inv-${inv.id}`} className="px-4 py-3 flex flex-col gap-2 border-b border-border last:border-0">
                      <p className="text-sm">
                        <span className="font-medium">{inv.inviter.username}</span>
                        {" invited you to a group chat"}
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => void acceptInvite(inv.id)}
                          className="flex-1 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs py-1.5 font-medium transition-colors cursor-pointer"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => void rejectInvite(inv.id)}
                          className="flex-1 rounded-md border border-border hover:bg-muted text-xs py-1.5 transition-colors cursor-pointer"
                        >
                          Decline
                        </button>
                      </div>
                    </div>
                  ))}
                  {unreadEntries.map(([threadIdStr, count]) => {
                    const threadId = Number(threadIdStr)
                    return (
                      <button
                        key={`unread-${threadId}`}
                        onClick={() => {
                          if (classroomId) {
                            navigate(`/classroom/${classroomId}/group/${threadId}`)
                          }
                        }}
                        className="w-full px-4 py-3 flex items-center gap-3 border-b border-border last:border-0 hover:bg-muted/40 cursor-pointer text-left"
                      >
                        <div className="w-8 h-8 rounded-full bg-violet-600/20 flex items-center justify-center shrink-0">
                          <MessageSquare className="w-4 h-4 text-violet-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">Group chat</p>
                          <p className="text-xs text-muted-foreground">
                            {count} new message{count !== 1 ? "s" : ""}
                          </p>
                        </div>
                      </button>
                    )
                  })}
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <ThemeToggle />

          <DropdownMenu>
            <DropdownMenuTrigger>
              <div className="flex items-center gap-2 cursor-pointer">
                <div
                  aria-hidden
                  className="size-8 rounded-full bg-gradient-to-br from-chart-1 to-chart-2 ring-1 ring-border/50 shadow-inner"
                />
                <span className="text-sm text-foreground/80">{username}</span>
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-72">
              <div className="flex flex-col items-center gap-3 px-4 py-4">
                <div
                  aria-hidden
                  className="size-16 rounded-full bg-gradient-to-br from-chart-1 to-chart-2 ring-1 ring-border/50 shadow-inner"
                />
                <span className="text-base font-semibold text-foreground">{username}</span>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={onLogout}
                className="cursor-pointer text-red-500 focus:text-red-500 hover:text-red-500"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="size-4 mr-2"
                  aria-hidden
                >
                  <path d="M16 13v-2H7V8l-5 4 5 4v-3h9zM20 3h-8v2h8v14h-8v2h8a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z" />
                </svg>
                <span>Log out</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}
