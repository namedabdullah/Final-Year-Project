import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Plus, X, Trash2 } from "lucide-react"
import Folder from "@/components/backgrounds/folder"
import Orb from "@/components/backgrounds/orb"
import { folderApi } from "@/api/sampai"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"

type FolderType = {
  id: number
  name: string
  files?: unknown[]
}

type FoldersSectionProps = {
  classroomId: number
  isOwner: boolean
  onFolderCreated?: () => void
}

export default function FoldersSection({ classroomId, isOwner, onFolderCreated }: FoldersSectionProps) {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const [folders, setFolders] = useState<FolderType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showCreateModal, setShowCreateModal] = useState(false)
  const [folderName, setFolderName] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  const [deletingFolder, setDeletingFolder] = useState<FolderType | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const folderColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  const fetchFolders = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await folderApi.list(classroomId)
      setFolders(data as FolderType[])
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(normalizeErrorDetail(detail, "Failed to load folders"))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void fetchFolders() }, [classroomId]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreateFolder = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = folderName.trim()
    if (!name || isSubmitting) return
    setIsSubmitting(true)
    setError(null)
    try {
      await folderApi.create(classroomId, name)
      setFolderName("")
      setShowCreateModal(false)
      await fetchFolders()
      onFolderCreated?.()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(normalizeErrorDetail(detail, "Failed to create folder"))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteFolder = async (folderId: number) => {
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await folderApi.remove(folderId)
      setFolders((prev) => prev.filter((f) => f.id !== folderId))
      setDeletingFolder(null)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setDeleteError(normalizeErrorDetail(detail, "Failed to delete folder"))
    } finally {
      setIsDeleting(false)
    }
  }

  const hasFolders = folders.length > 0
  const showCreateButton = isOwner

  return (
    <div className="p-4 sm:p-6 md:p-8 pt-20 sm:pt-24 md:pt-28 w-full overflow-x-hidden">
      <div className="max-w-[1400px] mx-auto w-full">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 min-h-[60vh] gap-4">
            <LoadingOrb size={96} />
            <p className="text-sm text-muted-foreground">Loading folders...</p>
          </div>
        ) : !hasFolders && !showCreateButton ? (
          <div className="text-center py-16">
            <p className="text-muted-foreground">No folders yet</p>
          </div>
        ) : !hasFolders && showCreateButton ? (
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className="group flex flex-col items-center gap-6">
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="relative size-[160px] rounded-full cursor-pointer"
                aria-label="Create folder"
              >
                <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                <div className="pointer-events-none absolute inset-0 grid place-items-center">
                  <Plus className="size-12 text-foreground/95" />
                </div>
              </button>
              <p className="text-lg text-foreground text-center font-semibold tracking-wide">Create Folder</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 sm:gap-x-8 md:gap-x-10 gap-y-20 sm:gap-y-24">
            {folders.map((folder) => (
              <div
                key={folder.id}
                className="group relative flex flex-col items-center cursor-pointer"
                onClick={() => navigate(`/classroom/${classroomId}/folder/${folder.id}`)}
              >
                {isOwner && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setDeletingFolder(folder)
                      setDeleteError(null)
                    }}
                    className="absolute top-0 right-2 z-30 opacity-0 group-hover:opacity-100 transition-opacity w-8 h-8 rounded-full flex items-center justify-center bg-card/70 backdrop-blur-sm border border-border/40 text-muted-foreground/60 hover:text-destructive hover:border-destructive/40 hover:bg-destructive/10 cursor-pointer"
                    title="Delete folder"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
                <div className="relative flex items-center justify-center w-full h-[150px] mb-2 overflow-visible">
                  <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-chart-1/30 to-chart-2/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="relative z-10 flex items-center justify-center">
                    <Folder color={folderColor} size={1.4} description="" showPapers className="cursor-pointer transition-transform" />
                  </div>
                </div>
                <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 line-clamp-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                  {folder.name}
                </p>
              </div>
            ))}

            {showCreateButton && (
              <div className="group flex flex-col items-center">
                <div className="relative flex items-center justify-center w-full h-[150px] mb-2">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(true)}
                    className="relative size-[110px] rounded-full cursor-pointer"
                    aria-label="Create folder"
                  >
                    <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                    <div className="pointer-events-none absolute inset-0 grid place-items-center">
                      <Plus className="size-7 text-foreground/95" />
                    </div>
                  </button>
                </div>
                <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                  Create Folder
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {showCreateModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md"
              aria-hidden
              onClick={() => setShowCreateModal(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="fixed inset-0 z-40 grid place-items-center p-4"
              role="dialog"
              aria-modal="true"
            >
              <div className="relative w-full max-w-md rounded-2xl border border-border bg-card/70 backdrop-blur-xl shadow-2xl">
                <div className="relative p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-medium text-foreground">Create Folder</h3>
                    <button
                      type="button"
                      onClick={() => setShowCreateModal(false)}
                      className="p-2 rounded-md border border-border/60 bg-card/60 hover:bg-card/80 cursor-pointer"
                      aria-label="Close"
                    >
                      <X className="size-4" />
                    </button>
                  </div>
                  <form onSubmit={handleCreateFolder} className="space-y-4">
                    <div className="space-y-2">
                      <label className="text-sm text-muted-foreground">Folder name</label>
                      <input
                        value={folderName}
                        onChange={(e) => setFolderName(e.target.value)}
                        className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-[color-mix(in_oklab,var(--chart-1),transparent_70%)]"
                        placeholder="e.g. Lecture Notes"
                        autoFocus
                      />
                    </div>
                    {error && <p className="text-sm text-destructive/90">{error}</p>}
                    <div className="flex items-center justify-end gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => setShowCreateModal(false)}
                        className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-2 rounded-md bg-[color-mix(in_oklab,var(--chart-1),transparent_10%)] text-foreground hover:shadow-[0_0_26px_rgba(99,102,241,0.35)] cursor-pointer disabled:opacity-70"
                        disabled={isSubmitting || !folderName.trim()}
                      >
                        {isSubmitting ? "Creating..." : "Create"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Delete Confirmation Modal */}
      <AnimatePresence>
        {deletingFolder && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md"
              aria-hidden
              onClick={() => { setDeletingFolder(null); setDeleteError(null) }}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="fixed inset-0 z-40 grid place-items-center p-4"
              role="dialog"
              aria-modal="true"
            >
              <div className="w-full max-w-sm rounded-2xl border border-destructive/30 bg-card/80 backdrop-blur-xl shadow-2xl p-6 space-y-4">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex-none w-9 h-9 rounded-full flex items-center justify-center bg-destructive/10 border border-destructive/30">
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-base font-semibold text-foreground">Delete &ldquo;{deletingFolder.name}&rdquo;?</h3>
                    <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                      This will permanently delete this folder and all files inside it. This cannot be undone.
                    </p>
                  </div>
                </div>
                {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
                <div className="flex gap-3 justify-end pt-1">
                  <button
                    type="button"
                    onClick={() => { setDeletingFolder(null); setDeleteError(null) }}
                    disabled={isDeleting}
                    className="px-4 py-2 rounded-xl border border-border/60 bg-card/50 hover:bg-card/70 text-sm text-foreground cursor-pointer disabled:opacity-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteFolder(deletingFolder.id)}
                    disabled={isDeleting}
                    className="px-4 py-2 rounded-xl bg-destructive/80 hover:bg-destructive text-white text-sm font-medium cursor-pointer disabled:opacity-50 transition-colors"
                  >
                    {isDeleting ? "Deleting…" : "Delete folder"}
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
