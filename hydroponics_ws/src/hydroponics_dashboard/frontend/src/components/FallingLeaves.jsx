import React, { useState, useEffect, useRef } from 'react'

const LEAF_COUNT = 20

const GREENS = [
  '#8BC34A', '#AED581', '#7CB342', '#9CCC65', '#C5E1A5',
  '#4CAF50', '#66BB6A', '#43A047', '#388E3C', '#2E7D32',
  '#1B5E20', '#2D5A27', '#33691E', '#1A4A1A', '#224D22',
]

const LEAF_PATHS = [
  'M15 0C15 0 2 12 2 22C2 30 7 36 15 38C23 36 28 30 28 22C28 12 15 0 15 0Z',
  'M15 0C15 0 0 14 0 24C0 32 6 38 15 40C24 38 30 32 30 24C30 14 15 0 15 0Z',
  'M15 0C15 0 4 10 4 20C4 28 8 34 15 36C22 34 26 28 26 20C26 10 15 0 15 0Z',
]

const VEIN_DATA = [
  { c: 'M15 6L15 34', l: 'M15 14L9 22', r: 'M15 20L21 27' },
  { c: 'M15 6L15 36', l: 'M15 16L8 24', r: 'M15 22L22 29' },
  { c: 'M15 5L15 32', l: 'M15 12L9 20', r: 'M15 18L21 25' },
]

function darkenColor(hex) {
  const r = Math.max(0, parseInt(hex.slice(1, 3), 16) - 50)
  const g = Math.max(0, parseInt(hex.slice(3, 5), 16) - 50)
  const b = Math.max(0, parseInt(hex.slice(5, 7), 16) - 50)
  return `rgb(${r},${g},${b})`
}

function createLeafProps(isRecycle) {
  const scale = 0.55 + Math.random() * 0.9
  const baseDuration = 6 + Math.random() * 8
  return {
    x: 5 + Math.random() * 90,
    scale,
    duration: (baseDuration / scale) * 1000,
    delay: isRecycle ? Math.random() * 2000 : Math.random() * 8000,
    color: GREENS[Math.floor(Math.random() * GREENS.length)],
    variant: Math.floor(Math.random() * 3),
    swayAmplitude: 40 + Math.random() * 45,
    swayFrequency: 1.6 + Math.random() * 1.6,
    swayPhase: Math.random() * Math.PI * 2,
    rotYPhase: Math.random() * Math.PI * 2,
    id: Math.random(),
  }
}

function LeafSVG({ variant, color }) {
  const stroke = darkenColor(color)
  const veins = VEIN_DATA[variant]
  return (
    <svg viewBox="0 0 30 40" width={30} height={40}>
      <path d={LEAF_PATHS[variant]} fill={color} />
      <path d={veins.c} stroke={stroke} strokeWidth="0.8" fill="none" opacity="0.5" />
      <path d={veins.l} stroke={stroke} strokeWidth="0.6" fill="none" opacity="0.3" />
      <path d={veins.r} stroke={stroke} strokeWidth="0.6" fill="none" opacity="0.3" />
    </svg>
  )
}

export default function FallingLeaves() {
  const [leaves, setLeaves] = useState(() =>
    Array.from({ length: LEAF_COUNT }, () => createLeafProps(false))
  )
  const [viewportHeight, setViewportHeight] = useState(window.innerHeight)

  const leafElems = useRef([])
  const leafDataRef = useRef([])
  const startTimes = useRef(new Array(LEAF_COUNT).fill(null))
  const rafRef = useRef(null)
  const timeoutRefs = useRef([])
  const vhRef = useRef(window.innerHeight)

  // Keep leaf data in sync via ref for rAF access
  useEffect(() => {
    leafDataRef.current = leaves
  }, [leaves])

  // Track viewport height
  useEffect(() => {
    const onResize = () => {
      const h = window.innerHeight
      setViewportHeight(h)
      vhRef.current = h
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // rAF animation loop
  useEffect(() => {
    const animate = (now) => {
      const vh = vhRef.current

      for (let i = 0; i < LEAF_COUNT; i++) {
        const el = leafElems.current[i]
        const data = leafDataRef.current[i]
        if (!el || !data) continue

        if (startTimes.current[i] === null) {
          startTimes.current[i] = now + data.delay
        }

        const elapsed = now - startTimes.current[i]
        if (elapsed < 0) {
          el.style.opacity = '0'
          continue
        }

        const progress = elapsed / data.duration

        if (progress >= 1.0) {
          el.style.opacity = '0'
          startTimes.current[i] = null
          const newProps = createLeafProps(true)
          leafDataRef.current[i] = newProps
          setLeaves(prev => {
            const next = [...prev]
            next[i] = newProps
            return next
          })
          continue
        }

        // Vertical position
        const y = -60 + progress * (vh + 120)

        // Sinusoidal sway
        const sec = elapsed / 1000
        const phase = sec * data.swayFrequency + data.swayPhase
        const swayX = Math.sin(phase) * data.swayAmplitude

        // Z rotation derived from sway direction (cosine = derivative of sine)
        const rotZ = Math.cos(phase) * -28

        // Y rotation at 0.7x sway frequency
        const rotY = Math.sin(sec * data.swayFrequency * 0.7 + data.rotYPhase) * 22

        // Opacity with depth parallax + fade in/out
        let opacity = 0.45 + data.scale * 0.4
        if (progress < 0.08) opacity *= progress / 0.08
        if (progress > 0.90) opacity *= (1 - progress) / 0.10

        el.style.transform = `translate3d(${swayX.toFixed(1)}px, ${y.toFixed(1)}px, 0) scale(${data.scale}) rotateZ(${rotZ.toFixed(1)}deg) rotateY(${rotY.toFixed(1)}deg)`
        el.style.opacity = opacity.toFixed(3)
      }

      rafRef.current = requestAnimationFrame(animate)
    }

    rafRef.current = requestAnimationFrame(animate)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      timeoutRefs.current.forEach(clearTimeout)
    }
  }, [])

  return (
    <div style={{
      position: 'absolute', inset: 0, overflow: 'hidden',
      pointerEvents: 'none', zIndex: 0,
    }}>
      {leaves.map((leaf, i) => (
        <div
          key={leaf.id}
          ref={el => { leafElems.current[i] = el }}
          style={{
            position: 'absolute',
            left: `${leaf.x}%`,
            top: 0,
            willChange: 'transform, opacity',
            transformStyle: 'preserve-3d',
            opacity: 0,
          }}
        >
          <LeafSVG variant={leaf.variant} color={leaf.color} />
        </div>
      ))}
    </div>
  )
}
