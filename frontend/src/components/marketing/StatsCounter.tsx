'use client'

import { useEffect, useRef, useState } from 'react'
import { useInView, useReducedMotion } from 'framer-motion'

interface StatItem {
  value: number
  suffix?: string
  label: string
}

function Counter({ value, suffix = '' }: { value: number; suffix?: string }) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true })
  const shouldReduceMotion = useReducedMotion()
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!isInView) return
    if (shouldReduceMotion) {
      setCount(value)
      return
    }

    let start = 0
    const duration = 2000
    const step = value / (duration / 16)

    const timer = setInterval(() => {
      start += step
      if (start >= value) {
        setCount(value)
        clearInterval(timer)
      } else {
        setCount(Math.floor(start))
      }
    }, 16)

    return () => clearInterval(timer)
  }, [isInView, value, shouldReduceMotion])

  return <span ref={ref}>{count}{suffix}</span>
}

export default function StatsCounter({ stats }: { stats: StatItem[] }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
      {stats.map((stat, i) => (
        <div key={i} className="text-center">
          <div className="text-4xl md:text-5xl font-bold text-white">
            <Counter value={stat.value} suffix={stat.suffix} />
          </div>
          <div className="text-sm md:text-base text-slate-400 mt-2">{stat.label}</div>
        </div>
      ))}
    </div>
  )
}
