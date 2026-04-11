import React, { useState, useEffect } from 'react'

/* ── KPI Icons ───────────────────────────────────────────────────────────── */
const KpiIcons = {
  ndvi: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 20h10"/><path d="M12 20v-6"/>
      <path d="M12 14c-3 0-6-3-6-7 3 0 6 3 6 7z"/>
      <path d="M12 14c3 0 6-3 6-7-3 0-6 3-6 7z"/>
    </svg>
  ),
  probe: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a4 4 0 0 0-4 4v6a4 4 0 0 0 8 0V6a4 4 0 0 0-4-4z"/>
      <path d="M12 16v6"/><path d="M8 22h8"/>
    </svg>
  ),
  water: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2c0 0-8 4-8 10a8 8 0 0 0 16 0c0-6-8-10-8-10z"/>
    </svg>
  ),
  diagnostic: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <path d="M12 8v4M12 16h.01"/>
    </svg>
  ),
}

/* ── KPI Card ────────────────────────────────────────────────────────────── */
function KpiCard({ icon, iconBg, label, value, sub, trend, trendUp }) {
  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '20px 24px' }}>
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

/* ── NDVI severity colour ────────────────────────────────────────────────── */
function ndviColor(ndvi) {
  if (ndvi == null) return 'var(--text-muted)'
  if (ndvi >= 0.3)  return 'var(--accent)'
  if (ndvi >= 0.2)  return 'var(--yellow)'
  return 'var(--red)'
}

/* ── Severity badge ──────────────────────────────────────────────────────── */
const SEV_BADGE = { 0: 'badge-green', 1: 'badge-yellow', 2: 'badge-red' }
const SEV_LABEL = { 0: 'Healthy', 1: 'Warning', 2: 'Critical' }

/* ── Water level bar ─────────────────────────────────────────────────────── */
function WaterBar({ percent }) {
  const pct = Math.max(0, Math.min(100, percent ?? 0))
  const color = pct > 40 ? 'var(--teal)' : pct > 20 ? 'var(--yellow)' : 'var(--red)'
  return (
    <div style={{ position: 'relative', height: 8, background: 'rgba(255,248,235,0.06)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 'var(--radius-full)', transition: 'width 0.5s ease' }}/>
    </div>
  )
}

/* ── Mini NDVI chart ─────────────────────────────────────────────────────── */
function MiniNdviChart({ data }) {
  if (!data || data.length < 2) {
    return (
      <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        Awaiting NDVI data...
      </div>
    )
  }
  const W = 700, H = 180
  const PAD = { t: 12, r: 16, b: 28, l: 44 }
  const cW = W - PAD.l - PAD.r, cH = H - PAD.t - PAD.b

  const points = data.map(d => ({ x: new Date(d.timestamp).getTime(), y: d.mean_ndvi ?? 0 })).sort((a, b) => a.x - b.x)
  const xs = points.map(p => p.x), ys = points.map(p => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const maxY = Math.max(1, ...ys) * 1.1
  const minY = 0

  const px = x => PAD.l + ((x - minX) / (maxX - minX || 1)) * cW
  const py = y => PAD.t + cH - ((y - minY) / (maxY - minY)) * cH

  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(p.x)} ${py(p.y)}`).join(' ')
  const areaD = d + ` L ${px(points[points.length - 1].x)} ${PAD.t + cH} L ${px(points[0].x)} ${PAD.t + cH} Z`

  const yTicks = [0, 0.2, 0.3, 0.5, 1.0].filter(v => v <= maxY)

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PAD.l} y1={py(v)} x2={PAD.l + cW} y2={py(v)}
            stroke={v === 0.3 ? 'rgba(74,222,128,0.25)' : v === 0.2 ? 'rgba(251,191,36,0.25)' : 'var(--border)'}
            strokeWidth="1" strokeDasharray={v === 0.3 || v === 0.2 ? '4 4' : undefined}/>
          <text x={PAD.l - 8} y={py(v) + 4} textAnchor="end" fontSize="10" fill="var(--text-muted)">
            {v.toFixed(1)}
          </text>
        </g>
      ))}
      <defs>
        <linearGradient id="ndvi-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4ade80" stopOpacity="0.18"/>
          <stop offset="100%" stopColor="#4ade80" stopOpacity="0.01"/>
        </linearGradient>
      </defs>
      <path d={areaD} fill="url(#ndvi-area-grad)"/>
      <path d={d} fill="none" stroke="#4ade80" strokeWidth="2.5" strokeLinejoin="round"/>
      <circle cx={px(points[points.length - 1].x)} cy={py(points[points.length - 1].y)}
        r="4" fill="#4ade80" stroke="#1c1915" strokeWidth="2"/>
    </svg>
  )
}

/* ── Main Dashboard ──────────────────────────────────────────────────────── */
export default function Dashboard({ probeReading, ndviReading, waterLevel, plantStatus, diagnosticReport, alerts }) {
  const [ndviData, setNdviData] = useState([])
  const [chartRange, setChartRange] = useState('7d')

  useEffect(() => {
    fetch(`/api/ndvi_history?range=${chartRange}`)
      .then(r => r.json())
      .then(d => setNdviData(d?.readings ?? []))
      .catch(() => {})
  }, [chartRange])

  const pr = probeReading ?? {}
  const nr = ndviReading ?? {}
  const wl = waterLevel ?? {}
  const ps = plantStatus ?? {}
  const dr = diagnosticReport ?? {}

  const ndvi        = nr.mean_ndvi
  const ndviTrend   = nr.ndvi_trend_slope
  const severity    = dr.overall_severity ?? 0
  const activeRules = dr.active_rules ?? []
  const warnings    = ps.active_warnings ?? []

  const trendUp     = ndviTrend != null ? ndviTrend >= 0 : undefined
  const trendStr    = ndviTrend != null
    ? `${ndviTrend >= 0 ? '+' : ''}${(ndviTrend * 1000).toFixed(2)}\u00d710\u207b\u00b3/reading`
    : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* ── KPI Cards ──────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
        <KpiCard
          icon={KpiIcons.ndvi}
          iconBg="var(--accent-subtle)"
          label="NDVI"
          value={ndvi != null ? ndvi.toFixed(3) : '--'}
          trend={trendStr}
          trendUp={trendUp}
        />
        <KpiCard
          icon={KpiIcons.probe}
          iconBg="var(--blue-light)"
          label="PH / EC"
          value={pr.ph != null ? `${pr.ph.toFixed(2)} / ${pr.ec_mS_cm?.toFixed(2) ?? '--'} mS` : '-- / --'}
          sub={pr.temperature_C != null ? `${pr.temperature_C.toFixed(1)}\u00b0C` : undefined}
        />
        <KpiCard
          icon={KpiIcons.water}
          iconBg="rgba(45,212,191,0.1)"
          label="WATER LEVEL"
          value={wl.level_percent != null ? `${wl.level_percent.toFixed(0)}%` : '--'}
          sub={wl.level_cm != null ? `${wl.level_cm.toFixed(1)} cm` : undefined}
        />
        <KpiCard
          icon={KpiIcons.diagnostic}
          iconBg={severity >= 2 ? 'var(--red-light)' : severity >= 1 ? 'var(--yellow-light)' : 'var(--accent-subtle)'}
          label="PLANT STATUS"
          value={ps.summary || SEV_LABEL[severity] || '--'}
          sub={activeRules.length > 0 ? `${activeRules.length} rule${activeRules.length !== 1 ? 's' : ''} active` : 'No active rules'}
        />
      </div>

      {/* ── Active Warnings ────────────────────────────────────────────── */}
      {warnings.length > 0 && (
        <div className="alert-banner alert-banner-warning">
          <span style={{ fontSize: 16 }}>{'\u26a0'}</span>
          <span style={{ flex: 1, fontWeight: 500 }}>{warnings.join(' \u00b7 ')}</span>
        </div>
      )}

      {/* ── NDVI Trend Chart ───────────────────────────────────────────── */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
            NDVI Trend
          </span>
          <div className="pill-group">
            {['24h', '7d', 'all'].map(r => (
              <button key={r} className={`pill-btn ${chartRange === r ? 'active' : ''}`}
                onClick={() => setChartRange(r)}>
                {r.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <MiniNdviChart data={ndviData}/>
        <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: 11, color: 'var(--text-muted)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 2, background: 'rgba(74,222,128,0.6)', borderRadius: 2, display: 'inline-block' }}/>
            Healthy threshold (0.3)
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 2, background: 'rgba(251,191,36,0.6)', borderRadius: 2, display: 'inline-block' }}/>
            Warning threshold (0.2)
          </span>
        </div>
      </div>

      {/* ── Water Level + Diagnostic Rules ─────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Water level card */}
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>
            Water Level
          </div>
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
              <span style={{ color: 'var(--text-muted)' }}>Level</span>
              <span style={{ fontWeight: 700, color: 'var(--teal)' }}>
                {wl.level_percent != null ? `${wl.level_percent.toFixed(0)}%` : '--'}
              </span>
            </div>
            <WaterBar percent={wl.level_percent}/>
          </div>
          {wl.level_cm != null && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {wl.level_cm.toFixed(1)} cm depth
            </div>
          )}
        </div>

        {/* Diagnostic rules card */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
              Active Rules
            </span>
            {dr.overall_severity != null && (
              <span className={`badge ${SEV_BADGE[dr.overall_severity] ?? 'badge-green'}`}>
                {SEV_LABEL[dr.overall_severity] ?? 'Info'}
              </span>
            )}
          </div>
          {activeRules.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-muted)', paddingTop: 4 }}>
              {'\u2705'} No rules firing
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {activeRules.map((rule, i) => (
                <div key={i} style={{
                  fontSize: 12, color: 'var(--text-secondary)',
                  padding: '5px 10px', borderRadius: 'var(--radius-sm)',
                  background: 'rgba(255,248,235,0.04)',
                  border: '1px solid var(--border)',
                  fontFamily: "'SF Mono', monospace",
                }}>
                  {rule}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Recent Alerts ──────────────────────────────────────────────── */}
      {alerts.length > 0 && (
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 14 }}>
            Recent Alerts
          </div>
          {alerts.slice(0, 5).map((a, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '9px 0',
              borderBottom: i < Math.min(4, alerts.length - 1) ? '1px solid var(--border)' : 'none',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: a.severity === 'critical' ? 'var(--red)' : a.severity === 'warning' ? 'var(--yellow)' : 'var(--blue)',
                }}/>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {a.message ?? a.alert_type}
                </span>
              </div>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0, marginLeft: 12 }}>
                {a.timestamp ? new Date(a.timestamp).toLocaleTimeString() : ''}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
