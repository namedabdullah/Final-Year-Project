import { motion, useInView } from "framer-motion"
import { useRef, useState, useEffect } from "react"
import { BookOpen, Upload, FlaskConical, Layers, GitBranch, Megaphone, FolderOpen } from "lucide-react"
import { useTheme } from "@/hooks/use-theme"
import Stack from "@/components/backgrounds/stack"
import Plasma from "@/components/backgrounds/plasma"
import { LazyVisual } from "@/components/landingpage/lazy-visual"

export function TeacherSection() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })
  const { theme } = useTheme()
  const [cardDims, setCardDims] = useState<{ width: number; height: number }>({ width: 480, height: 300 })

  useEffect(() => {
    const update = () => {
      const w = window.innerWidth
      if (w < 380) setCardDims({ width: 300, height: 200 })
      else if (w < 640) setCardDims({ width: 340, height: 220 })
      else if (w < 768) setCardDims({ width: 400, height: 260 })
      else setCardDims({ width: 480, height: 300 })
    }
    update()
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [])

  const capabilityCards = [
    {
      id: 1,
      title: "Classroom Spaces",
      subtitle: "Organised per course",
      details:
        "Content is grouped into classroom spaces with invite-based access, so every course's material stays in one place and relevant to the people enrolled.",
      icon: BookOpen,
    },
    {
      id: 2,
      title: "Document Ingestion",
      subtitle: "PDF, DOCX, PPTX, XLSX",
      details:
        "Uploaded files are parsed and indexed into a knowledge graph by SAMpai — making every page instantly queryable instead of sitting unread in a folder.",
      icon: Upload,
    },
    {
      id: 3,
      title: "Quiz Generation",
      subtitle: "MCQ & short-answer",
      details:
        "Multiple-choice quizzes are generated from a single file, or cross-file short-answer quizzes that draw on everything uploaded to the classroom.",
      icon: FlaskConical,
    },
    {
      id: 4,
      title: "Flashcard Generation",
      subtitle: "Key concepts, auto-extracted",
      details:
        "Key terms, definitions, and concepts are pulled from any uploaded file and turned into ready-to-use flashcards — no manual work involved.",
      icon: Layers,
    },
    {
      id: 5,
      title: "Mind Map Generation",
      subtitle: "Visual concept maps",
      details:
        "A visual map shows how topics in a document connect, making relationships between concepts easy to see and the big picture easy to grasp.",
      icon: GitBranch,
    },
    {
      id: 6,
      title: "Announcements",
      subtitle: "Broadcast to the class",
      details:
        "Updates posted to a classroom are visible to everyone enrolled — deadlines, reminders, and important notices all in one place.",
      icon: Megaphone,
    },
    {
      id: 7,
      title: "Folder Organisation",
      subtitle: "Structure course content",
      details:
        "Files are grouped into topic folders, with folder-level quizzes that span every file inside for broader, mixed practice.",
      icon: FolderOpen,
    },
  ]

  const plasmaColor = theme === "dark" ? "#60a5fa" : "#3b82f6"

  return (
    <section id="capabilities" ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
      <LazyVisual className="absolute inset-0 -z-10 opacity-80">
        <Plasma
          key={theme}
          color={plasmaColor}
          speed={0.6}
          direction="forward"
          scale={1.08}
          opacity={0.6}
          mouseInteractive={false}
        />
      </LazyVisual>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
          className="text-center mb-14"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6 text-balance">
            What{" "}
            <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">SAMpai</span>{" "}
            Can Do
          </h2>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed text-pretty">
            Course material goes in once. SAMpai turns it into quizzes, flashcards, mind maps, and a classroom chat — every output grounded in the uploaded content.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={isInView ? { opacity: 1, scale: 1 } : {}}
          transition={{ duration: 0.7 }}
          className="flex justify-center items-center px-2"
        >
          <div className="relative">
            <Stack
              cardsData={capabilityCards}
              cardDimensions={cardDims}
              randomRotation={true}
              sensitivity={160}
              sendToBackOnClick={false}
              contentVariant="teacher"
            />
          </div>
        </motion.div>
      </div>
    </section>
  )
}
