import type React from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useState, useEffect, useRef, useCallback } from "react"
import { MessageSquare, FlaskConical, Layers, GitBranch, Users, FolderOpen } from "lucide-react"
import { useTheme } from "@/hooks/use-theme"
import Squares from "@/components/backgrounds/squares"
import { LazyVisual } from "@/components/landingpage/lazy-visual"

export function FeaturesSection() {
  const { theme } = useTheme()
  const [currentFeatureIndex, setCurrentFeatureIndex] = useState(0)
  const [isHoldingSection, setIsHoldingSection] = useState(false)
  const [isHoldingCard, setIsHoldingCard] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const features = [
    {
      icon: MessageSquare,
      title: "RAG-Powered Classroom Chat",
      description:
        "Ask any question about your course and get an answer sourced directly from your uploaded materials — not the internet.",
    },
    {
      icon: FlaskConical,
      title: "Auto-Generated Quizzes",
      description:
        "Multiple-choice and short-answer quizzes generated from individual files or across all classroom materials.",
    },
    {
      icon: Layers,
      title: "Smart Flashcards",
      description:
        "Key concepts and definitions extracted from any uploaded file and turned into ready-to-use flashcards.",
    },
    {
      icon: GitBranch,
      title: "Mind Maps",
      description:
        "Visual concept maps generated from course documents to show how topics and ideas connect to each other.",
    },
    {
      icon: Users,
      title: "Group Chat",
      description:
        "Collaborate with classmates in real time, @mention each other, and discuss course material together.",
    },
    {
      icon: FolderOpen,
      title: "File & Folder Organisation",
      description:
        "Course content is organised into folders, and you interact with each file individually via chat, quizzes, and flashcards.",
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
      <LazyVisual className="absolute inset-0 z-0">
        <Squares
          key={theme}
          direction="diagonal"
          speed={isHoldingSection && !isHoldingCard ? 3 : 0.8}
          borderColor={squareBorderColor}
          squareSize={50}
          hoverFillColor={squareHoverColor}
        />
      </LazyVisual>

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
            Everything You Need to{" "}
            <span className="bg-gradient-to-r from-chart-1 to-chart-2 bg-clip-text text-transparent">
              Study Smarter
            </span>
          </h2>
          <p className="text-lg sm:text-xl text-muted-foreground max-w-3xl mx-auto leading-relaxed">
            All built on your actual course content — every answer, quiz, and flashcard comes from your actual course material.
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
