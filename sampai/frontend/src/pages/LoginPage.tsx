import Threads from '@/components/backgrounds/threads'
import { AuthCard } from '@/components/auth/auth-card'

export default function LoginPage() {
  return (
    <div className="relative min-h-screen w-full flex items-center justify-center overflow-hidden bg-background">
      <div className="absolute inset-0 z-0">
        <Threads
          color={[0.35, 0.25, 0.75]}
          amplitude={1.2}
          distance={0.3}
          enableMouseInteraction
        />
      </div>
      <div className="relative z-10 w-full max-w-md px-4">
        <AuthCard initialMode="login" />
      </div>
    </div>
  )
}
