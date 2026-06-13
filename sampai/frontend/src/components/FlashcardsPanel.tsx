import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { BrainCircuit } from "lucide-react"
import { flashcardApi, type Card } from "@/api/sampai"

type ReviewResult = "know" | "unsure" | "forgot"
type State = "idle" | "generating" | "reviewing" | "done" | "error"

const BOX_COLORS = ["bg-red-400", "bg-orange-400", "bg-yellow-400", "bg-blue-400", "bg-emerald-400"]

const TYPE_COLORS: Record<string, string> = {
  definition: "border-blue-400/40 bg-blue-500/10 text-blue-600 dark:text-blue-300",
  concept: "border-purple-400/40 bg-purple-500/10 text-purple-600 dark:text-purple-300",
  example: "border-amber-400/40 bg-amber-500/10 text-amber-600 dark:text-amber-300",
  formula: "border-emerald-400/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300",
}

const REVIEW_OPTS: { result: ReviewResult; label: string; key: string; cls: string }[] = [
  { result: "forgot", label: "Forgot", key: "1", cls: "border-red-400/40 bg-red-500/10 text-red-500 hover:bg-red-500/20" },
  { result: "unsure", label: "Unsure", key: "2", cls: "border-amber-400/40 bg-amber-500/10 text-amber-500 hover:bg-amber-500/20" },
  { result: "know", label: "Know", key: "3", cls: "border-emerald-400/40 bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20" },
]

const CARD_H = 260
const MAX_BG = 3

// ── Flashcard Stack ───────────────────────────────────────────────────────────

function FlashcardStack({
  cards,
  onReview,
  onComplete,
}: {
  cards: Card[]
  onReview: (card: Card, result: ReviewResult) => void
  onComplete: (summary: { know: number; unsure: number; forgot: number }) => void
}) {
  const [stackIds, setStackIds] = useState(() => cards.map((c) => c.id))
  const [flipped, setFlipped] = useState(false)
  const [reviewedCount, setReviewed] = useState(0)
  const [summary, setSummary] = useState({ know: 0, unsure: 0, forgot: 0 })
  const [animating, setAnimating] = useState(false)

  const cardById = Object.fromEntries(cards.map((c) => [c.id, c]))
  const totalCards = cards.length
  const topId = stackIds[stackIds.length - 1]
  const visibleIds = stackIds.slice(-(MAX_BG + 1))

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable) return
      if (e.key === " ") { e.preventDefault(); if (!flipped && !animating) setFlipped(true) }
      if (flipped && !animating) {
        if (e.key === "1") handleReview("forgot")
        else if (e.key === "2") handleReview("unsure")
        else if (e.key === "3") handleReview("know")
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flipped, animating])

  function handleReview(result: ReviewResult) {
    if (animating) return
    const card = cardById[topId]
    if (!card) return

    setAnimating(true)
    const newSummary = { ...summary, [result]: summary[result] + 1 }
    setSummary(newSummary)
    onReview(card, result)

    const newCount = reviewedCount + 1
    setReviewed(newCount)

    if (newCount >= totalCards) {
      setTimeout(() => onComplete(newSummary), 420)
      return
    }

    setTimeout(() => {
      setStackIds((prev) => {
        const arr = [...prev]
        const top = arr.pop()!
        arr.unshift(top)
        return arr
      })
      setFlipped(false)
      setTimeout(() => setAnimating(false), 260)
    }, 230)
  }

  const pct = totalCards > 0 ? (reviewedCount / totalCards) * 100 : 0

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-6 py-4 min-h-0">

      {/* Progress */}
      <div className="w-full max-w-lg space-y-1.5 shrink-0">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{reviewedCount} of {totalCards} reviewed</span>
          <span>{totalCards - reviewedCount} left</span>
        </div>
        <div className="h-1.5 rounded-full bg-border/30 overflow-hidden">
          <div
            className="h-full bg-chart-1/60 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Stack */}
      <div className="relative w-full max-w-lg flex-none mx-auto" style={{ height: CARD_H }}>
        {visibleIds.map((id, visIdx) => {
          const isTop = id === topId
          const posFromTop = visibleIds.length - 1 - visIdx
          const rotZ = isTop ? 0 : posFromTop % 2 === 0 ? posFromTop * 4 : -(posFromTop * 4)
          const scl = 1 - posFromTop * 0.045
          const yOff = posFromTop * 6

          return (
            <motion.div
              key={id}
              className="absolute inset-0"
              style={{ zIndex: visIdx, transformOrigin: "50% 105%" }}
              animate={{ rotateZ: rotZ, scale: scl, y: yOff }}
              transition={{ type: "spring", stiffness: 280, damping: 22 }}
            >
              {isTop ? (
                <div style={{ width: "100%", height: "100%", perspective: 1400 }}>
                  <motion.div
                    className="relative w-full h-full"
                    style={{ transformStyle: "preserve-3d" }}
                    animate={{ rotateY: flipped ? 180 : 0 }}
                    transition={{ duration: 0.42, ease: "easeInOut" }}
                    onClick={() => { if (!flipped && !animating) setFlipped(true) }}
                  >
                    {/* Front */}
                    <div
                      className="absolute inset-0 rounded-2xl border border-border/70 bg-card/85 backdrop-blur-md flex flex-col items-center justify-center gap-4 text-center overflow-hidden cursor-pointer p-8 shadow-lg"
                      style={{ backfaceVisibility: "hidden" }}
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 via-transparent to-violet-500/10 rounded-2xl pointer-events-none" />
                      {cardById[id]?.card_type && (
                        <span className={`relative z-10 text-[11px] font-medium px-2.5 py-0.5 rounded-full border capitalize ${TYPE_COLORS[cardById[id].card_type] ?? "border-border/40 text-muted-foreground"}`}>
                          {cardById[id].card_type}
                        </span>
                      )}
                      <p className="relative z-10 text-base font-medium text-foreground leading-relaxed max-w-sm">
                        {cardById[id]?.front}
                      </p>
                      <p className="relative z-10 text-xs text-muted-foreground/40">click to reveal</p>
                    </div>

                    {/* Back */}
                    <div
                      className="absolute inset-0 rounded-2xl border border-chart-1/50 bg-card/85 backdrop-blur-md flex flex-col gap-4 overflow-hidden p-6 shadow-lg"
                      style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-chart-1/15 via-transparent to-chart-2/10 rounded-2xl pointer-events-none" />
                      <p className="flex-1 min-h-0 text-sm text-foreground leading-relaxed overflow-y-auto relative z-10">
                        {cardById[id]?.back}
                      </p>
                      <div className="shrink-0 flex gap-2 relative z-10">
                        {REVIEW_OPTS.map(({ result, label, key, cls }) => (
                          <button
                            key={result}
                            type="button"
                            onClick={(e) => { e.stopPropagation(); handleReview(result) }}
                            className={`flex-1 py-2 rounded-xl border text-sm font-medium transition-colors cursor-pointer ${cls}`}
                          >
                            {label} <span className="opacity-40 text-xs">{key}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                </div>
              ) : (
                <div className="w-full h-full rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm shadow-md" />
              )}
            </motion.div>
          )
        })}
      </div>

      {/* Hint */}
      <p className="shrink-0 text-[11px] text-muted-foreground/40 text-center">
        Space to flip · 1 Forgot · 2 Unsure · 3 Know
      </p>
    </div>
  )
}

// ── Main Panel ────────────────────────────────────────────────────────────────

export default function FlashcardsPanel({ fileId }: { fileId: number }) {
  const [state, setState] = useState<State>("idle")
  const [deckId, setDeckId] = useState<number | null>(null)
  const [cards, setCards] = useState<Card[]>([])
  const [count, setCount] = useState<10 | 20 | 30>(20)
  const [boxCounts, setBoxCounts] = useState<Record<string, number> | null>(null)
  const [dueCount, setDueCount] = useState(0)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [summary, setSummary] = useState({ know: 0, unsure: 0, forgot: 0 })
  const [showHistory, setShowHistory] = useState(false)
  const [historyItems, setHistoryItems] = useState<{ deck_id: number; status: string; card_count: number | null }[]>([])
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollStartRef = useRef<number>(0)

  function refresh() {
    flashcardApi.history(fileId)
      .then((h) => { setBoxCounts(h.box_counts); setHistoryItems(h.items) })
      .catch(() => {})
    flashcardApi.due(fileId).then((d) => setDueCount(d.total_due)).catch(() => {})
  }

  useEffect(() => {
    refresh()
    flashcardApi.history(fileId)
      .then((h) => {
        setBoxCounts(h.box_counts)
        setHistoryItems(h.items)
        if (h.has_open_deck && h.open_deck_id != null) {
          resumeDeck(h.open_deck_id)
        } else {
          flashcardApi.due(fileId).then((d) => setDueCount(d.total_due)).catch(() => {})
        }
      })
      .catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId])

  async function resumeDeck(id: number) {
    setDeckId(id)
    try {
      const detail = await flashcardApi.getDeck(id)
      if (detail.status === "ready" && detail.cards?.length) {
        setCards(detail.cards); setSummary({ know: 0, unsure: 0, forgot: 0 }); setState("reviewing")
      } else if (detail.status === "pending" || detail.status === "generating") {
        pollStartRef.current = Date.now(); setState("generating")
      } else if (detail.status === "failed") {
        setErrorMsg(detail.error_msg ?? "Generation failed."); setState("error")
      }
    } catch { setState("idle") }
  }

  useEffect(() => {
    if (state !== "generating" || deckId == null) return
    const interval = setInterval(async () => {
      if (Date.now() - pollStartRef.current > 120_000) {
        clearInterval(interval); setErrorMsg("Timed out. Please try again."); setState("error"); return
      }
      try {
        const detail = await flashcardApi.getDeck(deckId)
        if (detail.status === "ready" && detail.cards?.length) {
          clearInterval(interval); setCards(detail.cards); setSummary({ know: 0, unsure: 0, forgot: 0 }); setState("reviewing"); refresh()
        } else if (detail.status === "failed") {
          clearInterval(interval); setErrorMsg(detail.error_msg ?? "Generation failed."); setState("error")
        }
      } catch {}
    }, 2000)
    return () => clearInterval(interval)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, deckId])

  async function handleGenerate() {
    setErrorMsg(null)
    try {
      const res = await flashcardApi.generate(fileId, count)
      setDeckId(res.deck_id); pollStartRef.current = Date.now(); setState("generating")
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to start generation."
      setErrorMsg(msg)
    }
  }

  async function handleStartDueReview() {
    try {
      const due = await flashcardApi.due(fileId)
      if (!due.cards.length) return
      setCards(due.cards); setSummary({ know: 0, unsure: 0, forgot: 0 }); setDeckId(null); setState("reviewing")
    } catch {}
  }

  function handleReview(card: Card, result: ReviewResult) {
    flashcardApi.review(card.id, result).catch(() => {})
  }

  function handleComplete(s: { know: number; unsure: number; forgot: number }) {
    setSummary(s); setState("done"); refresh()
  }

  function handleReset() {
    setDeckId(null); setCards([]); setErrorMsg(null)
    setSummary({ know: 0, unsure: 0, forgot: 0 }); setState("idle")
    refresh()
  }

  const totalInBoxes = boxCounts ? Object.values(boxCounts).reduce((a, b) => a + b, 0) : 0

  return (
    <div className="flex-1 flex flex-col min-h-0">

      {/* ── IDLE ── */}
      {state === "idle" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-8 px-8 py-6">

          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl border border-border/40 bg-card/40 backdrop-blur-sm mb-1">
              <BrainCircuit className="w-7 h-7 text-chart-1" />
            </div>
            <p className="text-base font-semibold text-foreground">Flashcards</p>
            <p className="text-xs text-muted-foreground/70 max-w-xs">
              {historyItems.length > 0
                ? "Spaced-repetition review from this document."
                : "AI-generated from this document. Review with spaced repetition."}
            </p>
          </div>

          {/* Mastery bar */}
          {boxCounts && totalInBoxes > 0 && (
            <div className="w-full max-w-xs space-y-1.5">
              <div className="flex h-2 rounded-full overflow-hidden gap-px">
                {[1, 2, 3, 4, 5].map((box) => {
                  const cnt = boxCounts[String(box)] ?? 0
                  const pct = totalInBoxes > 0 ? (cnt / totalInBoxes) * 100 : 0
                  return (
                    <div
                      key={box}
                      className={`${BOX_COLORS[box - 1]} transition-all`}
                      style={{ width: `${pct}%` }}
                      title={`Box ${box}: ${cnt} card${cnt !== 1 ? "s" : ""}`}
                    />
                  )
                })}
              </div>
              <div className="flex justify-between text-[10px] text-muted-foreground/50">
                <span>Learning</span><span>Mastered</span>
              </div>
            </div>
          )}

          <div className="w-full max-w-xs space-y-3">
            {/* Due review */}
            {dueCount > 0 && (
              <button
                type="button"
                onClick={handleStartDueReview}
                className="w-full py-3 rounded-xl border border-chart-1/40 bg-chart-1/15 text-sm font-medium text-chart-1 hover:bg-chart-1/25 transition-colors cursor-pointer"
              >
                Review {dueCount} due card{dueCount !== 1 ? "s" : ""}
              </button>
            )}

            {dueCount > 0 && (
              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-border/30" />
                <span className="text-[10px] text-muted-foreground/40">or generate new</span>
                <div className="flex-1 h-px bg-border/30" />
              </div>
            )}

            <div className="space-y-2.5">
              <div className="flex gap-2">
                {([10, 20, 30] as const).map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setCount(n)}
                    className={`flex-1 py-2 rounded-xl border text-sm font-medium transition-all cursor-pointer ${
                      count === n
                        ? "border-chart-1/60 bg-chart-1/20 text-foreground"
                        : "border-border/40 bg-card/20 text-muted-foreground hover:border-border/60 hover:text-foreground"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={handleGenerate}
                className="w-full py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer"
              >
                Generate {count} cards
              </button>
            </div>

            {errorMsg && <p className="text-xs text-destructive text-center">{errorMsg}</p>}
          </div>

          {/* History */}
          {historyItems.length > 0 && (
            <div className="w-full max-w-xs">
              <button
                type="button"
                onClick={() => setShowHistory((v) => !v)}
                className="w-full text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-pointer text-center"
              >
                {showHistory ? "Hide history" : `${historyItems.length} past deck${historyItems.length !== 1 ? "s" : ""}`}
              </button>
              {showHistory && (
                <div className="mt-2 max-h-40 overflow-y-auto space-y-1.5">
                  {historyItems.map((h) => (
                    <div key={h.deck_id} className="flex items-center justify-between rounded-lg border border-border/40 bg-card/30 px-3 py-2 text-xs">
                      <span className="text-muted-foreground capitalize">{h.status}</span>
                      <span className="text-muted-foreground/60">{h.card_count ?? "—"} cards</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── GENERATING ── */}
      {state === "generating" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div className="flex gap-1.5 items-center">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="block w-2 h-2 rounded-full bg-chart-1/70"
                animate={{ y: [0, -6, 0] }}
                transition={{ duration: 0.9, delay: i * 0.18, repeat: Infinity, ease: "easeInOut" }}
              />
            ))}
          </div>
          <p className="text-sm text-muted-foreground">Generating flashcards…</p>
          <p className="text-xs text-muted-foreground/50">This may take up to a minute.</p>
        </div>
      )}

      {/* ── REVIEWING ── */}
      {state === "reviewing" && cards.length > 0 && (
        <FlashcardStack
          cards={cards}
          onReview={handleReview}
          onComplete={handleComplete}
        />
      )}

      {/* ── DONE ── */}
      {state === "done" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-8">
          <div className="text-center">
            <p className="text-lg font-semibold text-foreground">Session complete</p>
            <p className="text-xs text-muted-foreground/60 mt-1">{cards.length} cards reviewed</p>
          </div>

          <div className="grid grid-cols-3 gap-3 w-full max-w-xs">
            {[
              { label: "Know", count: summary.know, cls: "border-emerald-400/30 bg-emerald-500/10", textCls: "text-emerald-500" },
              { label: "Unsure", count: summary.unsure, cls: "border-amber-400/30 bg-amber-500/10", textCls: "text-amber-500" },
              { label: "Forgot", count: summary.forgot, cls: "border-red-400/30 bg-red-500/10", textCls: "text-red-500" },
            ].map(({ label, count: c, cls, textCls }) => (
              <div key={label} className={`rounded-2xl border ${cls} p-4 text-center backdrop-blur-sm`}>
                <p className={`text-2xl font-bold ${textCls}`}>{c}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-2 w-full max-w-xs">
            {dueCount > 0 && (
              <button type="button" onClick={handleStartDueReview}
                className="w-full py-2.5 rounded-xl border border-chart-1/40 bg-chart-1/10 text-sm font-medium text-chart-1 hover:bg-chart-1/20 transition-colors cursor-pointer">
                Review {dueCount} due card{dueCount !== 1 ? "s" : ""}
              </button>
            )}
            <button type="button" onClick={handleGenerate}
              className="w-full py-2.5 rounded-xl bg-chart-1/80 hover:bg-chart-1 text-foreground text-sm font-medium transition-colors cursor-pointer">
              New deck
            </button>
            <button type="button" onClick={handleReset}
              className="w-full py-2 rounded-xl text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
              ← Back
            </button>
          </div>
        </div>
      )}

      {/* ── ERROR ── */}
      {state === "error" && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          {errorMsg && <p className="text-xs text-destructive text-center max-w-xs">{errorMsg}</p>}
          <button type="button" onClick={handleReset}
            className="px-6 py-2.5 rounded-xl border border-border/40 bg-card/30 text-sm text-foreground hover:bg-card/50 cursor-pointer transition-colors">
            Back to setup
          </button>
        </div>
      )}

    </div>
  )
}
