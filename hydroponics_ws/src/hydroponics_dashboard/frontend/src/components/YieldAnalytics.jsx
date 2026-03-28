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

export default function YieldAnalytics() {
  const [data, setData]    = useState(null)
  const [loading, setLoad] = useState(true)

  useEffect(() => {
    fetch('/api/yield_analytics')
      .then(r => r.json())
      .then(d => { setData(d); setLoad(false) })
      .catch(() => setLoad(false))
  }, [])

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
      <span className="loading-pulse" style={{ color: 'var(--text-muted)', fontSize: 14 }}>Loading yield data...</span>
    </div>
  )
  if (!data) return (
    <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)', fontSize: 14 }}>
      No yield data available yet.
    </div>
  )

  const harvests = data.harvests ?? []
  const totalW   = harvests.reduce((s, h) => s + (h.weight_grams ?? 0), 0)
  const avgW     = harvests.length > 0 ? totalW / harvests.length : 0
  const maxBarW  = Math.max(...harvests.map(h => h.weight_grams ?? 0), 1)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 16 }}>
        <StatCard label="Total Harvests" value={harvests.length} color="var(--blue)"/>
        <StatCard label="Total Weight" value={`${totalW.toFixed(1)}g`} color="var(--accent)"/>
        <StatCard label="Avg per Harvest" value={`${avgW.toFixed(1)}g`} color="var(--yellow)"/>
        {data.revenue_usd != null && (
          <StatCard label="Est. Revenue" value={`$${data.revenue_usd?.toFixed(2)}`} color="var(--purple)"/>
        )}
      </div>

      {/* Bar chart */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 18 }}>
          Weight Per Harvest
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 340, overflowY: 'auto' }}>
          {harvests.slice(-30).map((h, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', width: 80, flexShrink: 0, fontWeight: 500 }}>
                P{h.position_index} {h.action_type === 'cut' ? '\u2702' : '\u267b'}
              </span>
              <div style={{ flex: 1, height: 20, background: 'rgba(255,248,235,0.04)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                <div style={{
                  height: '100%', borderRadius: 'var(--radius-sm)',
                  background: h.action_type === 'cut'
                    ? 'linear-gradient(90deg, rgba(22,163,74,0.2), var(--accent))'
                    : 'linear-gradient(90deg, rgba(59,130,246,0.2), var(--blue))',
                  width: `${((h.weight_grams ?? 0) / maxBarW) * 100}%`,
                  minWidth: 4,
                  transition: 'width 0.5s ease',
                }}/>
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', width: 55, textAlign: 'right' }}>
                {h.weight_grams?.toFixed(1) ?? '--'} g
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Harvest log table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '18px 24px 0', fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 14 }}>
          Harvest Log
        </div>
        <table className="data-table">
          <thead>
            <tr>
              {['Date', 'Position', 'Type', 'Weight', 'Cut #'].map(h => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {harvests.slice(-20).reverse().map((h, i) => (
              <tr key={i}>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {h.timestamp ? new Date(h.timestamp).toLocaleDateString() : '--'}
                </td>
                <td style={{ fontWeight: 500 }}>Position {h.position_index ?? '--'}</td>
                <td>
                  <span className={`badge ${h.action_type === 'cut' ? 'badge-green' : 'badge-blue'}`}>
                    {h.action_type ?? '--'}
                  </span>
                </td>
                <td style={{ fontWeight: 600, color: 'var(--accent)' }}>
                  {h.weight_grams?.toFixed(1) ?? '--'} g
                </td>
                <td style={{ color: 'var(--text-muted)' }}>{h.cut_cycle_number ?? '--'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
