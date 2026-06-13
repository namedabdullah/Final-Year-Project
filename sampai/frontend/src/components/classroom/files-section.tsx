import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Check, Loader2, Trash2, Upload, X } from "lucide-react"
import { useNavigate } from "react-router-dom"
import File from "@/components/backgrounds/file"
import Orb from "@/components/backgrounds/orb"
import { fileApi } from "@/api/sampai"
import { normalizeErrorDetail } from "@/lib/error-utils"
import { useTheme } from "@/hooks/use-theme"
import { LoadingOrb } from "@/components/ui/liquid-orb-loader"

type FileType = {
  id: number
  filename: string
  file_url: string
  file_key?: string
  file_type: string | null
  file_size: number | null
  processing_status: 'pending' | 'processing' | 'naive_ready' | 'completed' | 'failed'
  folder_id: number
  uploaded_at: string
  processed_at: string | null
}

type FilesSectionProps = {
  classroomId: number
  folderId: number
  isOwner: boolean
  onFileUploaded?: () => void
}

export default function FilesSection({ classroomId, folderId, isOwner, onFileUploaded }: FilesSectionProps) {
  const { theme } = useTheme()
  const navigate = useNavigate()
  const [files, setFiles] = useState<FileType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showLoadingModal, setShowLoadingModal] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadedFileId, setUploadedFileId] = useState<number | null>(null)
  const [processingStatus, setProcessingStatus] = useState<"pending" | "processing" | "naive_ready" | "completed" | "failed">("pending")
  const [processingProgress, setProcessingProgress] = useState(0)
  const [uploadingFileName, setUploadingFileName] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [fileProcessingStatus, setFileProcessingStatus] = useState<Map<number, string>>(new Map())
  const [fileShowTick, setFileShowTick] = useState<Map<number, boolean>>(new Map())

  const fileColor = theme === "dark" ? "#93C5FD" : "#38BDF8"

  const fetchFiles = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fileApi.list(folderId)
      setFiles(data as unknown as FileType[])
      const statusMap = new Map<number, string>()
      data.forEach((f) => statusMap.set(f.id, f.processing_status))
      setFileProcessingStatus(statusMap)

      const processingFiles = data.filter(
        (f) => f.processing_status === "pending" || f.processing_status === "processing" || f.processing_status === "naive_ready"
      )
      if (processingFiles.length > 0 && !uploadedFileId) {
        const pollAll = async () => {
          const stillProcessing: number[] = []
          for (const f of processingFiles) {
            try {
              const statusData = await fileApi.status(f.id)
              setFileProcessingStatus((prev) => new Map(prev).set(f.id, statusData.status))
              if (statusData.status === "completed") {
                setFiles((prev) => prev.map((item) => item.id === f.id ? { ...item, processing_status: "completed" } : item))
                setFileShowTick((prev) => new Map(prev).set(f.id, true))
                setTimeout(() => {
                  setFileShowTick((prev) => { const m = new Map(prev); m.delete(f.id); return m })
                }, 3000)
              } else if (statusData.status === "failed") {
                setFiles((prev) => prev.map((item) => item.id === f.id ? { ...item, processing_status: "failed" } : item))
              } else {
                stillProcessing.push(f.id)
              }
            } catch {
              stillProcessing.push(f.id)
            }
          }
          if (stillProcessing.length === 0 && pollingIntervalRef.current && !uploadedFileId) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
          }
        }
        if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = setInterval(pollAll, 2000)
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(normalizeErrorDetail(detail, "Failed to load files"))
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteFile = async (fileId: number, filename: string) => {
    if (!isOwner) return
    if (!window.confirm(`Delete "${filename}"? This removes the file and its chat history permanently.`)) return
    try {
      await fileApi.remove(fileId)
      setFiles((prev) => prev.filter((f) => f.id !== fileId))
      setFileProcessingStatus((prev) => { const m = new Map(prev); m.delete(fileId); return m })
      setFileShowTick((prev) => { const m = new Map(prev); m.delete(fileId); return m })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(normalizeErrorDetail(detail, "Failed to delete file"))
    }
  }

  useEffect(() => {
    void fetchFiles()
    return () => { if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current) }
  }, [folderId]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const allowed = [".pdf", ".docx", ".pptx", ".txt"]
    const ext = "." + file.name.split(".").pop()?.toLowerCase()
    if (!allowed.includes(ext)) {
      setError(`File type not allowed. Supported: ${allowed.join(", ")}`)
      if (fileInputRef.current) fileInputRef.current.value = ""
      return
    }
    setError(null)
    setUploadingFileName(file.name)
    setShowLoadingModal(true)
    setIsUploading(true)
    setUploadProgress(0)
    setProcessingProgress(0)
    setProcessingStatus("pending")
    await new Promise((r) => setTimeout(r, 100))
    await uploadFile(file)
  }

  const uploadFile = async (file: globalThis.File) => {
    try {
      setUploadProgress(5)
      const response = await fileApi.upload(folderId, file as unknown as File, (pct) => {
        setUploadProgress(Math.max(5, Math.min(90, pct)))
      })
      setUploadProgress(100)
      setUploadedFileId(response.id)
      setProcessingStatus("pending")
      setProcessingProgress(20)
      setIsUploading(false)
      setFiles((prev) => [...prev, { ...response, processing_status: "pending" } as unknown as FileType])
      setFileProcessingStatus((prev) => new Map(prev).set(response.id, "pending"))
      setTimeout(() => {
        setShowLoadingModal(false)
        setUploadProgress(0)
        setUploadingFileName("")
        if (fileInputRef.current) fileInputRef.current.value = ""
      }, 500)
    } catch (err: unknown) {
      setIsUploading(false)
      setUploadProgress(0)
      setProcessingProgress(0)
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(normalizeErrorDetail(detail, "Failed to upload file"))
      setShowLoadingModal(false)
      setUploadingFileName("")
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  useEffect(() => {
    if (!uploadedFileId) return
    if (processingStatus === "completed" || processingStatus === "failed") {
      if (pollingIntervalRef.current) { clearInterval(pollingIntervalRef.current); pollingIntervalRef.current = null }
      return
    }
    const id = setInterval(async () => {
      try {
        const s = await fileApi.status(uploadedFileId)
        setProcessingStatus(s.status as typeof processingStatus)
        setFileProcessingStatus((prev) => new Map(prev).set(uploadedFileId, s.status))
        if (s.status === "pending") setProcessingProgress(20)
        else if (s.status === "processing") setProcessingProgress(50)
        else if (s.status === "naive_ready") setProcessingProgress(70)
        else if (s.status === "completed") {
          setProcessingProgress(100)
          setFiles((prev) => prev.map((f) => f.id === uploadedFileId ? { ...f, processing_status: "completed" } : f))
          setFileShowTick((prev) => new Map(prev).set(uploadedFileId, true))
          setTimeout(() => setFileShowTick((prev) => { const m = new Map(prev); m.delete(uploadedFileId); return m }), 3000)
          setUploadedFileId(null)
          setProcessingStatus("pending")
          onFileUploaded?.()
        } else if (s.status === "failed") {
          setProcessingProgress(0)
          setError("File processing failed. Please try again.")
          setFiles((prev) => prev.map((f) => f.id === uploadedFileId ? { ...f, processing_status: "failed" } : f))
        }
      } catch { /* continue polling */ }
    }, 2000)
    pollingIntervalRef.current = id
    return () => { if (id) clearInterval(id) }
  }, [uploadedFileId, processingStatus]) // eslint-disable-line react-hooks/exhaustive-deps

  const hasFiles = files.length > 0
  const showUploadButton = isOwner

  return (
    <div className="p-4 sm:p-6 md:p-8 pt-36 sm:pt-40 min-h-full w-full overflow-x-hidden">
      <div className="max-w-[1400px] mx-auto w-full">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 min-h-[60vh] gap-4">
            <LoadingOrb size={96} />
            <p className="text-sm text-muted-foreground">Loading files...</p>
          </div>
        ) : !hasFiles && !showUploadButton ? (
          <div className="text-center py-16"><p className="text-muted-foreground">No files yet</p></div>
        ) : !hasFiles && showUploadButton ? (
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className="group flex flex-col items-center gap-6">
              <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.docx,.pptx,.txt" onChange={handleFileSelect} />
              <button type="button" onClick={() => fileInputRef.current?.click()} className="relative size-[160px] rounded-full cursor-pointer" aria-label="Upload file">
                <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                <div className="pointer-events-none absolute inset-0 grid place-items-center">
                  <Upload className="size-12 text-foreground/95" />
                </div>
              </button>
              <p className="text-lg text-foreground text-center font-semibold tracking-wide">Upload File</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 sm:gap-x-8 md:gap-x-10 gap-y-20 sm:gap-y-24">
            {files.map((file) => {
              const status = fileProcessingStatus.get(file.id) ?? file.processing_status
              const isProcessing = status === "pending" || status === "processing"
              const showTick = fileShowTick.get(file.id) ?? false
              return (
                <div
                  key={file.id}
                  className="group flex flex-col items-center transition-opacity duration-300 cursor-pointer"
                  style={{ opacity: isProcessing ? 0.4 : 1 }}
                  onClick={() => navigate(`/classroom/${classroomId}/folder/${folderId}/file/${file.id}`)}
                >
                  <div className="relative flex items-center justify-center w-full h-[150px] mb-2 overflow-visible">
                    <div className="absolute inset-0 blur-2xl bg-gradient-to-br from-chart-1/30 to-chart-2/30 rounded-full pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="relative z-10 flex items-center justify-center">
                      <File color={fileColor} size={1.4} className="cursor-pointer transition-transform" />
                    </div>
                  </div>
                  <div className="flex flex-col items-center gap-1">
                    <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 line-clamp-2 min-h-[2.5rem] flex items-center justify-center mt-1">
                      {file.filename}
                    </p>
                    {isProcessing && <div className="flex items-center justify-center h-3"><Loader2 className="h-3 w-3 animate-spin text-muted-foreground" /></div>}
                    {showTick && (
                      <div className="flex items-center justify-center h-3">
                        <div className="h-3 w-3 rounded-full bg-green-500 flex items-center justify-center">
                          <Check className="h-2 w-2 text-white" />
                        </div>
                      </div>
                    )}
                    {isOwner && (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); void handleDeleteFile(file.id, file.filename) }}
                        className="mt-1 inline-flex items-center justify-center rounded-full border border-border/80 bg-card/80 px-3 py-1.5 text-sm text-destructive hover:bg-card/95 cursor-pointer"
                        aria-label={`Delete ${file.filename}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}

            {showUploadButton && (
              <div className="group flex flex-col items-center">
                <div className="relative flex items-center justify-center w-full h-[150px] mb-2">
                  <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.docx,.pptx,.txt" onChange={handleFileSelect} />
                  <button type="button" onClick={() => fileInputRef.current?.click()} className="relative size-[110px] rounded-full cursor-pointer" aria-label="Upload file">
                    <Orb hue={300} rotateOnHover hoverIntensity={0.6} />
                    <div className="pointer-events-none absolute inset-0 grid place-items-center">
                      <Upload className="size-7 text-foreground/95" />
                    </div>
                  </button>
                </div>
                <p className="text-sm text-foreground text-center font-semibold tracking-wide leading-tight px-2 min-h-[2.5rem] flex items-center justify-center mt-1">Upload File</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Upload Modal */}
      <AnimatePresence>
        {showLoadingModal && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} className="fixed inset-0 z-30 bg-background/50 backdrop-blur-md" aria-hidden />
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
                    <h3 className="text-lg font-medium text-foreground">Uploading File</h3>
                    {uploadProgress >= 100 && (
                      <button type="button" onClick={() => { setShowLoadingModal(false); setUploadProgress(0); setUploadingFileName("") }} className="p-2 rounded-md border border-border/60 bg-card/60 hover:bg-card/80 cursor-pointer" aria-label="Close">
                        <X className="size-4" />
                      </button>
                    )}
                  </div>
                  <div className="space-y-4">
                    {uploadingFileName && (
                      <div className="space-y-2">
                        <label className="text-sm text-muted-foreground">File</label>
                        <div className="w-full rounded-md border border-border bg-background/60 px-3 py-2 text-foreground">{uploadingFileName}</div>
                      </div>
                    )}
                    <div className="space-y-3 pt-2">
                      {uploadProgress < 100 && (
                        <div className="flex flex-col items-center justify-center py-4 gap-3">
                          <LoadingOrb size={64} />
                          <p className="text-sm text-muted-foreground">Uploading file... {uploadProgress}%</p>
                        </div>
                      )}
                      {uploadProgress >= 100 && (processingStatus === "pending" || processingStatus === "processing") && (
                        <div className="flex flex-col items-center justify-center py-4 gap-3">
                          <p className="text-sm text-green-500">✓ File uploaded successfully!</p>
                          <LoadingOrb size={48} />
                          <p className="text-sm text-muted-foreground">Processing file... {processingProgress}%</p>
                        </div>
                      )}
                      {uploadProgress >= 100 && processingStatus === "naive_ready" && (
                        <div className="flex flex-col items-center justify-center py-4 gap-3">
                          <p className="text-sm text-green-500">✓ Chat ready! Full analysis still loading...</p>
                          <LoadingOrb size={48} />
                          <p className="text-sm text-muted-foreground">Building knowledge graph... {processingProgress}%</p>
                        </div>
                      )}
                      {uploadProgress >= 100 && processingStatus === "completed" && (
                        <div className="flex items-center justify-center gap-2 text-sm text-green-500 py-4">
                          ✓ File uploaded and processed successfully!
                        </div>
                      )}
                    </div>
                    {error && <p className="text-sm text-destructive/90">{error}</p>}
                    {uploadProgress < 100 && (
                      <div className="flex items-center justify-end gap-3 pt-2">
                        <button
                          type="button"
                          onClick={() => {
                            if (pollingIntervalRef.current) { clearInterval(pollingIntervalRef.current); pollingIntervalRef.current = null }
                            setShowLoadingModal(false); setUploadProgress(0); setProcessingProgress(0); setUploadedFileId(null); setProcessingStatus("pending"); setUploadingFileName("")
                            if (fileInputRef.current) fileInputRef.current.value = ""
                          }}
                          className="px-4 py-2 rounded-md border border-border bg-card/50 hover:bg-card/70 cursor-pointer"
                          disabled={isUploading}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
