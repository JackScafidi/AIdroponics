import React, { useState, useEffect } from 'react'

const COLORS = { ph: '#3b82f6', ec: '#16a34a', temp: '#f97316' }

function ChartArea({ points, color, width = 700, height = 180, yMin, yMax, label }) {
  if (!points || points.length < 2) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        No data available
      </div>
    )
  }

  const PAD = { t: 12, r: 16, b: 28, l: 44 }
  const W = width, H = height
  const cW = W - PAD.l - PAD.r, cH = H - PAD.t - PAD.b

  const xs = points.map(p => p.x)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const px = x => PAD.l + ((x - minX) / (maxX - minX || 1)) * cW
  const py = y => PAD.t + cH - ((y - yMin) / ((yMax) - yMin)) * cH

  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(p.x)} ${py(p.y)}`).join(' ')
  const areaD = d + ` L ${px(points[points.length - 1].x)} ${PAD.t + cH} L ${px(points[0].x)} ${PAD.t + cH} Z`

  const yTicks = [0, 0.33, 0.66, 1].map(f => yMin + f * (yMax - yMin))

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      {/* Grid */}
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PAD.l} y1={py(v)} x2={PAD.l + cW} y2={py(v)}
            stroke="var(--border)" strokeWidth="1"/>
          <text x={PAD.l - 8} y={py(v) + 4} textAnchor="end" fontSize="10"
            fill="var(--text-muted)" fontFamily="Inter, sans-serif">
            {v.toFixed(1)}
          </text>
        </g>
      ))}
      {/* Y label */}
      <text x={12} y={PAD.t + cH / 2} transform={`rotate(-90, 12, ${PAD.t + cH / 2})`}
        textAnchor="middle" fontSize="10" fill="var(--text-muted)" fontFamily="Inter, sans-serif">
        {label}
      </text>
      {/* Area fill */}
      <defs>
        <linearGradient id={`nh-${label}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18"/>
          <stop offset="100%" stopColor={color} stopOpacity="0.02"/>
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#nh-${label})`}/>
      {/* Line */}
      <path d={d} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round"/>
      {/* End dot */}
      <circle cx={px(points[points.length - 1].x)} cy={py(points[points.length - 1].y)}
        r="4" fill={color} stroke="#1c1915" strokeWidth="2"/>
    </svg>
  )
}

export default function NutrientHistory() {
  const [data, setData]   = useState([])
  const [range, setRange] = useState('24h')
  const [loading, setL]   = useState(true)

  useEffect(() => {
    setL(true)
    fetch(`/api/probe_history?range=${range}`)
      .then(r => r.json())
      .then(d => { setData(d?.readings ?? []); setL(false) })
      .catch(() => setL(false))
  }, [range])

  const phPoints   = data.map(d => ({ x: new Date(d.timestamp).getTime(), y: d.ph }))
  const ecPoints   = data.map(d => ({ x: new Date(d.timestamp).getTime(), y: d.ec_mS_cm }))
  const tempPoints = data.map(d => ({ x: new Date(d.timestamp).getTime(), y: d.temperature_C }))

  const latestPh   = data.length > 0 ? data[data.length - 1].ph : null
  const latestEc   = data.length > 0 ? data[data.length - 1].ec_mS_cm : null
  const latestTemp = data.length > 0 ? data[data.length - 1].temperature_C : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {latestPh != null && (
            <span style={{ fontSize: 13, fontWeight: 500 }}>
              <span style={{ color: 'var(--text-muted)' }}>pH </span>
              <span style={{ color: COLORS.ph, fontWeight: 700 }}>{latestPh.toFixed(2)}</span>
            </span>
          )}
          {latestEc != null && (
            <span style={{ fontSize: 13, fontWeight: 500 }}>
              <span style={{ color: 'var(--text-muted)' }}>EC </span>
              <span style={{ color: COLORS.ec, fontWeight: 700 }}>{latestEc.toFixed(2)}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 11 }}> mS/cm</span>
            </span>
          )}
          {latestTemp != null && (
            <span style={{ fontSize: 13, fontWeight: 500 }}>
              <span style={{ color: 'var(--text-muted)' }}>Temp </span>
              <span style={{ color: 'var(--orange)', fontWeight: 700 }}>{latestTemp.toFixed(1)}\u00b0C</span>
            </span>
          )}
        </div>
        <div className="pill-group">
          {['1h', '24h', '7d', '30d'].map(r => (
            <button key={r} className={`pill-btn ${range === r ? 'active' : ''}`}
              onClick={() => setRange(r)}>
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span className="loading-pulse" style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading...</span>
        </div>
      ) : (
        <>
          {/* pH Chart */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS.ph }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>pH History</span>
            </div>
            <ChartArea points={phPoints} color={COLORS.ph} yMin={4} yMax={9} label="pH"/>
          </div>

          {/* EC Chart */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS.ec }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>EC History (mS/cm)</span>
            </div>
            <ChartArea points={ecPoints} color={COLORS.ec} yMin={0} yMax={4} label="EC"/>
          </div>

          {/* Temperature Chart */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS.temp }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>Temperature History (\u00b0C)</span>
            </div>
            <ChartArea points={tempPoints} color={COLORS.temp} yMin={10} yMax={35} label="\u00b0C"/>
          </div>

          {/* Readings table */}
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '18px 24px 0', fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 14 }}>
              Recent Readings
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  {['Time', 'pH', 'EC (mS/cm)', 'Temp (\u00b0C)'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.slice(-15).reverse().map((d, i) => (
                  <tr key={i}>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {new Date(d.timestamp).toLocaleTimeString()}
                    </td>
                    <td style={{ fontWeight: 600, color: COLORS.ph }}>{d.ph?.toFixed(2) ?? '--'}</td>
                    <td style={{ fontWeight: 600, color: COLORS.ec }}>{d.ec_mS_cm?.toFixed(2) ?? '--'}</td>
                    <td style={{ color: 'var(--orange)' }}>{d.temperature_C?.toFixed(1) ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
