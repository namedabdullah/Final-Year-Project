import React, { useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { AnimatePresence, motion } from "framer-motion"
import { Check, Eye, EyeOff, X } from "lucide-react"
import { authApi } from "@/api/sampai"
import { useAuth } from "@/stores/auth"
import { PixelCorruptionOverlay, type PixelTransitionHandle } from "@/components/ui/pixel-transition"
import { LoadingOverlay } from "@/components/ui/liquid-orb-loader"

// ── Password rule helper ─────────────────────────────────────────────────────

interface RuleItemProps {
  ok: boolean
  label: string
}

function RuleItem({ ok, label }: RuleItemProps) {
  return (
    <li className={`flex items-center gap-1.5 text-xs transition-colors ${ok ? "text-emerald-400" : "text-muted-foreground"}`}>
      {ok ? <Check className="h-3 w-3 shrink-0" /> : <X className="h-3 w-3 shrink-0" />}
      {label}
    </li>
  )
}

// ── AuthCard ─────────────────────────────────────────────────────────────────

interface AuthCardProps {
  initialMode?: "login" | "signup"
}

export function AuthCard({ initialMode = "login" }: AuthCardProps) {
  const navigate = useNavigate()
  const setAuth = useAuth((s) => s.setAuth)
  const overlayRef = useRef<PixelTransitionHandle>(null)

  const [mode, setMode] = useState<"login" | "signup">(initialMode)
  const [loading, setLoading] = useState(false)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [message, setMessage] = useState<string | null>(null)

  // ── Login fields
  const [loginEmail, setLoginEmail] = useState("")
  const [loginPassword, setLoginPassword] = useState("")
  const [showLoginPassword, setShowLoginPassword] = useState(false)

  // ── Signup fields
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  // ── Password rules
  const rules = {
    length: password.length >= 8,
    letter: /[A-Za-z]/.test(password),
    number: /\d/.test(password),
    match: confirmPassword.length > 0 && password === confirmPassword,
    username: /^[a-zA-Z0-9_-]{3,50}$/.test(username),
  }
  const canSignUp =
    Object.values(rules).every(Boolean) && /\S+@\S+\.\S+/.test(email)
  const canLogin = loginEmail.length > 0 && loginPassword.length > 0

  // ── Pixel-transition swipe between modes
  const triggerSwipe = async (target: "login" | "signup") => {
    if (loading) return
    setMessage(null)
    await overlayRef.current?.run(() => {
      setMode(target)
      navigate(target === "login" ? "/login" : "/signup")
    })
  }

  // ── Signup submit
  const onSubmitSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSignUp || loading) return
    setLoading(true)
    setLoadingProgress(0)
    setMessage(null)
    const interval = setInterval(() => {
      setLoadingProgress((p) => (p >= 90 ? p : p + Math.random() * 10))
    }, 100)
    try {
      setLoadingProgress(30)
      await authApi.signup({ username, email, password })
      setLoadingProgress(70)
      setMessage("Signup successful! Redirecting to login...")
      setLoadingProgress(90)
      await overlayRef.current?.run(() => {
        setMode("login")
        navigate("/login")
      })
      setLoadingProgress(100)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setMessage(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ")
          : "Signup failed. Please try again.",
      )
    } finally {
      clearInterval(interval)
      setLoading(false)
      setTimeout(() => setLoadingProgress(0), 500)
    }
  }

  // ── Login submit
  const onSubmitLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canLogin || loading) return
    setLoading(true)
    setLoadingProgress(0)
    setMessage(null)
    const interval = setInterval(() => {
      setLoadingProgress((p) => (p >= 90 ? p : p + Math.random() * 10))
    }, 100)
    try {
      setLoadingProgress(30)
      const res = await authApi.login({ email: loginEmail, password: loginPassword })
      setLoadingProgress(70)
      setAuth(res.access_token, res.user)
      setLoadingProgress(90)
      setMessage("Login successful! Redirecting...")
      setLoadingProgress(100)
      navigate("/dashboard")
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setMessage(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ")
          : "Login failed. Check your credentials.",
      )
    } finally {
      clearInterval(interval)
      setLoading(false)
      setTimeout(() => setLoadingProgress(0), 500)
    }
  }

  return (
    <div className="relative w-full rounded-2xl border border-border bg-card/80 backdrop-blur-md shadow-2xl overflow-hidden">
      {/* Pixel transition overlay */}
      <PixelCorruptionOverlay ref={overlayRef} gridSize={32} animationStepDuration={0.6} />

      {/* Loading overlay */}
      <LoadingOverlay
        visible={loading}
        progress={loadingProgress}
        message={loading ? "Please wait..." : undefined}
      />

      <div className="p-8">
        {/* Header tabs */}
        <div className="flex gap-1 mb-8 p-1 rounded-xl bg-muted">
          <button
            type="button"
            onClick={() => mode !== "login" && triggerSwipe("login")}
            className={`flex-1 rounded-lg py-2 text-sm font-medium transition-all ${
              mode === "login"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Log in
          </button>
          <button
            type="button"
            onClick={() => mode !== "signup" && triggerSwipe("signup")}
            className={`flex-1 rounded-lg py-2 text-sm font-medium transition-all ${
              mode === "signup"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Sign up
          </button>
        </div>

        {/* Forms */}
        <AnimatePresence mode="wait">
          {mode === "login" ? (
            <motion.form
              key="login"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              onSubmit={onSubmitLogin}
              className="space-y-4"
            >
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                    Email
                  </label>
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    required
                    className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      type={showLoginPassword ? "text" : "password"}
                      autoComplete="current-password"
                      placeholder="••••••••"
                      value={loginPassword}
                      onChange={(e) => setLoginPassword(e.target.value)}
                      required
                      className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                    <button
                      type="button"
                      onClick={() => setShowLoginPassword((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      tabIndex={-1}
                    >
                      {showLoginPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {message && (
                <p className={`text-xs px-3 py-2 rounded-lg ${
                  message.toLowerCase().includes("success")
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-destructive/10 text-destructive"
                }`}>
                  {message}
                </p>
              )}

              <button
                type="submit"
                disabled={!canLogin || loading}
                className="w-full rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white py-2.5 text-sm font-semibold transition-colors"
              >
                {loading ? "Logging in..." : "Log in"}
              </button>

              <p className="text-center text-xs text-muted-foreground">
                No account?{" "}
                <button
                  type="button"
                  onClick={() => triggerSwipe("signup")}
                  className="text-violet-400 hover:underline"
                >
                  Sign up
                </button>
              </p>
            </motion.form>
          ) : (
            <motion.form
              key="signup"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              onSubmit={onSubmitSignup}
              className="space-y-4"
            >
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                    Username
                  </label>
                  <input
                    type="text"
                    autoComplete="username"
                    placeholder="your_username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                    Email
                  </label>
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      autoComplete="new-password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                    Confirm password
                  </label>
                  <div className="relative">
                    <input
                      type={showConfirm ? "text" : "password"}
                      autoComplete="new-password"
                      placeholder="••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      className="w-full rounded-lg border border-input bg-background px-3 py-2.5 pr-10 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirm((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      tabIndex={-1}
                    >
                      {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Password rules */}
              <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
                <RuleItem ok={rules.username} label="Valid username" />
                <RuleItem ok={rules.length} label="8+ characters" />
                <RuleItem ok={rules.letter} label="A letter" />
                <RuleItem ok={rules.number} label="A number" />
                <RuleItem ok={rules.match} label="Passwords match" />
              </ul>

              {message && (
                <p className={`text-xs px-3 py-2 rounded-lg ${
                  message.toLowerCase().includes("success")
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-destructive/10 text-destructive"
                }`}>
                  {message}
                </p>
              )}

              <button
                type="submit"
                disabled={!canSignUp || loading}
                className="w-full rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white py-2.5 text-sm font-semibold transition-colors"
              >
                {loading ? "Creating account..." : "Create account"}
              </button>

              <p className="text-center text-xs text-muted-foreground">
                Already have an account?{" "}
                <button
                  type="button"
                  onClick={() => triggerSwipe("login")}
                  className="text-violet-400 hover:underline"
                >
                  Log in
                </button>
              </p>
            </motion.form>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
