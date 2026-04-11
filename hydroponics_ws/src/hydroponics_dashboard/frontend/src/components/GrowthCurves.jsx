import React, { useState, useEffect } from 'react'

const NDVI_COLOR = '#16a34a'
const NDVI_GRAD  = '#3b82f6'

function SVGLineChart({ series, yLabel = '' }) {
  if (!series || series.every(s => s.points.length === 0)) {
    return (
      <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        No NDVI data available
      </div>
    )
  }

  const W = 780, H = 300
  const PAD = { t: 16, r: 20, b: 40, l: 52 }
  const cW = W - PAD.l - PAD.r, cH = H - PAD.t - PAD.b

  const allPoints = series.flatMap(s => s.points)
  const xs = allPoints.map(p => p.x), ys = allPoints.map(p => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const maxY = Math.max(1, Math.max(...ys) * 1.12)

  const px = x => PAD.l + ((x - minX) / (maxX - minX || 1)) * cW
  const py = y => PAD.t + cH - (y / maxY) * cH

  const yTicks = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0].filter(v => v <= maxY * 1.05)
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map(f => minX + f * (maxX - minX))

  // Threshold reference lines
  const thresholds = [
    { value: 0.3, label: 'Healthy', color: 'rgba(22,163,74,0.4)' },
    { value: 0.2, label: 'Warning', color: 'rgba(245,158,11,0.4)' },
  ]

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      {/* Background grid */}
      {yTicks.map((v, i) => (
        <g key={`y-${i}`}>
          <line x1={PAD.l} y1={py(v)} x2={PAD.l + cW} y2={py(v)}
            stroke="var(--border)" strokeWidth="1"/>
          <text x={PAD.l - 10} y={py(v) + 4} textAnchor="end" fontSize="10"
            fill="var(--text-muted)" fontFamily="Inter, sans-serif">
            {v.toFixed(1)}
          </text>
        </g>
      ))}
      {/* Threshold reference lines */}
      {thresholds.map((t, i) => t.value <= maxY && (
        <g key={`t-${i}`}>
          <line x1={PAD.l} y1={py(t.value)} x2={PAD.l + cW} y2={py(t.value)}
            stroke={t.color} strokeWidth="1.5" strokeDasharray="6 4"/>
          <text x={PAD.l + cW + 6} y={py(t.value) + 4} fontSize="9"
            fill={t.color} fontFamily="Inter, sans-serif" fontWeight="600">
            {t.label}
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
        const COLORS = [NDVI_COLOR, NDVI_GRAD, '#f59e0b', '#8b5cf6']
        const col = COLORS[si % COLORS.length]
        const d = s.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(p.x)} ${py(p.y)}`).join(' ')
        const areaD = d + ` L ${px(s.points[s.points.length - 1].x)} ${PAD.t + cH} L ${px(s.points[0].x)} ${PAD.t + cH} Z`
        const gradId = `ndvi-grad-${si}`
        return (
          <g key={si}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={col} stopOpacity="0.15"/>
                <stop offset="100%" stopColor={col} stopOpacity="0.01"/>
              </linearGradient>
            </defs>
            <path d={areaD} fill={`url(#${gradId})`}/>
            <path d={d} fill="none" stroke={col} strokeWidth="2.5" strokeLinejoin="round"/>
            {s.points.length > 0 && (
              <circle cx={px(s.points[s.points.length - 1].x)} cy={py(s.points[s.points.length - 1].y)}
                r="4" fill={col} stroke="#1c1915" strokeWidth="2"/>
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
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/ndvi_history?range=${range}`)
      .then(r => r.json())
      .then(d => { setData(d?.readings ?? []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [range])

  const meanSeries = {
    label: 'Mean NDVI',
    points: data
      .filter(d => d.mean_ndvi != null)
      .map(d => ({ x: new Date(d.timestamp).getTime(), y: d.mean_ndvi }))
      .sort((a, b) => a.x - b.x),
  }

  const medianSeries = {
    label: 'Median NDVI',
    points: data
      .filter(d => d.median_ndvi != null)
      .map(d => ({ x: new Date(d.timestamp).getTime(), y: d.median_ndvi }))
      .sort((a, b) => a.x - b.x),
  }

  // Stats
  const latest = meanSeries.points[meanSeries.points.length - 1]?.y ?? null
  const first  = meanSeries.points[0]?.y ?? null
  const trend  = latest != null && first != null ? latest - first : null
  const latestStdDev = data.length > 0 ? data[data.length - 1]?.std_dev_ndvi : null

  return (
    <div style={{ display: 'flex', gap: 20 }}>
      {/* Main chart */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
              NDVI Trend
            </div>
            <div className="pill-group">
              {['7d', '30d', 'all'].map(r => (
                <button key={r} className={`pill-btn ${range === r ? 'active' : ''}`}
                  onClick={() => setRange(r)}>
                  {r.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          {loading ? (
            <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span className="loading-pulse" style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading data...</span>
            </div>
          ) : (
            <SVGLineChart series={[meanSeries, medianSeries]} yLabel="NDVI"/>
          )}
          {/* Legend */}
          <div style={{ display: 'flex', gap: 20, marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
            {[
              { label: 'Mean NDVI', color: NDVI_COLOR },
              { label: 'Median NDVI', color: NDVI_GRAD },
            ].map(({ label, color }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                <div style={{ width: 12, height: 3, borderRadius: 2, background: color }}/>
                <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{label}</span>
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <div style={{ width: 12, height: 2, borderRadius: 2, background: 'rgba(22,163,74,0.6)', borderTop: '1px dashed rgba(22,163,74,0.6)' }}/>
              <span style={{ color: 'var(--text-muted)' }}>Healthy threshold (0.3)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Stat sidebar */}
      <div style={{ width: 200, display: 'flex', flexDirection: 'column', gap: 12, flexShrink: 0 }}>
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 6 }}>
            Latest NDVI
          </div>
          <div style={{
            fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em',
            color: latest == null ? 'var(--text-muted)' : latest >= 0.3 ? 'var(--accent)' : latest >= 0.2 ? 'var(--yellow)' : 'var(--red)',
          }}>
            {latest != null ? latest.toFixed(3) : '--'}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>mean NDVI</div>
        </div>
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 6 }}>
            Range Change
          </div>
          <div style={{
            fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em',
            color: trend == null ? 'var(--text-muted)' : trend >= 0 ? 'var(--accent)' : 'var(--red)',
          }}>
            {trend != null ? `${trend >= 0 ? '+' : ''}${trend.toFixed(3)}` : '--'}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>over {range}</div>
        </div>
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 6 }}>
            Std Deviation
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--blue)' }}>
            {latestStdDev != null ? latestStdDev.toFixed(3) : '--'}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>spatial variation</div>
        </div>
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 6 }}>
            Readings
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            {data.length}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>in range</div>
        </div>
      </div>
    </div>
  )
}
