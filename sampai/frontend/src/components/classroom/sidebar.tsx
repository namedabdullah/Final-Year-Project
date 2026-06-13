import { useState, useEffect, useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { Home, ChevronDown, Folder } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import AnimatedList from "@/components/backgrounds/animated-list"
import { classroomApi } from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import { cn } from "@/lib/utils"
import type { Classroom } from "@/lib/types"

type FileType = {
  id: number
  filename: string
  file_url: string
  file_key?: string
  file_type: string | null
  file_size?: number | null
  processing_status: string
  folder_id?: number
  uploaded_at?: string
  processed_at?: string | null
}

type ClassroomSidebarProps = {
  collapsed: boolean
  currentClassroomId: number
  onHomeClick: () => void
  mode?: "classroom" | "file"
  folderId?: number
  files?: FileType[]
  onFolderClick?: () => void
  onFileSelect?: (fileId: number) => void
  currentFileId?: number
}

export default function ClassroomSidebar({
  collapsed,
  currentClassroomId: _currentClassroomId,
  onHomeClick,
  mode = "classroom",
  files = [],
  onFolderClick,
  onFileSelect,
  currentFileId,
}: ClassroomSidebarProps) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [classrooms, setClassrooms] = useState<Classroom[]>([])
  const [loading, setLoading] = useState(true)
  const [joinedExpanded, setJoinedExpanded] = useState(true)
  const [filesExpanded, setFilesExpanded] = useState(true)

  useEffect(() => {
    if (mode !== "classroom") {
      setLoading(false)
      return
    }
    classroomApi.list()
      .then(setClassrooms)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [mode])

  const joinedClassrooms = useMemo(() => {
    if (!user) return []
    return classrooms.filter((c) => c.owner_id !== user.id)
  }, [classrooms, user])

  const joinedNames = joinedClassrooms.map((c) => c.name)

  const handleClassroomSelect = (_name: string, index: number) => {
    const selected = joinedClassrooms[index]
    if (selected) navigate(`/classroom/${selected.id}`)
  }

  return (
    <motion.aside
      initial={false}
      animate={{ x: collapsed ? -280 : 0, opacity: collapsed ? 0 : 1 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="fixed left-0 top-16 w-[280px] h-[calc(100vh-4rem)] shrink-0 border-r bg-card/70 backdrop-blur-md border-border overflow-hidden flex flex-col z-40"
      style={{ pointerEvents: collapsed ? "none" : "auto" }}
    >
      {/* Home/Folder Button */}
      <div className="relative z-10 px-4 py-4 border-b border-border">
        <button
          type="button"
          onClick={mode === "file" && onFolderClick ? onFolderClick : onHomeClick}
          className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-card/50 cursor-pointer transition-colors w-full"
        >
          {mode === "file" ? (
            <Folder className="size-4 text-foreground" />
          ) : (
            <Home className="size-4 text-foreground" />
          )}
          <span className="text-sm font-medium text-foreground">
            {mode === "file" ? "Folder" : "Home"}
          </span>
        </button>
      </div>

      {mode === "file" ? (
        <div className="relative z-10 flex-1 min-h-0 flex flex-col">
          <button
            type="button"
            onClick={() => setFilesExpanded(!filesExpanded)}
            className="flex items-center justify-between px-4 py-3 border-b border-border hover:bg-card/30 cursor-pointer transition-colors"
          >
            <div className="flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" className="size-4 text-foreground" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M19 6h-6l-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2Zm-7 8H8v-2h4v2Zm3-4H8V8h7v2Z" />
              </svg>
              <span className="text-sm font-medium text-foreground">files</span>
            </div>
            <ChevronDown className={cn("size-4 text-foreground transition-transform", filesExpanded && "rotate-180")} aria-hidden />
          </button>

          <AnimatePresence>
            {filesExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex-1 min-h-0 flex flex-col"
              >
                {files.length === 0 ? (
                  <div className="p-4 text-sm text-muted-foreground text-center">No files in this folder</div>
                ) : (
                  <div className="flex-1 min-h-0">
                    <AnimatedList
                      items={files.map((f) => f.filename)}
                      onItemSelect={(_name, index) => {
                        const selected = files[index]
                        if (selected && onFileSelect) onFileSelect(selected.id)
                      }}
                      className="h-full"
                      itemClassName="border border-border rounded-lg cursor-pointer"
                      displayScrollbar
                      initialSelectedIndex={files.findIndex((f) => f.id === currentFileId)}
                    />
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ) : (
        <div className="relative z-10 flex-1 min-h-0 flex flex-col">
          <button
            type="button"
            onClick={() => setJoinedExpanded(!joinedExpanded)}
            className="flex items-center justify-between px-4 py-3 border-b border-border hover:bg-card/30 cursor-pointer transition-colors"
          >
            <div className="flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" className="size-4 text-foreground" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0Z"></path>
                <path fillRule="evenodd" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 18a7.963 7.963 0 0 1-5.657-2.343A8 8 0 1 1 12 20Z" clipRule="evenodd"></path>
              </svg>
              <span className="text-sm font-medium text-foreground">joined</span>
            </div>
            <ChevronDown className={cn("size-4 text-foreground transition-transform", joinedExpanded && "rotate-180")} aria-hidden />
          </button>

          <AnimatePresence>
            {joinedExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="flex-1 min-h-0 overflow-hidden"
              >
                {loading ? (
                  <div className="p-4 text-sm text-muted-foreground">Loading...</div>
                ) : joinedNames.length === 0 ? (
                  <div className="p-4 text-sm text-muted-foreground text-center">No classrooms joined yet</div>
                ) : (
                  <div className="h-full px-2 py-3 overflow-hidden">
                    <AnimatedList
                      items={joinedNames}
                      onItemSelect={handleClassroomSelect}
                      className="w-full h-full overflow-y-auto"
                      itemClassName="border border-border rounded-lg cursor-pointer"
                      displayScrollbar
                    />
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.aside>
  )
}
