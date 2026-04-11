import React, { useState, useEffect } from 'react'

const PROFILES = ['basil', 'mint', 'parsley', 'rosemary']

const PROFILE_ICONS = {
  basil:    '\u{1F33F}',
  mint:     '\u{1F343}',
  parsley:  '\u{1F33F}',
  rosemary: '\u{1F331}',
}

function RangeRow({ label, idealMin, idealMax, acceptMin, acceptMax }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '8px 0', borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, width: 120 }}>{label}</span>
      <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
        {idealMin} – {idealMax}
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400, marginLeft: 6 }}>
          ideal
        </span>
      </span>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {acceptMin} – {acceptMax}
        <span style={{ fontSize: 10, marginLeft: 4 }}>accept</span>
      </span>
    </div>
  )
}

export default function PlantProfileEditor() {
  const [selected, setSelected] = useState('basil')
  const [profile, setProfile]   = useState(null)
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/profiles/${selected}`)
      .then(r => r.json())
      .then(d => { setProfile(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [selected])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Profile selector */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {PROFILES.map(p => (
          <button key={p} onClick={() => setSelected(p)}
            className={selected === p ? 'btn-primary' : 'btn-ghost'}
            style={{
              textTransform: 'capitalize', fontSize: 13, padding: '8px 18px',
              borderRadius: 'var(--radius-sm)',
            }}>
            <span style={{ fontSize: 15 }}>{PROFILE_ICONS[p]}</span>
            {p}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <span className="loading-pulse" style={{ color: 'var(--text-muted)', fontSize: 14 }}>Loading profile...</span>
        </div>
      ) : !profile ? (
        <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
          Failed to load profile.
        </div>
      ) : (
        <>
          {/* Header */}
          <div className="card" style={{ padding: '20px 24px' }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
              {profile.display_name ?? profile.name}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              A:B nutrient ratio — {profile.nutrient_ab_ratio ?? 1.0}:1
            </div>
          </div>

          {/* Water chemistry ranges */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--blue)' }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
                Water Chemistry
              </span>
            </div>
            <RangeRow
              label="pH"
              idealMin={profile.ph?.ideal?.[0]}
              idealMax={profile.ph?.ideal?.[1]}
              acceptMin={profile.ph?.acceptable?.[0]}
              acceptMax={profile.ph?.acceptable?.[1]}
            />
            <RangeRow
              label="EC (mS/cm)"
              idealMin={profile.ec_mS_cm?.ideal?.[0]}
              idealMax={profile.ec_mS_cm?.ideal?.[1]}
              acceptMin={profile.ec_mS_cm?.acceptable?.[0]}
              acceptMax={profile.ec_mS_cm?.acceptable?.[1]}
            />
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 0',
            }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, width: 120 }}>Temp (\u00b0C)</span>
              <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
                {profile.temperature_C?.ideal?.[0]} – {profile.temperature_C?.ideal?.[1]}
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400, marginLeft: 6 }}>ideal</span>
              </span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {profile.temperature_C?.acceptable?.[0]} – {profile.temperature_C?.acceptable?.[1]}
                <span style={{ fontSize: 10, marginLeft: 4 }}>accept</span>
              </span>
            </div>
          </div>

          {/* NDVI thresholds */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)' }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
                NDVI Thresholds
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
              {[
                { label: 'Healthy Min', key: 'healthy_min', color: 'var(--accent)' },
                { label: 'Warning Threshold', key: 'warning_threshold', color: 'var(--yellow)' },
                { label: 'Critical Threshold', key: 'critical_threshold', color: 'var(--red)' },
              ].map(({ label, key, color }) => (
                <div key={key} style={{
                  padding: '16px 20px', borderRadius: 'var(--radius-md)',
                  background: 'rgba(255,248,235,0.03)',
                  border: `1px solid ${color}22`,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 6 }}>
                    {label}
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 700, color }}>
                    {profile.ndvi?.[key]?.toFixed(2) ?? '--'}
                  </div>
                </div>
              ))}
            </div>

            {/* NDVI visual bar */}
            <div style={{ marginTop: 16 }}>
              <div style={{ position: 'relative', height: 10, background: 'rgba(255,248,235,0.06)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${(profile.ndvi?.critical_threshold ?? 0.1) * 100}%`, background: 'rgba(239,68,68,0.5)', borderRadius: '6px 0 0 6px' }}/>
                <div style={{ position: 'absolute', left: `${(profile.ndvi?.critical_threshold ?? 0.1) * 100}%`, top: 0, height: '100%', width: `${((profile.ndvi?.warning_threshold ?? 0.2) - (profile.ndvi?.critical_threshold ?? 0.1)) * 100}%`, background: 'rgba(245,158,11,0.5)' }}/>
                <div style={{ position: 'absolute', left: `${(profile.ndvi?.warning_threshold ?? 0.2) * 100}%`, top: 0, height: '100%', width: `${((profile.ndvi?.healthy_min ?? 0.3) - (profile.ndvi?.warning_threshold ?? 0.2)) * 100}%`, background: 'rgba(245,158,11,0.3)' }}/>
                <div style={{ position: 'absolute', left: `${(profile.ndvi?.healthy_min ?? 0.3) * 100}%`, top: 0, height: '100%', right: 0, background: 'rgba(22,163,74,0.4)', borderRadius: '0 6px 6px 0' }}/>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--text-muted)' }}>
                <span>0.0</span>
                <span>Critical {profile.ndvi?.critical_threshold?.toFixed(2)}</span>
                <span>Warning {profile.ndvi?.warning_threshold?.toFixed(2)}</span>
                <span>Healthy {profile.ndvi?.healthy_min?.toFixed(2)}</span>
                <span>1.0</span>
              </div>
            </div>
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '0 4px' }}>
            Profiles are read-only in V0.1. Edit <code style={{ fontFamily: 'monospace', fontSize: 11 }}>plant_library.yaml</code> and restart to change thresholds.
          </div>
        </>
      )}
    </div>
  )
}
