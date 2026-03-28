import React, { useState, useEffect } from 'react'

/* ── Dashboard KPI Icons ─────────────────────────────────────────────────── */
const KpiIcons = {
  yield: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2"/>
      <path d="M12 6v6l4 2"/>
    </svg>
  ),
  plants: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 20h10"/>
      <path d="M12 20v-6"/>
      <path d="M12 14c-3 0-6-3-6-7 3 0 6 3 6 7z"/>
      <path d="M12 14c3 0 6-3 6-7-3 0-6 3-6 7z"/>
    </svg>
  ),
  clock: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
  dollar: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="1" x2="12" y2="23"/>
      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
    </svg>
  ),
}

/* ── KPI Card (matching mockup 1 layout) ─────────────────────────────────── */
function KpiCard({ icon, iconBg, label, value, sub, trend, trendUp }) {
  return (
    <div className="card" style={{
      display: 'flex', alignItems: 'center', gap: 20, padding: '20px 24px',
    }}>
      <div style={{
        width: 48, height: 48, borderRadius: 14,
        background: iconBg ?? 'var(--accent-subtle)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: 'var(--accent)', flexShrink: 0,
      }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
        {(sub || trend) && (
          <div className="metric-sub">
            {trend && (
              <span style={{
                color: trendUp ? 'var(--accent)' : trendUp === false ? 'var(--red)' : 'var(--text-muted)',
                fontWeight: 500,
              }}>
                {trendUp ? '\u2191' : trendUp === false ? '\u2193' : ''} {trend}
              </span>
            )}
            {sub && !trend && <span>{sub}</span>}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Station markers ─────────────────────────────────────────────────────── */
const STATIONS = {
  WORK:    { label: 'Work Station', x: 0.08, color: '#f59e0b' },
  GROW:    { label: 'Grow Channel', x: 0.5,  color: '#16a34a' },
  INSPECT: { label: 'Inspection',   x: 0.92, color: '#8b5cf6' },
}

const STATUS_COLORS = {
  EMPTY: '#d1d5db', SEEDLING: '#86efac', VEGETATIVE: '#4ade80',
  MATURE: '#16a34a', HARVESTED: '#f59e0b', SPENT: '#ef4444',
}

const STATUS_ICON = {
  EMPTY: '--', SEEDLING: '\u{1F331}', VEGETATIVE: '\u{1F33F}',
  MATURE: '\u{1F33F}', HARVESTED: '\u2702', SPENT: '\u{1F342}',
}

/* ── Mini line chart for dashboard ───────────────────────────────────────── */
function MiniGrowthChart({ data }) {
  if (!data || data.length < 2) {
    return (
      <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        Awaiting growth data...
      </div>
    )
  }
  const W = 700, H = 200
  const PAD = { t: 16, r: 16, b: 32, l: 48 }
  const cW = W - PAD.l - PAD.r, cH = H - PAD.t - PAD.b
  const colors = ['#3b82f6', '#16a34a', '#f59e0b', '#8b5cf6']

  const series = [0, 1, 2, 3].map(pos => ({
    points: data.filter(d => d.position_index === pos)
      .map(d => ({ x: new Date(d.timestamp).getTime(), y: d.canopy_area_cm2 ?? 0 }))
      .sort((a, b) => a.x - b.x),
  }))

  const allPts = series.flatMap(s => s.points)
  if (allPts.length < 2) return null
  const xs = allPts.map(p => p.x), ys = allPts.map(p => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const maxY = Math.max(...ys) * 1.15 || 1

  const px = x => PAD.l + ((x - minX) / (maxX - minX || 1)) * cW
  const py = y => PAD.t + cH - (y / maxY) * cH

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(f => f * maxY)

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      {/* Grid */}
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PAD.l} y1={py(v)} x2={PAD.l + cW} y2={py(v)}
            stroke="var(--border)" strokeWidth="1"/>
          <text x={PAD.l - 8} y={py(v) + 4} textAnchor="end" fontSize="10" fill="var(--text-muted)">
            {v.toFixed(0)}
          </text>
        </g>
      ))}
      {/* Lines */}
      {series.map((s, si) => {
        if (s.points.length < 2) return null
        const d = s.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(p.x)} ${py(p.y)}`).join(' ')
        const gradId = `grad-${si}`
        const areaD = d + ` L ${px(s.points[s.points.length - 1].x)} ${PAD.t + cH} L ${px(s.points[0].x)} ${PAD.t + cH} Z`
        return (
          <g key={si}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colors[si]} stopOpacity="0.12"/>
                <stop offset="100%" stopColor={colors[si]} stopOpacity="0.01"/>
              </linearGradient>
            </defs>
            <path d={areaD} fill={`url(#${gradId})`}/>
            <path d={d} fill="none" stroke={colors[si]} strokeWidth="2.5" strokeLinejoin="round"/>
          </g>
        )
      })}
      {/* Legend */}
      {series.map((s, i) => s.points.length > 0 && (
        <g key={`legend-${i}`} transform={`translate(${PAD.l + i * 120}, ${H - 6})`}>
          <circle cx="0" cy="-3" r="4" fill={colors[i]}/>
          <text x="10" y="0" fontSize="11" fill="var(--text-secondary)">Position {i}</text>
        </g>
      ))}
    </svg>
  )
}

/* ── Main Dashboard ──────────────────────────────────────────────────────── */
export default function Dashboard({ transportStatus, channelHealth, harvestEvents, nutrientStatus }) {
  const [growthData, setGrowthData] = useState([])
  const [chartRange, setChartRange] = useState('30d')
  const [yieldData, setYieldData]   = useState(null)

  useEffect(() => {
    fetch(`/api/growth_data?range=${chartRange}`)
      .then(r => r.json())
      .then(d => setGrowthData(d?.data ?? []))
      .catch(() => {})
  }, [chartRange])

  useEffect(() => {
    fetch('/api/yield_analytics')
      .then(r => r.json())
      .then(d => setYieldData(d))
      .catch(() => {})
  }, [])

  const position  = transportStatus?.current_position ?? 'GROW'
  const isMoving  = transportStatus?.is_moving ?? false
  const positionMm = transportStatus?.position_mm ?? 0
  const plants    = channelHealth?.plants ?? Array(4).fill(null)
  const recent    = harvestEvents?.slice(0, 5) ?? []

  // KPI calculations
  const totalYield = yieldData?.harvests?.reduce((s, h) => s + (h.weight_grams ?? 0), 0) ?? 0
  const healthyCount = plants.filter(p => p?.health_state === 'healthy' || !p?.health_state).length
  const totalPlants = plants.filter(p => p?.status && p.status !== 'EMPTY').length
  const deficiencyPlant = plants.find(p => p?.health_state && p.health_state !== 'healthy' && !p.health_state.startsWith('disease'))
  const deficiencyNote = deficiencyPlant ? `1 minor ${deficiencyPlant.health_state.replace(/_/g, ' ').replace(' deficiency', '')} deficiency` : 'All plants healthy'
  const costPerGram = totalYield > 0 ? (yieldData?.total_cost_usd ?? totalYield * 0.02) / totalYield : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* ── KPI Cards ──────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <KpiCard
          icon={KpiIcons.yield}
          iconBg="var(--accent-subtle)"
          label="TOTAL YIELD"
          value={`${totalYield.toFixed(1)}g`}
          trend="12% from last cycle"
          trendUp={true}
        />
        <KpiCard
          icon={KpiIcons.plants}
          iconBg="var(--accent-subtle)"
          label="HEALTHY PLANTS"
          value={totalPlants > 0 ? `${healthyCount} / ${totalPlants}` : '-- / --'}
          sub={deficiencyNote}
        />
        <KpiCard
          icon={KpiIcons.clock}
          iconBg="var(--yellow-light)"
          label="NEXT INSPECTION"
          value="14h 23m"
          sub="Scheduled scan"
        />
        <KpiCard
          icon={KpiIcons.dollar}
          iconBg="var(--accent-subtle)"
          label="COST / GRAM"
          value={costPerGram > 0 ? `$${costPerGram.toFixed(2)}` : '$--'}
          trend="8% improving"
          trendUp={false}
        />
      </div>

      {/* ── Rail Visualization ─────────────────────────────────────────── */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>Rail Position</span>
          <span className={`badge ${isMoving ? 'badge-yellow' : 'badge-green'}`}>
            {isMoving ? `Moving \u2192 ${transportStatus?.target_position ?? '...'}` : position}
          </span>
        </div>
        <div style={{
          position: 'relative', height: 56, background: 'rgba(255,248,235,0.04)',
          borderRadius: 'var(--radius-md)', border: '1px solid var(--border)',
          overflow: 'hidden',
        }}>
          {/* Rail track */}
          <div style={{
            position: 'absolute', top: '50%', left: '4%', right: '4%',
            height: 3, background: 'rgba(255,248,235,0.06)', borderRadius: 4, transform: 'translateY(-50%)',
          }}/>
          {/* Station dots */}
          {Object.entries(STATIONS).map(([key, s]) => (
            <div key={key} style={{
              position: 'absolute', left: `${s.x * 92 + 4}%`, top: '50%', transform: 'translate(-50%,-50%)',
              width: 14, height: 14, borderRadius: '50%', zIndex: 2,
              background: position === key ? s.color : 'rgba(255,248,235,0.08)',
              border: `2.5px solid ${s.color}`,
              transition: 'all 0.3s ease',
            }} title={s.label}/>
          ))}
          {/* Tray */}
          <div style={{
            position: 'absolute', top: '50%', transform: 'translate(-50%,-50%)',
            left: `${Math.min(100, (positionMm / 1200) * 92 + 4)}%`,
            width: 24, height: 24, borderRadius: 8, zIndex: 3,
            background: isMoving ? 'var(--yellow)' : 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, color: '#1c1915', fontWeight: 700,
            boxShadow: isMoving ? '0 2px 8px rgba(245,158,11,0.4)' : '0 2px 8px rgba(22,163,74,0.3)',
            transition: 'left 0.5s ease',
          }}>
            {'\u{1F33F}'}
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 11, color: 'var(--text-muted)' }}>
          <span>Work Station</span>
          <span>Grow Channel</span>
          <span>Inspection</span>
        </div>
      </div>

      {/* ── Plant Cards ────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {Array.from({ length: 4 }, (_, i) => {
          const p = plants[i]
          const status = p?.status ?? 'EMPTY'
          const health = p?.health_state ?? 'healthy'
          const days = p?.days_since_planted ?? 0
          const color = STATUS_COLORS[status] ?? '#d1d5db'
          const hasDisease = health?.startsWith('disease')

          return (
            <div key={i} className="card" style={{ padding: 18, textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>Pos {i}</span>
                {hasDisease && <span className="badge badge-red" style={{ fontSize: 9, padding: '2px 6px' }}>DISEASE</span>}
              </div>
              <div style={{
                width: 44, height: 44, borderRadius: '50%', margin: '0 auto 10px',
                background: `${color}18`, border: `2px solid ${color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 18, transition: 'all 0.3s ease',
              }}>
                {STATUS_ICON[status] ?? '--'}
              </div>
              <div className="badge" style={{
                background: `${color}15`, color: color,
                fontSize: 10, padding: '2px 8px', borderRadius: 'var(--radius-full)',
              }}>
                {status}
              </div>
              {days > 0 && (
                <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>Day {days}</div>
              )}
              {health && health !== 'healthy' && !hasDisease && (
                <div style={{ marginTop: 4, fontSize: 10, color: 'var(--yellow)' }}>
                  {health.replace(/_/g, ' ')}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Canopy Growth Chart ────────────────────────────────────────── */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
            Canopy Growth Over Time
          </span>
          <div className="pill-group">
            {['7d', '30d', 'all'].map(r => (
              <button key={r} className={`pill-btn ${chartRange === r ? 'active' : ''}`}
                onClick={() => setChartRange(r)}>
                {r.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <MiniGrowthChart data={growthData}/>
      </div>

      {/* ── Recent Harvests ────────────────────────────────────────────── */}
      {recent.length > 0 && (
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 14 }}>
            Recent Harvests
          </div>
          {recent.map((ev, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 0',
              borderBottom: i < recent.length - 1 ? '1px solid var(--border)' : 'none',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: ev.action_type === 'cut' ? 'var(--accent)' : 'var(--blue)',
                }}/>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  Position {ev.position_index} — <span style={{ textTransform: 'capitalize' }}>{ev.action_type}</span>
                </span>
              </div>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)' }}>
                {ev.weight_grams?.toFixed(1) ?? '--'} g
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
