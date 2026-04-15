'use client'

import { useEffect, useRef } from 'react'

interface AnimatedNumberProps {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
  duration?: number
  className?: string
  style?: React.CSSProperties
}

export default function AnimatedNumber({
  value,
  decimals = 2,
  prefix = '',
  suffix = '',
  duration = 900,
  className,
  style,
}: AnimatedNumberProps) {
  const elRef  = useRef<HTMLSpanElement>(null)
  const prevRef = useRef<number>(value)
  const rafRef  = useRef<number | null>(null)

  useEffect(() => {
    const from = prevRef.current
    const to   = value
    if (from === to) return

    const start = performance.now()

    const tick = (now: number) => {
      const elapsed  = now - start
      const progress = Math.min(elapsed / duration, 1)
      // ease-out cubic
      const eased    = 1 - Math.pow(1 - progress, 3)
      const current  = from + (to - from) * eased

      if (elRef.current) {
        elRef.current.textContent = `${prefix}${current.toLocaleString('en', {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })}${suffix}`
      }

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        prevRef.current = to
      }
    }

    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [value, decimals, prefix, suffix, duration])

  const initial = `${prefix}${value.toLocaleString('en', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}${suffix}`

  return (
    <span ref={elRef} className={className} style={style}>
      {initial}
    </span>
  )
}
