import { Link, useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { useAuth } from '@/stores/auth'
import NotificationBell from '@/components/NotificationBell'
import ThemeToggle from '@/components/theme/theme-toggle'

export default function AppHeader({ crumb }: { crumb?: string }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background/80 px-5 backdrop-blur-xl">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/dashboard" className="flex items-center gap-2 font-semibold text-foreground">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-primary via-[var(--chart-1)] to-[var(--chart-2)] flex items-center justify-center">
            <span className="text-xs font-bold text-primary-foreground">S</span>
          </div>
          <span>SAMpai</span>
        </Link>
        {crumb && <span className="text-muted-foreground/60">/ {crumb}</span>}
      </div>
      <div className="flex items-center gap-2 text-sm text-foreground">
        <NotificationBell />
        <ThemeToggle />
        <span className="text-muted-foreground hidden sm:block">{user?.username}</span>
        <button
          onClick={() => { logout(); navigate('/login') }}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" /> Logout
        </button>
      </div>
    </header>
  )
}
