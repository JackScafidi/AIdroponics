import React, { useState } from 'react'

const NDVI_STATUS = (v) => {
  if (v == null) return { cls: 'badge-grey', label: '--' }
  if (v >= 0.3) return { cls: 'badge-green', label: 'Healthy' }
  if (v >= 0.2) return { cls: 'badge-yellow', label: 'Warning' }
  return { cls: 'badge-red', label: 'Critical' }
}

function MetricRow({ label, value, unit, color, last }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '9px 0',
      borderBottom: last ? 'none' : '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: color ?? 'var(--text-primary)' }}>
        {value ?? '--'}{value != null && unit ? <span style={{ fontWeight: 400, color: 'var(--text-muted)', fontSize: 11, marginLeft: 3 }}>{unit}</span> : null}
      </span>
    </div>
  )
}

export default function InspectionViewer({ plantMeasurement, ndviReading, authToken }) {
  const [capturing, setCapturing] = useState(false)
  const [captureStatus, setCaptureStatus] = useState('')

  const pm = plantMeasurement ?? {}
  const nr = ndviReading ?? {}

  const ndviBadge = NDVI_STATUS(nr.mean_ndvi)
  const trendUp   = nr.ndvi_trend_slope != null && nr.ndvi_trend_slope > 0

  const captureVision = () => {
    if (!authToken) return
    setCapturing(true)
    fetch('/api/controls/capture_vision', {
      method: 'POST',
      headers: { Authorization: `Bearer ${authToken}` },
    })
      .then(r => r.json())
      .then(() => { setCaptureStatus('Capture triggered'); setTimeout(() => setCaptureStatus(''), 3000) })
      .catch(() => { setCaptureStatus('Capture failed'); setTimeout(() => setCaptureStatus(''), 3000) })
      .finally(() => setCapturing(false))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className={`badge ${ndviBadge.cls}`}>NDVI: {ndviBadge.label}</span>
          {nr.ndvi_trend_slope != null && (
            <span className={`badge ${trendUp ? 'badge-green' : 'badge-red'}`}>
              Trend: {trendUp ? '\u2191' : '\u2193'} {Math.abs(nr.ndvi_trend_slope * 1000).toFixed(2)}\u00d710\u207b\u00b3
            </span>
          )}
          {pm.timestamp && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Last scan: {new Date(pm.timestamp).toLocaleTimeString()}
            </span>
          )}
        </div>
        {authToken && (
          <button className="btn-primary" onClick={captureVision} disabled={capturing}
            style={{ opacity: capturing ? 0.6 : 1 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
            </svg>
            {capturing ? 'Capturing...' : 'Capture Vision'}
          </button>
        )}
      </div>

      {captureStatus && (
        <div className="alert-banner alert-banner-info">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
          </svg>
          <span style={{ fontWeight: 500 }}>{captureStatus}</span>
        </div>
      )}

      {/* Main grid: NDVI + Plant measurement */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* NDVI card */}
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>
            NDVI Analysis
          </div>
          <MetricRow label="Mean NDVI"   value={nr.mean_ndvi?.toFixed(3)}   color={nr.mean_ndvi >= 0.3 ? 'var(--accent)' : nr.mean_ndvi >= 0.2 ? 'var(--yellow)' : 'var(--red)'}/>
          <MetricRow label="Median NDVI" value={nr.median_ndvi?.toFixed(3)} color="var(--teal)"/>
          <MetricRow label="Std Deviation" value={nr.std_dev_ndvi?.toFixed(3)} color="var(--blue)"/>
          <MetricRow label="Trend Slope"
            value={nr.ndvi_trend_slope != null ? `${nr.ndvi_trend_slope >= 0 ? '+' : ''}${(nr.ndvi_trend_slope * 1000).toFixed(2)}\u00d710\u207b\u00b3` : null}
            color={nr.ndvi_trend_slope >= 0 ? 'var(--accent)' : 'var(--red)'}/>
          <MetricRow label="Trend Window" value={nr.trend_window_size} unit="readings" last/>
        </div>

        {/* Plant measurement card */}
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>
            Plant Measurement
          </div>
          <MetricRow label="Canopy Area"  value={pm.canopy_area_cm2?.toFixed(1)} unit="cm\u00b2" color="var(--accent)"/>
          <MetricRow label="Height"       value={pm.height_cm?.toFixed(1)} unit="cm" color="var(--blue)"/>
          <MetricRow label="Canopy Width" value={pm.canopy_width_cm?.toFixed(1)} unit="cm" color="var(--teal)" last/>
        </div>
      </div>

      {/* Visual symptoms */}
      {(pm.visual_symptoms ?? []).length > 0 && (
        <div className="alert-banner alert-banner-warning">
          <span style={{ fontSize: 16 }}>{'\u26a0'}</span>
          <span style={{ flex: 1, fontWeight: 500 }}>
            Visual symptoms detected: {pm.visual_symptoms.join(', ')}
          </span>
        </div>
      )}

      {/* NDVI health bar */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>
          NDVI Health Gauge
        </div>
        <div style={{ position: 'relative', height: 12, background: 'rgba(255,248,235,0.06)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
          {/* Color zones */}
          <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: '20%', background: 'rgba(239,68,68,0.3)', borderRadius: '6px 0 0 6px' }}/>
          <div style={{ position: 'absolute', left: '20%', top: 0, height: '100%', width: '10%', background: 'rgba(245,158,11,0.3)' }}/>
          <div style={{ position: 'absolute', left: '30%', top: 0, height: '100%', width: '70%', background: 'rgba(22,163,74,0.2)', borderRadius: '0 6px 6px 0' }}/>
          {/* Indicator */}
          {nr.mean_ndvi != null && (
            <div style={{
              position: 'absolute', top: -2, height: 16, width: 4, borderRadius: 2,
              background: 'white',
              left: `calc(${Math.min(100, Math.max(0, nr.mean_ndvi * 100))}% - 2px)`,
              transition: 'left 0.5s ease',
              boxShadow: '0 0 6px rgba(255,255,255,0.5)',
            }}/>
          )}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
          <span>0.0 Critical</span>
          <span>0.2 Warning</span>
          <span>0.3 Healthy</span>
          <span>1.0</span>
        </div>
      </div>
    </div>
  )
}
