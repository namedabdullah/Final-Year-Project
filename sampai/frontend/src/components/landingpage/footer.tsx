import { Globe, Users, Mail } from "lucide-react"

export function Footer() {
  return (
    <footer className="relative border-t border-border/50 bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          <div className="col-span-1 md:col-span-2">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary via-chart-1 to-chart-2 flex items-center justify-center">
                <span className="text-lg font-bold text-primary-foreground">S</span>
              </div>
              <span className="text-lg font-bold">The Learning SAMpai</span>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed max-w-md">
              A classroom platform that turns your course materials into instant, AI-powered answers
              grounded in actual course content — powered by LightRAG.
            </p>
          </div>

          <div>
            <h3 className="font-semibold mb-4">Navigation</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>
                <a href="#features" className="hover:text-foreground transition-colors">
                  Features
                </a>
              </li>
              <li>
                <a href="#capabilities" className="hover:text-foreground transition-colors">
                  Capabilities
                </a>
              </li>
              <li>
                <a href="#how-it-works" className="hover:text-foreground transition-colors">
                  How It Works
                </a>
              </li>
              <li>
                <a href="#cta" className="hover:text-foreground transition-colors">
                  Get Started
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="font-semibold mb-4">Built With</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>LightRAG</li>
              <li>Neo4j</li>
              <li>Qdrant</li>
              <li>React + Vite</li>
            </ul>
          </div>
        </div>

        <div className="pt-8 border-t border-border/50 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">© 2026 The Learning SAMpai. Final Year Project.</p>
          <div className="flex items-center space-x-4">
            <a href="#" className="text-muted-foreground hover:text-foreground transition-colors" aria-label="GitHub">
              <Globe className="w-5 h-5" />
            </a>
            <a href="#" className="text-muted-foreground hover:text-foreground transition-colors" aria-label="LinkedIn">
              <Users className="w-5 h-5" />
            </a>
            <a href="#" className="text-muted-foreground hover:text-foreground transition-colors" aria-label="Email">
              <Mail className="w-5 h-5" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
