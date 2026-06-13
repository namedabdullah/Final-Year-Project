import { useState, useEffect, useRef, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { Navbar } from "@/components/landingpage/navbar"
import Folder from "@/components/backgrounds/folder"
import Plasma from "@/components/backgrounds/plasma"
import { useTheme } from "@/hooks/use-theme"
import { classroomApi } from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import type { Classroom } from "@/lib/types"

export default function CreatedPage() {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const user = useAuth((s) => s.user)
  const logout = useAuth((s) => s.logout)
  const [classrooms, setClassrooms] = useState<Classroom[]>([])
  const [loadingClassrooms, setLoadingClassrooms] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const navRef = useRef<HTMLDivElement | null>(null)
  const [navH, setNavH] = useState<number>(64)

  useEffect(() => {
    if (!navRef.current) return
    const el = navRef.current
    const ro = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height || 64
      setNavH(h)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    setLoadingClassrooms(true)
    setError(null)
    classroomApi.list()
      .then(setClassrooms)
      .catch(() => setError("Failed to load classrooms. Please try again."))
      .finally(() => setLoadingClassrooms(false))
  }, [])

  const createdClassrooms = useMemo(
    () => (user ? classrooms.filter((c) => c.owner_id === user.id) : []),
    [classrooms, user],
  )

  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"
  const folderColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <div className="relative min-h-screen bg-background overflow-x-hidden">
      <div ref={navRef}>
        <Navbar
          variant="minimal"
          username={user?.username ?? ""}
          onLogout={handleLogout}
          actions={
            <button
              type="button"
              onClick={() => navigate("/dashboard")}
              className="px-4 py-2 rounded-md border border-border/70 bg-card/60 hover:bg-card/80 cursor-pointer text-sm font-medium text-foreground"
            >
              Dashboard
            </button>
          }
        />
      </div>

      <div className="absolute inset-0 opacity-80">
        <Plasma
          key={theme}
          color={plasmaColor}
          speed={0.6}
          direction="forward"
          scale={1.08}
          opacity={0.6}
          mouseInteractive={false}
        />
      </div>

      <main
        className="relative z-10 flex flex-col"
        style={{ paddingTop: `${navH + 32}px` }}
      >
        <div className="px-8 pb-24 w-full">
          <h1 className="text-4xl font-bold text-foreground mb-20">Created Classrooms</h1>

          <div className="w-full max-w-[1600px] mx-auto px-16">
            {loadingClassrooms ? (
              <p className="mt-16 text-sm text-muted-foreground">Loading classrooms...</p>
            ) : createdClassrooms.length === 0 ? (
              <p className="mt-16 text-sm text-muted-foreground">You haven't created any classrooms yet.</p>
            ) : (
              <div className="grid grid-cols-3 gap-x-16 gap-y-24">
                {createdClassrooms.map((classroom) => (
                  <div
                    key={classroom.id}
                    className="group flex flex-col items-center gap-4 w-full cursor-pointer"
                    onClick={() => navigate(`/classroom/${classroom.id}`)}
                  >
                    <div className="relative flex items-center justify-center w-full h-[180px]">
                      <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-chart-1/30 to-chart-2/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                      <Folder
                        color={folderColor}
                        size={1.8}
                        description={classroom.description ?? ""}
                        showPapers={true}
                        className="cursor-pointer transition-transform relative z-10"
                      />
                    </div>
                    <p className="text-lg text-foreground text-center font-semibold tracking-wide leading-tight min-h-[2.5rem] px-2">
                      {classroom.name}
                    </p>
                  </div>
                ))}
              </div>
            )}
            {error && (
              <p className="mt-4 text-sm text-destructive/90">{error}</p>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
