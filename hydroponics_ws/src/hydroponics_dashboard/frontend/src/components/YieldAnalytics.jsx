import React, { useState, useEffect } from 'react'

function StatCard({ label, value, unit, color, icon }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 150, padding: '20px 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>
            {label}
          </div>
          <div style={{ fontSize: 26, fontWeight: 700, color: color ?? 'var(--accent)', letterSpacing: '-0.02em' }}>
            {value}
          </div>
          {unit && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{unit}</div>}
        </div>
        {icon && (
          <div style={{
            width: 40, height: 40, borderRadius: 12,
            background: `${color ?? 'var(--accent)'}12`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18,
          }}>
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}

const PUMP_COLORS = {
  ph_up:      'var(--blue)',
  ph_down:    'var(--purple)',
  nutrient_a: 'var(--accent)',
  nutrient_b: 'var(--teal)',
}

const PUMP_LABELS = {
  ph_up:      'pH Up',
  ph_down:    'pH Down',
  nutrient_a: 'Nutrient A',
  nutrient_b: 'Nutrient B',
}

export default function YieldAnalytics() {
  const [dosingData, setDosingData]   = useState([])
  const [topoffData, setTopoffData]   = useState([])
  const [range, setRange]             = useState('7d')
  const [loading, setLoad]            = useState(true)

  useEffect(() => {
    setLoad(true)
    Promise.all([
      fetch(`/api/dosing_history?range=${range}`).then(r => r.json()),
      fetch('/api/water/topoff_history').then(r => r.json()),
    ])
      .then(([d, w]) => {
        setDosingData(d?.events ?? [])
        setTopoffData(w?.events ?? [])
        setLoad(false)
      })
      .catch(() => setLoad(false))
  }, [range])

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
      <span className="loading-pulse" style={{ color: 'var(--text-muted)', fontSize: 14 }}>Loading data...</span>
    </div>
  )

  // Dosing stats by pump
  const pumpTotals = {}
  const pumpCounts = {}
  for (const e of dosingData) {
    const p = e.pump_id ?? 'unknown'
    pumpTotals[p] = (pumpTotals[p] ?? 0) + (e.dose_mL ?? 0)
    pumpCounts[p] = (pumpCounts[p] ?? 0) + 1
  }
  const maxDose = Math.max(...Object.values(pumpTotals), 1)

  // Top-off stats
  const totalTopoff = topoffData.reduce((s, t) => s + (t.volume_added_mL ?? 0) / 1000, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 16 }}>
        <StatCard label="Dosing Events" value={dosingData.length} color="var(--blue)"/>
        <StatCard label="Total Volume" value={`${Object.values(pumpTotals).reduce((a, b) => a + b, 0).toFixed(1)} mL`} color="var(--accent)"/>
        <StatCard label="Top-off Events" value={topoffData.length} color="var(--teal)"/>
        <StatCard label="Water Added" value={`${totalTopoff.toFixed(2)} L`} color="var(--orange)"/>
      </div>

      {/* Range selector */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <div className="pill-group">
          {['1h', '24h', '7d', '30d'].map(r => (
            <button key={r} className={`pill-btn ${range === r ? 'active' : ''}`}
              onClick={() => setRange(r)}>
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Dosing bar chart */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 18 }}>
          Dosing Volume by Pump
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {['ph_up', 'ph_down', 'nutrient_a', 'nutrient_b'].map(pump => {
            const total = pumpTotals[pump] ?? 0
            const count = pumpCounts[pump] ?? 0
            const color = PUMP_COLORS[pump]
            return (
              <div key={pump} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 4, height: 32, borderRadius: 2, background: color, flexShrink: 0 }}/>
                <span style={{ width: 90, fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>
                  {PUMP_LABELS[pump]}
                </span>
                <div style={{ flex: 1, height: 20, background: 'rgba(255,248,235,0.04)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', borderRadius: 'var(--radius-sm)',
                    background: color,
                    width: `${(total / maxDose) * 100}%`,
                    minWidth: total > 0 ? 4 : 0,
                    transition: 'width 0.5s ease',
                    opacity: 0.7,
                  }}/>
                </div>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', width: 70, textAlign: 'right' }}>
                  {total.toFixed(1)} mL
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', width: 50 }}>
                  {count}x
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Dosing log table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '18px 24px 0', fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 14 }}>
          Dosing Log
        </div>
        <table className="data-table">
          <thead>
            <tr>
              {['Time', 'Pump', 'Volume', 'Reason'].map(h => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dosingData.slice(-25).reverse().map((e, i) => (
              <tr key={i}>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '--'}
                </td>
                <td>
                  <span className="badge badge-blue">{PUMP_LABELS[e.pump_id] ?? e.pump_id ?? '--'}</span>
                </td>
                <td style={{ fontWeight: 600, color: PUMP_COLORS[e.pump_id] ?? 'var(--accent)' }}>
                  {e.dose_mL?.toFixed(2) ?? '--'} mL
                </td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {e.reason ?? '--'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Top-off log */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '18px 24px 0', fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 14 }}>
          Water Top-off Log
        </div>
        <table className="data-table">
          <thead>
            <tr>
              {['Time', 'Amount Added', 'Level Before', 'Level After'].map(h => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {topoffData.slice(-15).reverse().map((e, i) => (
              <tr key={i}>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '--'}
                </td>
                <td style={{ fontWeight: 600, color: 'var(--teal)' }}>
                  {e.volume_added_mL != null ? (e.volume_added_mL / 1000).toFixed(3) : '--'} L
                </td>
                <td style={{ color: 'var(--text-muted)' }}>
                  {e.level_before_percent?.toFixed(0) ?? '--'}%
                </td>
                <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                  {e.level_after_percent?.toFixed(0) ?? '--'}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
