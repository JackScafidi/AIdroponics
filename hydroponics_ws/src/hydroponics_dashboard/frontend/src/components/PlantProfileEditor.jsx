import React, { useState, useEffect } from 'react'

const PROFILES = ['parsley', 'basil', 'cilantro', 'mint']
const STAGES   = ['seedling', 'vegetative', 'mature']

const PROFILE_ICONS = {
  parsley:  '\u{1F33F}',
  basil:    '\u{1F33F}',
  cilantro: '\u{1F331}',
  mint:     '\u{1F343}',
}

export default function PlantProfileEditor() {
  const [selected, setSelected] = useState('parsley')
  const [profile, setProfile]   = useState(null)
  const [loading, setLoading]   = useState(true)
  const [saved, setSaved]       = useState(false)

  useEffect(() => {
    setLoading(true)
    setSaved(false)
    fetch(`/api/plant_profiles/${selected}`)
      .then(r => r.json())
      .then(d => { setProfile(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [selected])

  const save = () => {
    fetch(`/api/plant_profiles/${selected}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    }).then(() => { setSaved(true); setTimeout(() => setSaved(false), 3000) })
  }

  const resetDefaults = () => {
    fetch(`/api/plant_profiles/${selected}/reset`, { method: 'POST' })
      .then(r => r.json())
      .then(d => { setProfile(d); setSaved(false) })
  }

  const setVal = (path, val) => {
    setProfile(prev => {
      const next = JSON.parse(JSON.stringify(prev))
      const keys = path.split('.')
      let obj = next
      for (let i = 0; i < keys.length - 1; i++) obj = obj[keys[i]]
      obj[keys[keys.length - 1]] = val
      return next
    })
  }

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
          {/* pH Targets */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--blue)' }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
                pH Targets by Stage
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
              {STAGES.map(stage => (
                <div key={stage}>
                  <label style={{
                    display: 'block', fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                    letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8,
                  }}>
                    {stage}
                  </label>
                  <input type="number" step="0.1" min="4" max="8"
                    value={profile?.growth_stages?.[stage]?.ph_target ?? 6.2}
                    onChange={e => setVal(`growth_stages.${stage}.ph_target`, parseFloat(e.target.value))}
                    style={{ width: '100%' }}/>
                </div>
              ))}
            </div>
          </div>

          {/* EC Targets */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)' }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
                EC Targets by Stage (mS/cm)
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
              {STAGES.map(stage => (
                <div key={stage}>
                  <label style={{
                    display: 'block', fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                    letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8,
                  }}>
                    {stage}
                  </label>
                  <input type="number" step="0.1" min="0" max="4"
                    value={profile?.growth_stages?.[stage]?.ec_target ?? 1.8}
                    onChange={e => setVal(`growth_stages.${stage}.ec_target`, parseFloat(e.target.value))}
                    style={{ width: '100%' }}/>
                </div>
              ))}
            </div>
          </div>

          {/* Harvest Thresholds */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--yellow)' }}/>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
                Harvest Thresholds
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
              {[
                { label: 'Min canopy area', unit: 'cm\u00b2', path: 'harvest.min_canopy_area_cm2', min: 0, max: 500, step: 5 },
                { label: 'Min days between cuts', unit: 'days', path: 'harvest.min_days_between_cuts', min: 1, max: 90, step: 1 },
                { label: 'Max cut cycles', unit: 'cycles', path: 'harvest.max_cut_cycles', min: 1, max: 10, step: 1 },
              ].map(({ label, unit, path, min, max, step }) => (
                <div key={path}>
                  <label style={{
                    display: 'block', fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                    letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 4,
                  }}>
                    {label}
                  </label>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 8 }}>{unit}</div>
                  <input type="number" min={min} max={max} step={step}
                    value={path.split('.').reduce((o, k) => o?.[k], profile) ?? 0}
                    onChange={e => setVal(path, parseFloat(e.target.value))}
                    style={{ width: '100%' }}/>
                </div>
              ))}
            </div>
          </div>

          {/* Save / Reset */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <button className="btn-success" onClick={save}
              style={{ fontSize: 13, padding: '10px 24px' }}>
              {saved ? '\u2713 Saved' : 'Save Profile'}
            </button>
            <button className="btn-ghost" onClick={resetDefaults}
              style={{ fontSize: 13, padding: '10px 20px' }}>
              Reset to Defaults
            </button>
          </div>
        </>
      )}
    </div>
  )
}
