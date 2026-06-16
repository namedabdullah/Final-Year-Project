import { motion } from "framer-motion"
import { AlertCircle, TrendingDown, Clock } from "lucide-react"
import { useRef } from "react"
import { useInView } from "framer-motion"
import { useTheme } from "@/hooks/use-theme"
import Squares from "@/components/backgrounds/squares"
import ElectricBorder from "@/components/backgrounds/electric-border"
import { LazyVisual } from "@/components/landingpage/lazy-visual"

export function ProblemSection() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })
  const { theme } = useTheme()

  const problems = [
    {
      icon: AlertCircle,
      title: "Generic AI Answers",
      description: "ChatGPT and search engines answer from the internet, not from your actual course material",
    },
    {
      icon: Clock,
      title: "Scattered Study Material",
      description: "Lecture slides, notes, and readings live in different places with no unified way to query them",
    },
    {
      icon: TrendingDown,
      title: "Passive Reading",
      description: "Reading PDFs and slides alone doesn't reinforce understanding — students need active recall tools",
    },
  ]

  const borderColor = theme === "dark" ? "rgba(124,58,237,0.15)" : "rgba(99,102,241,0.12)"
  const hoverColor = theme === "dark" ? "rgba(124,58,237,0.08)" : "rgba(99,102,241,0.06)"
  const electricColor = theme === "dark" ? "#7c3aed" : "#6366f1"

  return (
    <section ref={ref} className="relative py-20 sm:py-32 overflow-hidden">
      <LazyVisual className="absolute inset-0 opacity-20">
        <Squares
          direction="diagonal"
          speed={0.4}
          borderColor={borderColor}
          squareSize={60}
          hoverFillColor={hoverColor}
        />
      </LazyVisual>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6">
            The Problem with <span className="text-muted-foreground line-through">Generic</span> AI Study Tools
          </h2>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed">
            Existing tools don't know what your course actually covers. They answer from the internet — not from
            the slides, notes, and readings your course is actually built on.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8 max-w-6xl mx-auto">
          {problems.map((problem, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.6, delay: index * 0.1 }}
              className="relative group"
            >
              <ElectricBorder
                color={electricColor}
                speed={1.2}
                chaos={0.8}
                thickness={2}
                style={{ borderRadius: "1rem" }}
              >
                <div className="relative p-8 rounded-2xl bg-card/80 backdrop-blur-sm h-full">
                  <div className="w-12 h-12 rounded-xl bg-destructive/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <problem.icon className="w-6 h-6 text-destructive" />
                  </div>
                  <h3 className="text-xl font-semibold mb-3">{problem.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">{problem.description}</p>
                </div>
              </ElectricBorder>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
