import React from 'react'

/* ── Circular Gauge ──────────────────────────────────────────────────────── */
function CircularGauge({ label, value, min, max, target, unit, decimals = 1, color }) {
  const pct = Math.max(0, Math.min(1, (value - min) / (max - min)))
  const tpct = Math.max(0, Math.min(1, (target - min) / (max - min)))

  const diff = Math.abs(value - target)
  let gaugeColor = color ?? 'var(--accent)'
  if (diff > (max - min) * 0.15) gaugeColor = 'var(--red)'
  else if (diff > (max - min) * 0.07) gaugeColor = 'var(--yellow)'

  const R = 46, cx = 56, cy = 60
  const startAngle = Math.PI * 0.8
  const endAngle = Math.PI * 2.2
  const range = endAngle - startAngle

  const angleForPct = (p) => startAngle + p * range
  const xAt = (a) => cx + R * Math.cos(a)
  const yAt = (a) => cy + R * Math.sin(a)

  const trackPath = `M ${xAt(startAngle)} ${yAt(startAngle)} A ${R} ${R} 0 1 1 ${xAt(endAngle)} ${yAt(endAngle)}`
  const valueAngle = angleForPct(pct)
  const largeArc = (valueAngle - startAngle) > Math.PI ? 1 : 0
  const valuePath = `M ${xAt(startAngle)} ${yAt(startAngle)} A ${R} ${R} 0 ${largeArc} 1 ${xAt(valueAngle)} ${yAt(valueAngle)}`
  const targetAngle = angleForPct(tpct)

  return (
    <div className="card" style={{ textAlign: 'center', flex: 1, minWidth: 180, padding: '24px 20px' }}>
      <svg width="112" height="80" viewBox="0 0 112 80" style={{ overflow: 'visible', display: 'block', margin: '0 auto 8px' }}>
        <path d={trackPath} fill="none" stroke="rgba(255,248,235,0.08)" strokeWidth="10" strokeLinecap="round"/>
        <defs>
          <linearGradient id={`gauge-${label}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={gaugeColor} stopOpacity="0.3"/>
            <stop offset="100%" stopColor={gaugeColor}/>
          </linearGradient>
        </defs>
        <path d={valuePath} fill="none" stroke={`url(#gauge-${label})`} strokeWidth="10" strokeLinecap="round"/>
        <circle cx={xAt(targetAngle)} cy={yAt(targetAngle)} r="5"
          fill="var(--blue)" stroke="#1c1915" strokeWidth="2.5"/>
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="18" fontWeight="700"
          fill={gaugeColor} fontFamily="Inter, sans-serif">
          {value?.toFixed(decimals) ?? '--'}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fontSize="10"
          fill="var(--text-muted)" fontFamily="Inter, sans-serif">
          {unit}
        </text>
      </svg>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
        Target: {target?.toFixed(1)} {unit}
      </div>
    </div>
  )
}

/* ── Status Card ─────────────────────────────────────────────────────────── */
function StatusCard({ label, value, sub, color }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 150, padding: '20px 24px' }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: color ?? 'var(--accent)', letterSpacing: '-0.02em' }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

/* ── Progress Bar ────────────────────────────────────────────────────────── */
function ProgressRow({ label, value, max, unit, color }) {
  const pct = Math.min(100, (Math.abs(value ?? 0) / max) * 100)
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 5 }}>
        <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{label}</span>
        <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{value?.toFixed(3) ?? 0} {unit}</span>
      </div>
      <div style={{ height: 6, background: 'rgba(255,248,235,0.06)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 'var(--radius-full)',
          background: color ?? 'var(--blue)',
          width: `${pct}%`,
          transition: 'width 0.5s ease',
        }}/>
      </div>
    </div>
  )
}

/* ── Main Sensors Page ───────────────────────────────────────────────────── */
export default function SensorGauges({ probeReading, ndviReading, waterLevel }) {
  const pr = probeReading ?? {}
  const nr = ndviReading ?? {}
  const wl = waterLevel ?? {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Probe gauges */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
        <CircularGauge label="pH"          value={pr.ph ?? 7.0}           min={4} max={9}  target={6.0} unit="pH"    decimals={2} color="var(--blue)"/>
        <CircularGauge label="EC"          value={pr.ec_mS_cm ?? 1.2}     min={0} max={4}  target={1.3} unit="mS/cm" decimals={2} color="var(--accent)"/>
        <CircularGauge label="Temperature" value={pr.temperature_C ?? 22} min={10} max={35} target={22}  unit="\u00b0C"   decimals={1} color="var(--orange)"/>
      </div>

      {/* NDVI + water status row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
        <StatusCard
          label="NDVI"
          value={nr.mean_ndvi?.toFixed(3) ?? '--'}
          sub={nr.ndvi_trend_slope != null ? `Trend: ${nr.ndvi_trend_slope >= 0 ? '+' : ''}${(nr.ndvi_trend_slope * 1000).toFixed(2)}\u00d710\u207b\u00b3` : undefined}
          color={nr.mean_ndvi != null ? (nr.mean_ndvi >= 0.3 ? 'var(--accent)' : nr.mean_ndvi >= 0.2 ? 'var(--yellow)' : 'var(--red)') : 'var(--text-muted)'}
        />
        <StatusCard
          label="Water Level"
          value={wl.level_percent != null ? `${wl.level_percent.toFixed(0)}%` : '--'}
          sub={wl.level_cm != null ? `${wl.level_cm.toFixed(1)} cm` : undefined}
          color="var(--teal)"
        />
        <StatusCard
          label="NDVI Std Dev"
          value={nr.std_dev_ndvi?.toFixed(3) ?? '--'}
          sub="Spatial variation"
          color="var(--blue)"
        />
        <StatusCard
          label="Trend Window"
          value={nr.trend_window_size ?? '--'}
          sub="readings"
          color="var(--text-secondary)"
        />
      </div>

      {/* NDVI detail row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* NDVI channels */}
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>
            NDVI Readings
          </div>
          <ProgressRow label="Mean NDVI"   value={nr.mean_ndvi}   max={1} unit="" color="var(--accent)"/>
          <ProgressRow label="Median NDVI" value={nr.median_ndvi} max={1} unit="" color="var(--teal)"/>
          <ProgressRow label="Std Dev"     value={nr.std_dev_ndvi} max={0.3} unit="" color="var(--blue)"/>
        </div>

        {/* Probe readings summary */}
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>
            Latest Probe Reading
          </div>
          {[
            { name: 'pH',      val: pr.ph?.toFixed(2),           color: 'var(--blue)' },
            { name: 'EC',      val: pr.ec_mS_cm != null ? `${pr.ec_mS_cm.toFixed(2)} mS/cm` : '--', color: 'var(--accent)' },
            { name: 'Temp',    val: pr.temperature_C != null ? `${pr.temperature_C.toFixed(1)}\u00b0C` : '--', color: 'var(--orange)' },
          ].map(({ name, val, color }, i) => (
            <div key={name} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '9px 0',
              borderBottom: i < 2 ? '1px solid var(--border)' : 'none',
            }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>{name}</span>
              <span style={{ fontSize: 15, fontWeight: 700, color }}>{val ?? '--'}</span>
            </div>
          ))}
          {pr.timestamp && (
            <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)' }}>
              {new Date(pr.timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
