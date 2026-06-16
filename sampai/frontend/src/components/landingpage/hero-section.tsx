import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { motion } from "framer-motion"
import { ArrowRight, Sparkles } from "lucide-react"
import { useTheme } from "@/hooks/use-theme"
import Threads from "@/components/backgrounds/threads"
import { LazyVisual } from "@/components/landingpage/lazy-visual"

export function HeroSection() {
  const { theme } = useTheme()
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      <LazyVisual eager className="absolute inset-0 z-0">
        <Threads key={theme} color={[0.3, 0.6, 1]} amplitude={1.2} distance={0.3} enableMouseInteraction={true} />
      </LazyVisual>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10 pt-20">
        <div className="max-w-5xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-8"
          >
            <Sparkles className="w-4 h-4 text-chart-1" />
            <span className="text-sm font-medium text-foreground/80">Built on LightRAG · Graph-Based RAG</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1, ease: "easeOut" }}
            className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold mb-6 leading-tight"
          >
            Your Course Material.{" "}
            <span className="bg-gradient-to-r from-chart-1 via-chart-2 to-chart-1 bg-clip-text text-transparent">
              Answered Instantly.
            </span>
            <br />
            Grounded in What You Actually Study.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
            className="text-lg sm:text-xl text-muted-foreground mb-10 max-w-3xl mx-auto leading-relaxed"
          >
            The Learning SAMpai is a classroom platform that turns your course materials into instant,
            AI-powered answers — grounded in the actual uploaded content, not the internet.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3, ease: "easeOut" }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4"
          >
            <Link to="/signup">
              <Button
                size="lg"
                className="text-base px-8 py-6 cursor-pointer bg-gradient-to-r from-chart-1 to-chart-2 hover:opacity-90 transition-all duration-300 group"
              >
                Get Started Free
                <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
            <a href="#how-it-works">
              <Button
                size="lg"
                variant="outline"
                className="text-base px-8 py-6 cursor-pointer border-2 hover:bg-accent transition-all duration-300 bg-transparent"
              >
                See How It Works
              </Button>
            </a>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.5 }}
            className="mt-16 text-sm text-muted-foreground"
          >
            Powered by LightRAG · Neo4j · Qdrant · Redis
          </motion.div>
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-background to-transparent z-[5]" />
    </section>
  )
}
