import { Navbar } from "@/components/landingpage/navbar"
import { HeroSection } from "@/components/landingpage/hero-section"
import { ProblemSection } from "@/components/landingpage/problem-section"
import { SolutionSection } from "@/components/landingpage/solution-section"
import { FeaturesSection } from "@/components/landingpage/features-section"
import { TeacherSection } from "@/components/landingpage/teacher-section"
import { HowItWorksSection } from "@/components/landingpage/how-it-works-section"
import { CTASection } from "@/components/landingpage/cta-section"
import { Footer } from "@/components/landingpage/footer"

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground overflow-x-hidden">
      <Navbar variant="full" />
      <main>
        <HeroSection />
        <ProblemSection />
        <SolutionSection />
        <FeaturesSection />
        <TeacherSection />
        <HowItWorksSection />
        <CTASection />
      </main>
      <Footer />
    </div>
  )
}
