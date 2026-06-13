import { useState, useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import Squares from "@/components/backgrounds/squares"
import { classroomApi, folderApi } from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import FilesSection from "@/components/classroom/files-section"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
import type { Classroom, Folder } from "@/lib/types"

export default function FolderPage() {
  const { id, folderId } = useParams<{ id: string; folderId: string }>()
  const navigate = useNavigate()
  const classroomId = parseInt(id ?? "0", 10)
  const folderIdNum = parseInt(folderId ?? "0", 10)
  const { user, logout } = useAuth()
  const { theme } = useTheme()

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [folder, setFolder] = useState<Folder | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const borderColor = theme === "dark" ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)"
  const hoverFillColor = theme === "dark" ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.05)"

  useEffect(() => {
    if (!user) { navigate("/login"); return }
    if (!classroomId || isNaN(classroomId) || !folderIdNum || isNaN(folderIdNum)) return
    const fetchAll = async () => {
      setLoading(true)
      setError(null)
      try {
        const [cls, folders] = await Promise.all([
          classroomApi.get(classroomId),
          folderApi.list(classroomId),
        ])
        setClassroom(cls)
        const found = folders.find((f) => f.id === folderIdNum)
        if (found) setFolder(found)
        else setError("Folder not found")
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        if (status === 401) { logout(); navigate("/login") }
        else if (status === 403) setError("You are not a member of this classroom")
        else if (status === 404) setError("Not found")
        else setError("Failed to load. Please try again.")
      } finally {
        setLoading(false)
      }
    }
    void fetchAll()
  }, [user, classroomId, folderIdNum]) // eslint-disable-line react-hooks/exhaustive-deps

  const isOwner = !!(user && classroom && user.id === classroom.owner_id)
  const handleLogout = () => { logout(); navigate("/login") }

  if (loading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <LoadingOrb size={96} />
          <p className="text-sm text-muted-foreground">Loading folder...</p>
        </div>
      </div>
    )
  }

  if (error || !classroom || !folder) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "Folder not found"}</p>
          <button onClick={() => navigate(`/classroom/${classroomId}`)} className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer">
            Back to Classroom
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <ClassroomHeader
        classroomName={classroom.name}
        folderName={folder.name}
        classroomId={classroomId}
        username={user?.username ?? ""}
        onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        onLogout={handleLogout}
      />

      <div className="flex pt-16">
        <ClassroomSidebar
          collapsed={sidebarCollapsed}
          currentClassroomId={classroomId}
          onHomeClick={() => navigate(isOwner ? "/created" : "/joined")}
        />

        <main
          className={`flex-1 flex flex-col min-h-[calc(100vh-4rem)] transition-all duration-300 ${
            sidebarCollapsed ? "ml-0" : "ml-[280px]"
          }`}
        >
          <div className="z-20 flex shrink-0 border-b border-border bg-background/80 backdrop-blur-sm">
            <button
              type="button"
              className="px-5 py-2.5 text-sm font-medium transition-colors border-b-2 border-violet-500 text-foreground"
            >
              Files
            </button>
            <button
              type="button"
              onClick={() => navigate(`/classroom/${classroomId}/folder/${folderIdNum}/cross-quiz`)}
              className="px-5 py-2.5 text-sm font-medium transition-colors border-b-2 border-transparent text-muted-foreground hover:text-foreground"
            >
              Cross-file quiz
            </button>
          </div>

          <div className="relative flex-1 overflow-hidden">
            <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
              <Squares speed={0.5} squareSize={40} direction="diagonal" borderColor={borderColor} hoverFillColor={hoverFillColor} />
            </div>
            <div className="relative z-10 h-full overflow-y-auto overflow-x-hidden">
              <FilesSection classroomId={classroomId} folderId={folderIdNum} isOwner={isOwner} />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
