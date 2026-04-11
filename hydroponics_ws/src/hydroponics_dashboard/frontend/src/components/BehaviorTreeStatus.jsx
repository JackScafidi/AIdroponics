import React from 'react'

const SEVERITY_COLOR = {
  0: 'var(--accent)',
  1: 'var(--yellow)',
  2: 'var(--red)',
}

const SEVERITY_LABEL = {
  0: 'INFO',
  1: 'WARNING',
  2: 'CRITICAL',
}

const SEVERITY_BG = {
  0: 'var(--accent-subtle)',
  1: 'var(--yellow-light)',
  2: 'var(--red-light)',
}

export default function BehaviorTreeStatus({ diagnosticReport }) {
  const dr = diagnosticReport ?? {}
  const severity      = dr.overall_severity ?? 0
  const activeRules   = dr.active_rules ?? []
  const symptoms      = dr.detected_symptoms ?? []
  const recommendations = dr.recommendations ?? []
  const color         = SEVERITY_COLOR[severity] ?? 'var(--text-muted)'
  const bg            = SEVERITY_BG[severity] ?? 'rgba(255,248,235,0.04)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Status cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
        <div className="card" style={{ padding: '20px 24px' }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8 }}>
            Overall Severity
          </div>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '6px 14px', borderRadius: 'var(--radius-sm)',
            background: bg,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%', background: color,
              boxShadow: severity === 0 ? `0 0 8px ${color}` : 'none',
            }}/>
            <span style={{ fontSize: 16, fontWeight: 700, color }}>
              {SEVERITY_LABEL[severity] ?? 'UNKNOWN'}
            </span>
          </div>
        </div>
        <div className="card" style={{ padding: '20px 24px' }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8 }}>
            Probe Summary
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[
              { label: 'pH',   value: dr.probe_ph   != null ? dr.probe_ph.toFixed(2)   : '--', color: 'var(--blue)' },
              { label: 'EC',   value: dr.probe_ec   != null ? `${dr.probe_ec.toFixed(2)} mS/cm` : '--', color: 'var(--teal)' },
              { label: 'Temp', value: dr.probe_temp != null ? `${dr.probe_temp.toFixed(1)}\u00b0C` : '--', color: 'var(--orange)' },
            ].map(({ label, value, color: c }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ fontWeight: 600, color: c, fontFamily: "'SF Mono', 'Fira Code', monospace" }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Diagnostics detail */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Detected symptoms */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
              Detected Symptoms
            </span>
            <span style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 'var(--radius-full)',
              background: symptoms.length > 0 ? 'rgba(239,68,68,0.1)' : 'rgba(74,222,128,0.08)',
              color: symptoms.length > 0 ? 'var(--red)' : 'var(--accent)',
              fontWeight: 600,
            }}>
              {symptoms.length}
            </span>
          </div>
          {symptoms.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No symptoms detected
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {symptoms.map((s, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                  background: 'rgba(239,68,68,0.06)',
                  border: '1px solid rgba(239,68,68,0.12)',
                }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--red)', marginTop: 4, flexShrink: 0 }}/>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{s}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recommendations */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
              Recommendations
            </span>
            <span style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 'var(--radius-full)',
              background: 'rgba(59,130,246,0.1)',
              color: 'var(--blue)',
              fontWeight: 600,
            }}>
              {recommendations.length}
            </span>
          </div>
          {recommendations.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No recommendations
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {recommendations.map((r, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                  background: 'rgba(59,130,246,0.06)',
                  border: '1px solid rgba(59,130,246,0.12)',
                }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--blue)', marginTop: 4, flexShrink: 0 }}/>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Active rules */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>
          Active Diagnostic Rules
        </div>
        {activeRules.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--text-muted)', fontStyle: 'italic' }}>
            No active rules \u2014 all parameters nominal
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {activeRules.map((rule, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '7px 12px', borderRadius: 'var(--radius-sm)',
                background: 'rgba(255,248,235,0.03)',
                border: '1px solid var(--border)',
              }}>
                <span style={{
                  fontSize: 9, padding: '2px 6px', borderRadius: 'var(--radius-full)',
                  background: 'rgba(245,158,11,0.1)', color: 'var(--yellow)',
                  fontWeight: 700, letterSpacing: '0.03em', flexShrink: 0,
                }}>
                  RULE
                </span>
                <span style={{
                  fontSize: 12, fontFamily: "'SF Mono', 'Fira Code', monospace",
                  color: 'var(--text-secondary)',
                }}>
                  {rule}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
