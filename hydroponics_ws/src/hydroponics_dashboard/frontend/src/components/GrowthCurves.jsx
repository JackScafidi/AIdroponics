import React, { useState, useEffect } from 'react'

const COLORS = ['#3b82f6', '#16a34a', '#f59e0b', '#8b5cf6']

function SVGLineChart({ series, yLabel = '' }) {
  if (!series || series.every(s => s.points.length === 0)) {
    return (
      <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        No growth data available
      </div>
    )
  }

  const W = 780, H = 300
  const PAD = { t: 16, r: 20, b: 40, l: 52 }
  const cW = W - PAD.l - PAD.r, cH = H - PAD.t - PAD.b

  const allPoints = series.flatMap(s => s.points)
  const xs = allPoints.map(p => p.x), ys = allPoints.map(p => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const maxY = Math.max(...ys) * 1.12 || 1

  const px = x => PAD.l + ((x - minX) / (maxX - minX || 1)) * cW
  const py = y => PAD.t + cH - (y / maxY) * cH

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(f => f * maxY)

  // Time labels
  const timeRange = maxX - minX
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map(f => minX + f * timeRange)

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      {/* Background grid */}
      {yTicks.map((v, i) => (
        <g key={`y-${i}`}>
          <line x1={PAD.l} y1={py(v)} x2={PAD.l + cW} y2={py(v)}
            stroke="var(--border)" strokeWidth="1"/>
          <text x={PAD.l - 10} y={py(v) + 4} textAnchor="end" fontSize="10"
            fill="var(--text-muted)" fontFamily="Inter, sans-serif">
            {v.toFixed(0)}
          </text>
        </g>
      ))}
      {/* X axis labels */}
      {xTicks.map((t, i) => (
        <text key={`x-${i}`} x={px(t)} y={PAD.t + cH + 20} textAnchor="middle"
          fontSize="10" fill="var(--text-muted)" fontFamily="Inter, sans-serif">
          {new Date(t).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
        </text>
      ))}
      {/* Y label */}
      <text x={14} y={PAD.t + cH / 2} transform={`rotate(-90, 14, ${PAD.t + cH / 2})`}
        textAnchor="middle" fontSize="10" fill="var(--text-muted)" fontFamily="Inter, sans-serif">
        {yLabel}
      </text>
      {/* Series with area fill */}
      {series.map((s, si) => {
        if (s.points.length < 2) return null
        const d = s.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(p.x)} ${py(p.y)}`).join(' ')
        const areaD = d + ` L ${px(s.points[s.points.length - 1].x)} ${PAD.t + cH} L ${px(s.points[0].x)} ${PAD.t + cH} Z`
        const gradId = `growth-grad-${si}`
        return (
          <g key={si}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLORS[si]} stopOpacity="0.15"/>
                <stop offset="100%" stopColor={COLORS[si]} stopOpacity="0.01"/>
              </linearGradient>
            </defs>
            <path d={areaD} fill={`url(#${gradId})`}/>
            <path d={d} fill="none" stroke={COLORS[si]} strokeWidth="2.5" strokeLinejoin="round"/>
            {/* End dot */}
            {s.points.length > 0 && (
              <circle cx={px(s.points[s.points.length - 1].x)} cy={py(s.points[s.points.length - 1].y)}
                r="4" fill={COLORS[si]} stroke="#1c1915" strokeWidth="2"/>
            )}
          </g>
        )
      })}
    </svg>
  )
}

export default function GrowthCurves() {
  const [data, setData]       = useState([])
  const [range, setRange]     = useState('7d')
  const [selected, setSelc]   = useState('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/growth_data?range=${range}`)
      .then(r => r.json())
      .then(d => { setData(d?.data ?? []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [range])

  const series = [0, 1, 2, 3].map(pos => ({
    label: `Position ${pos}`,
    points: data
      .filter(d => d.position_index === pos)
      .map(d => ({ x: new Date(d.timestamp).getTime(), y: d.canopy_area_cm2 ?? 0 }))
      .sort((a, b) => a.x - b.x),
  }))

  const visibleSeries = selected === 'all' ? series : [series[parseInt(selected)]]

  // Compute stats
  const latestValues = series.map(s => s.points.length > 0 ? s.points[s.points.length - 1].y : 0)
  const avgGrowth = series.map(s => {
    if (s.points.length < 2) return 0
    const first = s.points[0].y, last = s.points[s.points.length - 1].y
    const days = (s.points[s.points.length - 1].x - s.points[0].x) / (1000 * 60 * 60 * 24)
    return days > 0 ? (last - first) / days : 0
  })

  return (
    <div style={{ display: 'flex', gap: 20 }}>
      {/* Main chart */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
              Canopy Area (cm\u00b2) — {selected === 'all' ? 'All Positions' : `Position ${selected}`}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <select value={selected} onChange={e => setSelc(e.target.value)}
                style={{ padding: '5px 10px', fontSize: 12 }}>
                <option value="all">All Positions</option>
                {[0, 1, 2, 3].map(i => <option key={i} value={i}>Position {i}</option>)}
              </select>
              <div className="pill-group">
                {['7d', '30d', 'all'].map(r => (
                  <button key={r} className={`pill-btn ${range === r ? 'active' : ''}`}
                    onClick={() => setRange(r)}>
                    {r.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {loading ? (
            <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span className="loading-pulse" style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading data...</span>
            </div>
          ) : (
            <SVGLineChart series={visibleSeries} yLabel="cm\u00b2"/>
          )}
          {/* Legend */}
          <div style={{ display: 'flex', gap: 20, marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
            {series.map((s, i) => (
              (selected === 'all' || parseInt(selected) === i) && (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                  <div style={{ width: 12, height: 3, borderRadius: 2, background: COLORS[i] }}/>
                  <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{s.label}</span>
                </div>
              )
            ))}
          </div>
        </div>
      </div>

      {/* Stat sidebar */}
      <div style={{ width: 200, display: 'flex', flexDirection: 'column', gap: 12, flexShrink: 0 }}>
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 6 }}>
            Avg Growth
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--accent)', letterSpacing: '-0.02em' }}>
            {avgGrowth.reduce((a, b) => a + b, 0) > 0
              ? `${(avgGrowth.reduce((a, b) => a + b, 0) / avgGrowth.filter(a => a > 0).length).toFixed(1)} cm\u00b2/d`
              : '-- cm\u00b2/d'}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>per day average</div>
        </div>
        {series.map((s, i) => (
          <div key={i} className="card" style={{ padding: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: COLORS[i] }}/>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                Pos {i}
              </span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
              {latestValues[i] > 0 ? `${latestValues[i].toFixed(1)}` : '--'}
              <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 4 }}>cm\u00b2</span>
            </div>
            {avgGrowth[i] > 0 && (
              <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 2 }}>
                +{avgGrowth[i].toFixed(2)} cm\u00b2/d
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
