import { useState, useEffect, useRef, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Plus, LogIn, X } from "lucide-react"
import { toast } from "sonner"
import Navbar from "@/components/landingpage/navbar"
import { LeftPane } from "@/components/dashboard/left-pane"
import { RightPane } from "@/components/dashboard/right-pane"
import Orb from "@/components/backgrounds/orb"
import Squares from "@/components/backgrounds/squares"
import { apiErrorDetail, classroomApi } from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import { useTheme } from "@/hooks/use-theme"
import type { Classroom } from "@/lib/types"

const LEFT_PANE_W = 360
const EXPAND_MS = 650

export default function DashboardPage() {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const logout = useAuth((s) => s.logout)
  const { theme } = useTheme()

  // ── data ──
  const [classrooms, setClassrooms] = useState<Classroom[]>([])

  const fetchClassrooms = useCallback(async () => {
    try {
      const data = await classroomApi.list()
      setClassrooms(data)
    } catch (e) {
      toast.error(apiErrorDetail(e, "Failed to load classrooms"))
    }
  }, [])

  useEffect(() => { fetchClassrooms() }, [fetchClassrooms])

  // ── modal state ──
  const [showCreate, setShowCreate] = useState(false)
  const [showJoin, setShowJoin] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createDesc, setCreateDesc] = useState("")
  const [joinCode, setJoinCode] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const closeModal = useCallback(() => {
    setShowCreate(false)
    setShowJoin(false)
    setCreateName("")
    setCreateDesc("")
    setJoinCode("")
    setFormError(null)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeModal() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [closeModal])

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = createName.trim()
    if (!name || isSubmitting) return
    setIsSubmitting(true)
    setFormError(null)
    try {
      const c = await classroomApi.create({ name, description: createDesc.trim() || undefined })
      setClassrooms((prev) => [...prev, c])
      closeModal()
      navigate(`/classroom/${c.id}`)
    } catch (e) {
      setFormError(apiErrorDetail(e, "Failed to create classroom."))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleJoinSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const code = joinCode.trim()
    if (!code || isSubmitting) return
    setIsSubmitting(true)
    setFormError(null)
    try {
      const c = await classroomApi.join(code.toUpperCase())
      setClassrooms((prev) => prev.find((x) => x.id === c.id) ? prev : [...prev, c])
      closeModal()
      navigate(`/classroom/${c.id}`)
    } catch (e) {
      setFormError(apiErrorDetail(e, "Failed to join classroom."))
    } finally {
      setIsSubmitting(false)
    }
  }

  // ── nav height ──
  const navRef = useRef<HTMLDivElement>(null)
  const [navH, setNavH] = useState(64)

  useEffect(() => {
    if (!navRef.current) return
    const ro = new ResizeObserver((entries) => {
      setNavH(entries[0]?.contentRect.height || 64)
    })
    ro.observe(navRef.current)
    return () => ro.disconnect()
  }, [])

  // ── viewport width (for expand animation) ──
  const [viewportW, setViewportW] = useState(0)
  useEffect(() => {
    const update = () => setViewportW(window.innerWidth)
    update()
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [])

  // ── expand overlay → navigate ──
  const [expandingPane, setExpandingPane] = useState<null | "joined" | "created">(null)
  const expandTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const triggerExpand = (pane: "joined" | "created") => {
    if (expandingPane) return
    setExpandingPane(pane)
    expandTimerRef.current = setTimeout(() => {
      navigate(pane === "joined" ? "/joined" : "/created")
    }, EXPAND_MS)
  }

  useEffect(() => () => { if (expandTimerRef.current) clearTimeout(expandTimerRef.current) }, [])

  // ── derived lists ──
  const joinedClassrooms = classrooms.filter((c) => c.owner_id !== user?.id)
  const createdClassrooms = classrooms.filter((c) => c.owner_id === user?.id)
  const hasCreated = createdClassrooms.length > 0

  const handleLogout = () => { logout(); navigate("/login") }

  // ── Squares colors ──
  const borderColor = theme === "dark" ? "rgba(147, 197, 253, 0.3)" : "rgba(56, 189, 248, 0.4)"
  const hoverFillColor = theme === "dark" ? "rgba(147, 197, 253, 0.1)" : "rgba(56, 189, 248, 0.15)"

  return (
    <div className="relative min-h-screen w-screen overflow-hidden bg-background">

      <div ref={navRef} className="relative z-10">
        <Navbar
          variant="minimal"
          username={user?.username ?? ""}
          onLogout={handleLogout}
        />
      </div>

      {/* Main fills everything below navbar */}
      <main
        className="absolute left-0 right-0 bottom-0 flex z-10"
        style={{ top: `${navH}px` }}
      >
        {/* Left Pane — always visible */}
        <LeftPane
          classrooms={joinedClassrooms.map((c) => c.name)}
          classroomObjects={joinedClassrooms}
          onSelect={(_name, index) => {
            const c = joinedClassrooms[index]
            if (c) navigate(`/classroom/${c.id}`)
          }}
          onExpand={() => triggerExpand("joined")}
          className="rounded-none h-full"
        />

        {/* Center — Squares + two big orb buttons */}
        <section className="relative flex-1 flex items-center justify-center overflow-hidden">
          <div className="absolute inset-0 opacity-60 pointer-events-none z-0">
            <Squares
              speed={0.5}
              squareSize={40}
              direction="diagonal"
              borderColor={borderColor}
              hoverFillColor={hoverFillColor}
            />
          </div>

          <div
            className={`relative z-10 flex items-center justify-center transition-all duration-300 ${
              hasCreated ? "gap-10 xl:gap-12" : "gap-16 xl:gap-20"
            }`}
          >
            {/* Join button */}
            <button
              type="button"
              onClick={() => { setShowJoin(true); setFormError(null) }}
              className="relative size-[19rem] xl:size-[21rem] rounded-full cursor-pointer group"
              aria-label="Join classroom"
            >
              <Orb hue={30} rotateOnHover hoverIntensity={0.6} />
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="flex items-center gap-3 text-foreground/95">
                  <LogIn className="size-7 xl:size-8" />
                  <span className="text-xl xl:text-2xl font-medium">Join</span>
                </div>
              </div>
            </button>

            {/* Create button */}
            <button
              type="button"
              onClick={() => { setShowCreate(true); setFormError(null) }}
              className="relative size-[19rem] xl:size-[21rem] rounded-full cursor-pointer group"
              aria-label="Create classroom"
            >
              <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="flex items-center gap-3 text-foreground/95">
                  <Plus className="size-7 xl:size-8" />
                  <span className="text-xl xl:text-2xl font-medium">Create</span>
                </div>
              </div>
            </button>
          </div>
        </section>

        {/* Right Pane — slides in when there are created classrooms */}
        <AnimatePresence mode="wait">
          {hasCreated && (
            <motion.div
              key="right-pane"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className="shrink-0 h-full"
            >
              <RightPane
                classrooms={createdClassrooms.map((c) => c.name)}
                classroomObjects={createdClassrooms}
                onSelect={(_name, index) => {
                  const c = createdClassrooms[index]
                  if (c) navigate(`/classroom/${c.id}`)
                }}
                onExpand={() => triggerExpand("created")}
                className="rounded-none h-full"
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Modal — unified dialog for create & join */}
      <AnimatePresence>
        {(showCreate || showJoin) && (
          <>
            {/* Backdrop */}
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md"
              aria-hidden
              onClick={closeModal}
            />
            {/* Card */}
            <motion.div
              key="card"
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="fixed inset-0 z-40 grid place-items-center p-4"
              role="dialog"
              aria-modal="true"
            >
              <div className="relative w-full max-w-md rounded-2xl border border-border bg-card/70 backdrop-blur-xl shadow-2xl">
                {/* Ambient glow */}
                <div
                  aria-hidden
                  className="pointer-events-none absolute -inset-1 rounded-2xl blur-2xl opacity-40"
                  style={{
                    background:
                      "radial-gradient(60% 40% at 50% 0%, color-mix(in oklab, var(--chart-1), transparent 80%) 0%, transparent 70%)",
                  }}
                />
                <div className="relative p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-medium text-foreground">
                      {showCreate ? "Create Classroom" : "Join Classroom"}
                    </h3>
                    <button
                      type="button"
                      onClick={closeModal}
                      className="p-2 rounded-md border border-border/60 bg-card/60 hover:bg-card/80 cursor-pointer transition-colors"
                      aria-label="Close"
                    >
                      <X className="size-4" />
                    </button>
                  </div>

                  {showCreate ? (
                    <form onSubmit={handleCreateSubmit} className="space-y-4">
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Classroom name</label>
                        <input
                          autoFocus
                          value={createName}
                          onChange={(e) => setCreateName(e.target.value)}
                          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_70%)]"
                          placeholder="e.g. Algebra 101"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Description</label>
                        <textarea
                          value={createDesc}
                          onChange={(e) => setCreateDesc(e.target.value)}
                          rows={3}
                          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-2),transparent_70%)] resize-none"
                          placeholder="Optional details"
                        />
                      </div>
                      <div className="flex items-center justify-end gap-3 pt-2">
                        <button
                          type="button"
                          onClick={closeModal}
                          className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={isSubmitting || !createName.trim()}
                          className="px-4 py-2 rounded-md bg-[color-mix(in_oklab,var(--chart-1),transparent_10%)] text-foreground hover:shadow-[0_0_26px_rgba(99,102,241,0.35)] cursor-pointer disabled:opacity-70 transition-all"
                        >
                          {isSubmitting ? "Creating..." : "Create"}
                        </button>
                      </div>
                      {formError && <p className="text-sm text-destructive/90">{formError}</p>}
                    </form>
                  ) : (
                    <form onSubmit={handleJoinSubmit} className="space-y-4">
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">Classroom code</label>
                        <input
                          autoFocus
                          value={joinCode}
                          onChange={(e) => setJoinCode(e.target.value)}
                          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_70%)]"
                          placeholder="e.g. X1Y2Z3"
                        />
                      </div>
                      <div className="flex items-center justify-end gap-3 pt-2">
                        <button
                          type="button"
                          onClick={closeModal}
                          className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={isSubmitting || !joinCode.trim()}
                          className="px-4 py-2 rounded-md bg-[color-mix(in_oklab,var(--chart-2),transparent_10%)] text-foreground hover:shadow-[0_0_26px_rgba(99,102,241,0.35)] cursor-pointer disabled:opacity-70 transition-all"
                        >
                          {isSubmitting ? "Joining..." : "Join"}
                        </button>
                      </div>
                      {formError && <p className="text-sm text-destructive/90">{formError}</p>}
                    </form>
                  )}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Full-screen expand overlay → navigates after EXPAND_MS */}
      <AnimatePresence>
        {expandingPane && (
          <motion.div
            key={expandingPane}
            initial={{
              width: LEFT_PANE_W,
              x: expandingPane === "created" ? (viewportW || LEFT_PANE_W) - LEFT_PANE_W : 0,
            }}
            animate={{ width: viewportW || LEFT_PANE_W, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: EXPAND_MS / 1000, ease: [0.22, 0.8, 0.3, 0.98] }}
            className="fixed z-40 left-0 bottom-0 bg-background/95 backdrop-blur-2xl pointer-events-none"
            style={{
              top: navH,
              height: `calc(100vh - ${navH}px)`,
              transformOrigin: expandingPane === "joined" ? "left center" : "right center",
            }}
          >
            {expandingPane === "joined" ? (
              <LeftPane
                classrooms={joinedClassrooms.map((c) => c.name)}
                classroomObjects={joinedClassrooms}
                onSelect={(_name, index) => {
                  const c = joinedClassrooms[index]
                  if (c) navigate(`/classroom/${c.id}`)
                }}
                expanded
                showExpandButton={false}
                className="rounded-none h-full"
              />
            ) : (
              <RightPane
                classrooms={createdClassrooms.map((c) => c.name)}
                classroomObjects={createdClassrooms}
                onSelect={(_name, index) => {
                  const c = createdClassrooms[index]
                  if (c) navigate(`/classroom/${c.id}`)
                }}
                expanded
                showExpandButton={false}
                className="rounded-none h-full"
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
