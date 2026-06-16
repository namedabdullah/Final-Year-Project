import { useEffect, useRef, useState, type ReactNode, type CSSProperties } from "react"

type LazyVisualProps = {
  children: ReactNode
  className?: string
  style?: CSSProperties
  /** How far outside the viewport to start mounting (and how late to unmount). */
  rootMargin?: string
  /** Mount immediately on first render — use for above-the-fold sections (hero). */
  eager?: boolean
}

/**
 * Mounts its (expensive, animated) children only while the wrapper is near the
 * viewport, and unmounts them once scrolled away.
 *
 * The landing page stacks ~8 WebGL canvases (Threads, LightRays, 4×Orb, Plasma,
 * Aurora) plus animated 2D canvases. Rendering them all at once exhausts the
 * browser's WebGL context budget and runs every requestAnimationFrame loop in
 * parallel, which is what makes scrolling stutter. Gating each background to its
 * own section keeps only the 1–2 on-screen visuals alive at a time.
 */
export function LazyVisual({ children, className, style, rootMargin = "200px", eager = false }: LazyVisualProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(eager)

  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === "undefined") {
      setActive(true)
      return
    }
    const io = new IntersectionObserver((entries) => setActive(entries[0]?.isIntersecting ?? false), { rootMargin })
    io.observe(el)
    return () => io.disconnect()
  }, [rootMargin])

  return (
    <div ref={ref} className={className} style={style}>
      {active ? children : null}
    </div>
  )
}

export default LazyVisual
