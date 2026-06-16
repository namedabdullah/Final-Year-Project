/**
 * Shared helpers for the landing-page background effects.
 *
 * The landing page stacks many continuously-animating WebGL/canvas visuals.
 * Even with viewport gating (see `landingpage/lazy-visual.tsx`), running every
 * loop at full 60fps and full retina resolution saturates the GPU and main
 * thread, which is what makes scrolling stutter. These helpers let each effect
 * cap its pixel density and frame rate, and pause while the tab is hidden — at
 * a quality level that's visually indistinguishable for ambient backgrounds.
 */

/** Cap device-pixel-ratio so heavy fragment shaders don't render at 2–3× retina. */
export function cappedDpr(max = 1.5): number {
  if (typeof window === "undefined") return 1
  return Math.min(window.devicePixelRatio || 1, max)
}

/**
 * Returns a gate function for a rAF loop. Call it at the top of each frame with
 * the rAF timestamp; it returns false when the frame should be skipped (tab
 * hidden, or not enough time has elapsed for the target fps).
 *
 *   const shouldRender = frameGate(30)
 *   const loop = (t) => { raf = requestAnimationFrame(loop); if (!shouldRender(t)) return; ...render... }
 */
export function frameGate(fps = 30): (t: number) => boolean {
  const minDelta = 1000 / fps
  let last = -Infinity
  return (t: number) => {
    if (typeof document !== "undefined" && document.hidden) return false
    if (t - last < minDelta) return false
    last = t
    return true
  }
}
