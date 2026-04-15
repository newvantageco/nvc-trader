'use client'

/**
 * PageTransition — wraps each page with a subtle fade + slide-up on mount.
 * CSS-only (no framer-motion), respects prefers-reduced-motion.
 * Adapted from SightSync PageTransition.tsx pattern.
 */
export default function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <div className="page-transition h-full">
      {children}
    </div>
  )
}
