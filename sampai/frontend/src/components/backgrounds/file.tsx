import { useState } from "react"

const darkenColor = (hex: string, percent: number): string => {
  let color = hex.startsWith("#") ? hex.slice(1) : hex
  if (color.length === 3) {
    color = color
      .split("")
      .map((c) => c + c)
      .join("")
  }
  const num = Number.parseInt(color, 16)
  let r = (num >> 16) & 0xff
  let g = (num >> 8) & 0xff
  let b = num & 0xff
  r = Math.max(0, Math.min(255, Math.floor(r * (1 - percent))))
  g = Math.max(0, Math.min(255, Math.floor(g * (1 - percent))))
  b = Math.max(0, Math.min(255, Math.floor(b * (1 - percent))))
  return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1).toUpperCase()
}

interface FileProps {
  color?: string
  size?: number
  items?: React.ReactNode[]
  className?: string
}

const File: React.FC<FileProps> = ({ color = "#3B82F6", size = 1, items = [], className = "" }) => {
  const maxItems = 3
  const papers = items.slice(0, maxItems)
  while (papers.length < maxItems) {
    papers.push(null)
  }

  const [open, setOpen] = useState(false)
  const [paperOffsets, setPaperOffsets] = useState<{ x: number; y: number }[]>(
    Array.from({ length: maxItems }, () => ({ x: 0, y: 0 })),
  )

  const fileMainColor = color
  const fileFoldColor = darkenColor(color, 0.15)
  const paper1 = darkenColor("#ffffff", 0.1)
  const paper2 = darkenColor("#ffffff", 0.05)
  const paper3 = "#ffffff"

  const handleMouseEnter = () => setOpen(true)

  const handleMouseLeave = () => {
    setOpen(false)
    setPaperOffsets(Array.from({ length: maxItems }, () => ({ x: 0, y: 0 })))
  }

  const handlePaperMouseMove = (e: React.MouseEvent<HTMLDivElement, MouseEvent>, index: number) => {
    if (!open) return
    e.stopPropagation()
    const rect = e.currentTarget.getBoundingClientRect()
    const centerX = rect.left + rect.width / 2
    const centerY = rect.top + rect.height / 2
    const offsetX = (e.clientX - centerX) * 0.1
    const offsetY = (e.clientY - centerY) * 0.1
    setPaperOffsets((prev) => {
      const newOffsets = [...prev]
      newOffsets[index] = { x: offsetX, y: offsetY }
      return newOffsets
    })
  }

  const handlePaperMouseLeaveLocal = (_e: React.MouseEvent<HTMLDivElement, MouseEvent>, index: number) => {
    setPaperOffsets((prev) => {
      const newOffsets = [...prev]
      newOffsets[index] = { x: 0, y: 0 }
      return newOffsets
    })
  }

  const scaleStyle = { transform: `scale(${size})`, transformOrigin: "center center" }

  const getOpenTransform = (index: number) => {
    if (index === 0) return "translate(60%, -10%) rotate(15deg)"
    if (index === 1) return "translate(35%, -5%) rotate(7deg)"
    if (index === 2) return "translate(10%, 0%) rotate(2deg)"
    return ""
  }

  return (
    <div style={scaleStyle} className={className}>
      <div
        className={`group relative transition-all duration-300 ease-in-out cursor-pointer ${
          !open ? "hover:-translate-y-2" : ""
        }`}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        style={{ width: "85px", height: "110px" }}
      >
        {papers.map((item, i) => {
          const transformStyle = open
            ? `${getOpenTransform(i)} translate(${paperOffsets[i].x}px, ${paperOffsets[i].y}px)`
            : "translate(0, 0) rotate(0deg)"

          return (
            <div
              key={i}
              onMouseMove={(e) => handlePaperMouseMove(e, i)}
              onMouseLeave={(e) => handlePaperMouseLeaveLocal(e, i)}
              className="absolute top-0 left-0 w-full h-full transition-all duration-500 ease-[cubic-bezier(0.25,1,0.5,1)] border border-black/5 shadow-sm"
              style={{
                backgroundColor: i === 0 ? paper1 : i === 1 ? paper2 : paper3,
                zIndex: open ? 10 + i : 0,
                borderRadius: "8px",
                transform: transformStyle,
                opacity: open ? 1 : 0,
              }}
            >
              <div className="w-full h-full p-2 flex flex-col gap-1 overflow-hidden">
                {!item && (
                  <>
                    <div className="w-[80%] h-1 bg-gray-200 rounded-full mb-1"></div>
                    <div className="w-[100%] h-1 bg-gray-100 rounded-full"></div>
                    <div className="w-[90%] h-1 bg-gray-100 rounded-full"></div>
                    <div className="w-[60%] h-1 bg-gray-100 rounded-full"></div>
                  </>
                )}
                {item}
              </div>
            </div>
          )
        })}

        <div
          className={`absolute inset-0 z-40 transition-all duration-300 ease-in-out shadow-md
            ${open ? "-translate-x-[20%] translate-y-[5%] rotate-[-5deg]" : "group-hover:rotate-[-2deg]"}
          `}
          style={{
            backgroundColor: fileMainColor,
            clipPath: "polygon(0 0, 75% 0, 100% 20%, 100% 100%, 0 100%)",
            borderRadius: "8px 8px 8px 8px",
          }}
        >
          <div className="absolute top-[30%] left-[10%] w-[60%] h-[2px] bg-black/10 rounded-full"></div>
          <div className="absolute top-[40%] left-[10%] w-[80%] h-[2px] bg-black/10 rounded-full"></div>
          <div className="absolute top-[50%] left-[10%] w-[70%] h-[2px] bg-black/10 rounded-full"></div>
        </div>

        <div
          className={`absolute z-50 top-0 right-0 w-[25%] h-[20%] transition-all duration-300 ease-in-out
             ${open ? "-translate-x-[20%] translate-y-[5%] rotate-[-5deg] opacity-0" : "group-hover:opacity-0 group-hover:rotate-[-2deg]"}
             `}
          style={{
            background: fileFoldColor,
            borderRadius: "0 0 0 4px",
          }}
        ></div>

        <div
          className={`absolute inset-0 z-0 bg-black/20 blur-md rounded-lg transition-all duration-300
            ${open ? "opacity-40 translate-y-4 translate-x-4" : "opacity-0"}
            `}
        />
      </div>
    </div>
  )
}

export default File
