import { useState, useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import Squares from "@/components/backgrounds/squares"
import { classroomApi } from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import { useTheme } from "@/hooks/use-theme"
import ClassroomSidebar from "@/components/classroom/sidebar"
import ClassroomHeader from "@/components/classroom/header"
import FoldersSection from "@/components/classroom/folders-section"
import AnnouncementsSection from "@/components/classroom/announcements-section"
import ClassroomCodeDisplay from "@/components/classroom/code-display"
import GroupChatsTab from "@/components/classroom/group-chats-tab"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"
import type { Classroom } from "@/lib/types"

export default function ClassroomPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const classroomId = parseInt(id ?? "0", 10)
  const { user, logout } = useAuth()
  const { theme } = useTheme()

  const [classroom, setClassroom] = useState<Classroom | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activeTab, setActiveTab] = useState<"files" | "groups">("files")

  const fetchClassroom = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await classroomApi.get(classroomId)
      setClassroom(data)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 401) { logout(); navigate("/login") }
      else if (status === 403) setError("You are not a member of this classroom")
      else if (status === 404) setError("Classroom not found")
      else setError("Failed to load classroom. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!user) { navigate("/login"); return }
    if (classroomId && !isNaN(classroomId)) void fetchClassroom()
  }, [user, classroomId]) // eslint-disable-line react-hooks/exhaustive-deps

  const isOwner = !!(user && classroom && user.id === classroom.owner_id)
  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"
  const handleLogout = () => { logout(); navigate("/login") }

  if (loading) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <LoadingOrb size={96} />
          <p className="text-sm text-muted-foreground">Loading classroom...</p>
        </div>
      </div>
    )
  }

  if (error || !classroom) {
    return (
      <div className="min-h-screen w-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-destructive">{error || "Classroom not found"}</p>
          <button onClick={() => navigate("/dashboard")} className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer">
            Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background">
      <ClassroomHeader
        classroomName={classroom.name}
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
          <div
            className="fixed top-16 z-20 flex border-b border-border bg-background/80 backdrop-blur-sm"
            style={{ width: sidebarCollapsed ? "100%" : "calc(100% - 280px)" }}
          >
            <button
              onClick={() => setActiveTab("files")}
              className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
                activeTab === "files" ? "border-violet-500 text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Files
            </button>
            <button
              onClick={() => setActiveTab("groups")}
              className={`px-5 py-2.5 text-sm font-medium transition-colors border-b-2 ${
                activeTab === "groups" ? "border-violet-500 text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Group Chats
            </button>
          </div>

          {activeTab === "files" ? (
            <div className="relative flex-1 overflow-hidden">
              <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
                <Squares speed={0.5} squareSize={40} direction="diagonal" borderColor={borderColor} hoverFillColor={hoverFillColor} />
              </div>
              <div className="relative z-10 h-full overflow-y-auto overflow-x-hidden">
                <FoldersSection classroomId={classroomId} isOwner={isOwner} />
                <div className="px-4 sm:px-6 md:px-8 pb-8">
                  <div className="h-[420px]">
                    <AnnouncementsSection classroomId={classroomId} isOwner={isOwner} currentUserId={user?.id ?? 0} />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="relative flex-1 overflow-hidden">
              <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
                <Squares speed={0.5} squareSize={40} direction="diagonal" borderColor={borderColor} hoverFillColor={hoverFillColor} />
              </div>
              <div className="relative z-10 h-full overflow-y-auto overflow-x-hidden">
                <GroupChatsTab classroomId={classroomId} />
              </div>
            </div>
          )}
        </main>

        {isOwner && <ClassroomCodeDisplay code={classroom.code} isOwner={isOwner} />}
      </div>
    </div>
  )
}
