import React from 'react'

const HEALTH_BADGE = {
  healthy:               { cls: 'badge-green',  label: 'Healthy' },
  nitrogen_deficiency:   { cls: 'badge-yellow', label: 'N Deficiency' },
  phosphorus_deficiency: { cls: 'badge-yellow', label: 'P Deficiency' },
  potassium_deficiency:  { cls: 'badge-yellow', label: 'K Deficiency' },
  iron_deficiency:       { cls: 'badge-yellow', label: 'Fe Deficiency' },
  disease_fungal:        { cls: 'badge-red',    label: 'Fungal Disease' },
  disease_bacterial:     { cls: 'badge-red',    label: 'Bacterial Disease' },
}

const MATURITY_BADGE = {
  immature:   { cls: 'badge-grey',   label: 'Immature' },
  vegetative: { cls: 'badge-blue',   label: 'Vegetative' },
  mature:     { cls: 'badge-green',  label: 'Mature' },
  overmature: { cls: 'badge-yellow', label: 'Overmature' },
}

const HEALTH_ICON = {
  healthy: '\u2714',
  nitrogen_deficiency: 'N',
  phosphorus_deficiency: 'P',
  potassium_deficiency: 'K',
  iron_deficiency: 'Fe',
  disease_fungal: '\u26a0',
  disease_bacterial: '\u26a0',
}

function PlantInspectionCard({ plant }) {
  const health   = HEALTH_BADGE[plant?.health_state] ?? { cls: 'badge-grey', label: plant?.health_state ?? '--' }
  const maturity = MATURITY_BADGE[plant?.status]      ?? { cls: 'badge-grey', label: plant?.status ?? '--' }
  const icon     = HEALTH_ICON[plant?.health_state]   ?? '?'
  const isHealthy = plant?.health_state === 'healthy'
  const hasDisease = plant?.health_state?.startsWith('disease')

  return (
    <div className="card" style={{ flex: 1, minWidth: 200, padding: '20px 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Position {plant?.position_index ?? '?'}
        </span>
        <div style={{
          width: 32, height: 32, borderRadius: 10,
          background: hasDisease ? 'var(--red-light)' : isHealthy ? 'var(--accent-subtle)' : 'var(--yellow-light)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, fontWeight: 700,
          color: hasDisease ? 'var(--red)' : isHealthy ? 'var(--accent)' : 'var(--yellow)',
        }}>
          {icon}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
        <span className={`badge ${health.cls}`}>{health.label}</span>
        <span className={`badge ${maturity.cls}`}>{maturity.label}</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {[
          { label: 'Canopy', val: plant?.canopy_area_cm2?.toFixed(1) ?? '--', unit: 'cm\u00b2' },
          { label: 'Height', val: plant?.height_cm?.toFixed(1) ?? '--', unit: 'cm' },
          { label: 'Leaves', val: plant?.leaf_count ?? '--', unit: '' },
          { label: 'Age',    val: plant?.days_since_planted ?? '--', unit: 'days' },
        ].map(({ label, val, unit }, i) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '9px 0',
            borderBottom: i < 3 ? '1px solid var(--border)' : 'none',
          }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {val} <span style={{ fontWeight: 400, color: 'var(--text-muted)', fontSize: 11 }}>{unit}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function InspectionViewer({ inspectionResult }) {
  const plants       = inspectionResult?.plants ?? Array(4).fill(null).map((_, i) => ({ position_index: i }))
  const scanNumber   = inspectionResult?.scan_number ?? 0
  const disease      = inspectionResult?.disease_detected ?? false
  const deficiencies = inspectionResult?.deficiency_trends ?? []

  const triggerInspection = () => {
    fetch('/api/trigger_inspection', { method: 'POST' })
      .then(r => r.json())
      .then(d => console.log('Inspection triggered:', d))
      .catch(e => console.error(e))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-secondary)' }}>
            Scan #{scanNumber}
          </span>
          {disease && (
            <span className="badge badge-red">Disease Detected</span>
          )}
          {deficiencies.length > 0 && (
            <span className="badge badge-yellow">
              Deficiency: {deficiencies.join(', ')}
            </span>
          )}
        </div>
        <button className="btn-primary" onClick={triggerInspection}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
          </svg>
          Trigger Inspection
        </button>
      </div>

      {/* Alert banners */}
      {disease && (
        <div className="alert-banner alert-banner-critical">
          <span style={{ fontSize: 16 }}>{'\u26a0'}</span>
          <span style={{ flex: 1, fontWeight: 500 }}>Disease detected during latest scan. Immediate attention recommended.</span>
        </div>
      )}
      {deficiencies.length > 0 && (
        <div className="alert-banner alert-banner-warning">
          <span style={{ fontSize: 16 }}>{'\u26a0'}</span>
          <span style={{ flex: 1, fontWeight: 500 }}>
            Nutrient deficiency trends: {deficiencies.join(', ')}. A/B ratio may need adjustment.
          </span>
        </div>
      )}

      {/* Plant cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        {plants.map((plant, i) => (
          <PlantInspectionCard key={i} plant={plant}/>
        ))}
      </div>
    </div>
  )
}
