import React, { useState } from 'react'

const SEVERITY_CONFIG = {
  info:     { bg: 'rgba(59,130,246,0.06)',  border: 'rgba(59,130,246,0.18)',  color: 'var(--blue)',   icon: '\u{2139}\ufe0f',  badgeCls: 'badge-blue' },
  warning:  { bg: 'rgba(245,158,11,0.06)',  border: 'rgba(245,158,11,0.18)',  color: 'var(--yellow)', icon: '\u26a0\ufe0f',    badgeCls: 'badge-yellow' },
  critical: { bg: 'rgba(239,68,68,0.06)',   border: 'rgba(239,68,68,0.18)',   color: 'var(--red)',    icon: '\u{1F6A8}',       badgeCls: 'badge-red' },
}

export default function AlertPanel({ alerts = [] }) {
  const [filter, setFilter]     = useState('all')
  const [localAlerts, setLocal] = useState(null)
  const [dismissedIds, setDismissed] = useState(new Set())

  const source = localAlerts ?? alerts
  const displayed = source
    .filter(a => filter === 'all' || a.severity === filter)
    .filter((_, i) => !dismissedIds.has(i))

  const clearAlerts = () => setLocal([])

  const counts = {
    all: source.length,
    info: source.filter(a => a.severity === 'info').length,
    warning: source.filter(a => a.severity === 'warning').length,
    critical: source.filter(a => a.severity === 'critical').length,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Filter bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div className="pill-group">
          {['all', 'info', 'warning', 'critical'].map(f => (
            <button key={f} className={`pill-btn ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
              style={{ textTransform: 'capitalize' }}>
              {f}
              {counts[f] > 0 && (
                <span style={{
                  marginLeft: 4, fontSize: 10, fontWeight: 700,
                  background: filter === f ? 'var(--accent-subtle)' : 'rgba(255,248,235,0.06)',
                  padding: '1px 5px', borderRadius: 'var(--radius-full)',
                  color: filter === f ? 'var(--accent)' : 'var(--text-muted)',
                }}>
                  {counts[f]}
                </span>
              )}
            </button>
          ))}
        </div>
        <button className="btn-ghost" onClick={clearAlerts} style={{ fontSize: 12, padding: '6px 14px' }}>
          Clear All
        </button>
      </div>

      {/* Alert count */}
      <div style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 500 }}>
        {displayed.length} alert{displayed.length !== 1 ? 's' : ''}
        {filter !== 'all' ? ` (${filter})` : ''}
      </div>

      {/* Alert list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 540, overflowY: 'auto' }}>
        {displayed.length === 0 ? (
          <div style={{
            padding: 48, textAlign: 'center', borderRadius: 'var(--radius-lg)',
            background: 'var(--glass-bg)', border: '1px solid var(--border)',
          }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>{'\u2705'}</div>
            <div style={{ fontSize: 14, color: 'var(--text-muted)', fontWeight: 500 }}>No alerts</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>System is running smoothly</div>
          </div>
        ) : (
          displayed.map((alert, i) => {
            const cfg = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.info
            return (
              <div key={i} className="fade-in" style={{
                background: cfg.bg,
                border: `1px solid ${cfg.border}`,
                borderRadius: 'var(--radius-md)',
                padding: '14px 18px',
                display: 'flex', gap: 14, alignItems: 'flex-start',
              }}>
                <span style={{ fontSize: 20, flexShrink: 0, lineHeight: 1 }}>{cfg.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontWeight: 600, fontSize: 13, color: cfg.color }}>
                        {alert.alert_type}
                      </span>
                      <span className={`badge ${cfg.badgeCls}`} style={{ fontSize: 9, padding: '1px 6px' }}>
                        {alert.severity}
                      </span>
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
                      {alert.timestamp ? new Date(alert.timestamp * 1000).toLocaleTimeString() : ''}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.5, marginBottom: 4 }}>
                    {alert.message}
                  </div>
                  {alert.recommended_action && (
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                      \u2192 {alert.recommended_action}
                    </div>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
