import { useState, useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
import ClassroomHeader from "@/components/classroom/header"
import ClassroomSidebar from "@/components/classroom/sidebar"
import { GroupChatPanel } from "@/components/group-chat/group-chat-panel"
import { InviteDialog } from "@/components/group-chat/invite-dialog"
import { groupChatApi, classroomApi, fileApi, folderApi } from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import { useRealtime } from "@/stores/realtime"
import { LogOut, UserPlus } from "lucide-react"
import type { GroupChat } from "@/api/sampai"
import type { Classroom, FileItem, Folder } from "@/lib/types"

export default function GroupChatThreadPage() {
  const { threadId } = useParams<{ threadId: string }>()
  const tid = Number(threadId)
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const clearUnread = useRealtime((s) => s.clearUnread)

  const [thread, setThread] = useState<GroupChat | null>(null)
  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [currentFile, setCurrentFile] = useState<FileItem | null>(null)
  const [files, setFiles] = useState<FileItem[]>([])
  const [folder, setFolder] = useState<Folder | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [showInvite, setShowInvite] = useState(false)

  useEffect(() => {
    if (!user) { navigate("/login"); return }
    clearUnread(tid)
  }, [tid, clearUnread]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!user || !tid) return
    const load = async () => {
      try {
        const th = await groupChatApi.thread(tid)
        setThread(th)
        const [cls, file] = await Promise.all([
          classroomApi.get(th.classroom_id),
          fileApi.get(th.file_id),
        ])
        setClassroom(cls)
        setCurrentFile(file)
        const folders = await folderApi.list(th.classroom_id)
        const fo = folders.find((f) => f.id === file.folder_id) ?? null
        setFolder(fo)
        if (fo) {
          const fls = await fileApi.list(fo.id)
          setFiles(fls)
        }
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 401) { logout(); navigate("/login") }
        else setError("Group chat not found or you don't have access.")
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [user, tid]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleLogout = () => { logout(); navigate("/login") }

  if (loading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <LoadingOrb size={96} />
          <p className="text-sm text-muted-foreground">Loading group chat...</p>
        </div>
      </div>
    )
  }

  if (error || !thread || !classroom) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "Group chat not found"}</p>
          <button
            onClick={() => navigate("/dashboard")}
            className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  const members = thread.members
  const filename = currentFile?.filename ?? thread.name ?? `Group Chat #${thread.id}`
  const folderId = folder?.id ?? currentFile?.folder_id

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <ClassroomHeader
        classroomName={classroom.name}
        folderName={folder?.name}
        fileName={filename}
        classroomId={classroom.id}
        folderId={folderId}
        username={user?.username ?? ""}
        onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        onLogout={handleLogout}
      />

      <div className="flex pt-16">
        <ClassroomSidebar
          collapsed={sidebarCollapsed}
          currentClassroomId={classroom.id}
          mode="file"
          folderId={folderId}
          files={files}
          currentFileId={currentFile?.id}
          onFolderClick={() => folderId && navigate(`/classroom/${classroom.id}/folder/${folderId}`)}
          onFileSelect={(fid) => folderId && navigate(`/classroom/${classroom.id}/folder/${folderId}/file/${fid}`)}
          onHomeClick={() => navigate("/dashboard")}
        />

        <main
          className={`relative z-10 flex-1 flex flex-col h-[calc(100vh-4rem)] transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          {/* Action bar */}
          <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-border bg-background/80 backdrop-blur-sm">
            <p className="text-sm font-medium text-foreground truncate">
              {thread.name ?? `Group Chat #${thread.id}`}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowInvite(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-violet-600/10 border border-violet-500/30 text-violet-400 hover:bg-violet-600/20 transition-colors cursor-pointer"
              >
                <UserPlus className="w-3.5 h-3.5" /> Invite
              </button>
              <button
                onClick={async () => {
                  if (!confirm("Leave this group chat?")) return
                  await groupChatApi.leave(tid)
                  navigate(`/classroom/${classroom.id}`)
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-destructive/10 border border-destructive/30 text-destructive hover:bg-destructive/20 transition-colors cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" /> Leave
              </button>
            </div>
          </div>

          {/* Chat panel */}
          <div className="flex-1 min-h-0">
            {user && (
              <GroupChatPanel
                groupChatId={tid}
                currentUserId={user.id}
                members={members}
                filename={filename}
              />
            )}
          </div>
        </main>
      </div>

      {showInvite && currentFile && (
        <InviteDialog
          fileId={currentFile.id}
          classroomId={classroom.id}
          groupChatId={tid}
          onClose={() => setShowInvite(false)}
          onDone={() => setShowInvite(false)}
        />
      )}
    </div>
  )
}
