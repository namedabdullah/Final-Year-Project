import type React from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useState, useEffect, useRef, useCallback } from "react"
import { Route, MessageSquare, FlaskConical, FileCheck, Trophy, Users, AlertTriangle, Clock } from "lucide-react"
import { useTheme } from "@/hooks/use-theme"
import Squares from "@/components/backgrounds/squares"

export function FeaturesSection() {
  const { theme } = useTheme()
  const [currentFeatureIndex, setCurrentFeatureIndex] = useState(0)
  const [isHoldingSection, setIsHoldingSection] = useState(false)
  const [isHoldingCard, setIsHoldingCard] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const features = [
    {
      icon: Route,
      title: "Personalized Learning Pathways",
      description:
        "AI dynamically adjusts lesson sequences based on performance, bringing in simpler explanations when needed.",
    },
    {
      icon: MessageSquare,
      title: "Context-Aware Explanations",
      description: "Adaptive answers that explain step-by-step and switch between summary, in-depth, or visual modes.",
    },
    {
      icon: FlaskConical,
      title: "Adaptive Practice & Quizzing",
      description: "Generates new questions each time, adjusting difficulty automatically with hints and solutions.",
    },
    {
      icon: FileCheck,
      title: "AI Feedback on Student Work",
      description: "Upload code, essays, or solutions. AI evaluates, points out errors, and suggests improvements.",
    },
    {
      icon: Trophy,
      title: "Gamified Progress Dashboard",
      description: "Earn badges, streaks, and levels. AI recommends challenges based on recent activity.",
    },
    {
      icon: Users,
      title: "Peer + AI Hybrid Study Rooms",
      description: "Collaborate in real-time with AI moderation, summaries, and follow-up suggestions.",
    },
    {
      icon: AlertTriangle,
      title: "Error-Aware Practice Mode",
      description: "AI intervenes at the exact point of error, explaining what went wrong for better understanding.",
    },
    {
      icon: Clock,
      title: "Micro-Learning & Smart Reminders",
      description: 'Breaks lessons into daily goals with reminders like "You struggled with recursion yesterday."',
    },
  ]

  useEffect(() => {
    if (isHoldingCard) return

    const interval = isHoldingSection ? 1800 : 4000

    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    if (isHoldingSection) {
      const timeout = setTimeout(() => {
        setCurrentFeatureIndex((prev) => (prev + 1) % features.length)
        intervalRef.current = setInterval(() => {
          setCurrentFeatureIndex((prev) => (prev + 1) % features.length)
        }, interval)
      }, 50)
      return () => {
        clearTimeout(timeout)
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    }

    intervalRef.current = setInterval(() => {
      setCurrentFeatureIndex((prev) => (prev + 1) % features.length)
    }, interval)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [isHoldingSection, isHoldingCard, features.length])

  const handleSectionMouseDown = useCallback(() => {
    setIsHoldingSection(true)
  }, [])

  const handleSectionMouseUp = useCallback(() => {
    setIsHoldingSection(false)
  }, [])

  const handleCardMouseDown = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.stopPropagation()
    setIsHoldingCard(true)
  }, [])

  const handleCardMouseUp = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.stopPropagation()
    setIsHoldingCard(false)
  }, [])

  const squareBorderColor = theme === "dark" ? "rgba(99,102,241,0.15)" : "rgba(99,102,241,0.1)"
  const squareHoverColor = theme === "dark" ? "rgba(99,102,241,0.08)" : "rgba(99,102,241,0.05)"

  const currentFeature = features[currentFeatureIndex]
  const isLeftSide = currentFeatureIndex % 2 === 0
  const animDuration = isHoldingSection ? 0.27 : 0.6

  return (
    <section
      id="features"
      className="relative py-20 sm:py-32 overflow-hidden cursor-pointer select-none"
      onMouseDown={handleSectionMouseDown}
      onMouseUp={handleSectionMouseUp}
      onMouseLeave={handleSectionMouseUp}
      onTouchStart={handleSectionMouseDown}
      onTouchEnd={handleSectionMouseUp}
    >
      <div className="absolute inset-0 z-0">
        <Squares
          key={theme}
          direction="diagonal"
          speed={isHoldingSection && !isHoldingCard ? 3 : 0.8}
          borderColor={squareBorderColor}
          squareSize={50}
          hoverFillColor={squareHoverColor}
        />
      </div>

      <div className="absolute inset-0 z-[1] pointer-events-none bg-gradient-to-b from-background/80 via-background/60 to-background/80" />

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6">
            Powerful Features for{" "}
            <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">
              Every Learner
            </span>
          </h2>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed">
            Experience learning that adapts to you, not the other way around.
          </p>
          <p className="text-sm text-muted-foreground mt-4 opacity-70">
            {isHoldingSection
              ? "⚡ Speed Mode Active"
              : isHoldingCard
                ? "⏸ Paused"
                : "Hold to speed up • Click cards to pause"}
          </p>
        </motion.div>

        <div className="relative min-h-[400px] max-w-6xl mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentFeatureIndex}
              initial={{
                opacity: 0,
                x: isLeftSide ? -100 : 100,
                scale: 0.9,
              }}
              animate={{
                opacity: 1,
                x: 0,
                scale: 1,
              }}
              exit={{
                opacity: 0,
                x: isLeftSide ? 100 : -100,
                scale: 0.9,
              }}
              transition={{
                duration: animDuration,
                ease: "easeInOut",
              }}
              className={`absolute inset-0 flex items-center ${isLeftSide ? "justify-start" : "justify-end"}`}
            >
              <motion.div
                className={`w-full max-w-md ${isLeftSide ? "ml-0 md:ml-8" : "mr-0 md:mr-8"}`}
                onMouseDown={handleCardMouseDown}
                onMouseUp={handleCardMouseUp}
                onMouseLeave={handleCardMouseUp}
                onTouchStart={handleCardMouseDown}
                onTouchEnd={handleCardMouseUp}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.98 }}
              >
                <div className="relative p-8 rounded-3xl bg-card/90 backdrop-blur-xl border-2 border-primary/30 shadow-2xl hover:shadow-primary/20 transition-all duration-300">
                  <div className="absolute inset-0 rounded-3xl bg-gradient-to-br from-chart-1/20 to-chart-2/20 -z-10 blur-xl" />

                  <div className="flex items-start gap-4 mb-4">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-chart-1 to-chart-2 flex items-center justify-center flex-shrink-0 shadow-lg">
                      <currentFeature.icon className="w-8 h-8 text-white" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-2xl font-bold mb-2">{currentFeature.title}</h3>
                      <div className="text-sm font-medium text-muted-foreground mb-2">
                        Feature {currentFeatureIndex + 1} of {features.length}
                      </div>
                    </div>
                  </div>

                  <p className="text-base text-muted-foreground leading-relaxed">{currentFeature.description}</p>

                  <div className="mt-6 flex gap-1.5">
                    {features.map((_, index) => (
                      <div
                        key={index}
                        className={`h-1.5 rounded-full transition-all duration-300 ${
                          index === currentFeatureIndex
                            ? "bg-gradient-to-r from-chart-1 to-chart-2 flex-1"
                            : "bg-muted flex-1"
                        }`}
                      />
                    ))}
                  </div>
                </div>
              </motion.div>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </section>
  )
}
