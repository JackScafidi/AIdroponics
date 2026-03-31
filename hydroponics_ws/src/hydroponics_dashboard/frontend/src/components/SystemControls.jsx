import React, { useState } from 'react'

/* ── Transport/Action button row (matching mockup 3) ─────────────────────── */
function ActionRow({ icon, label, active, onClick, variant = 'default' }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%', padding: '16px 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexDirection: 'column', gap: 6,
        background: active ? 'var(--accent-subtle)' : 'var(--bg-card)',
        border: `1px solid ${active ? 'rgba(22,163,74,0.2)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)',
        color: active ? 'var(--accent)' : 'var(--text-secondary)',
        fontSize: 13, fontWeight: active ? 600 : 500,
        transition: 'all 0.15s ease',
        boxShadow: active ? '0 2px 8px rgba(22,163,74,0.1)' : 'var(--shadow-sm)',
        cursor: 'pointer',
      }}
    >
      <span style={{ fontSize: 22 }}>{icon}</span>
      <span>{label}</span>
    </button>
  )
}

/* ── Icons ────────────────────────────────────────────────────────────────── */
const TransportIcons = {
  WORK: '\u{1F527}',     // wrench
  GROW: '\u{1F331}',     // seedling
  INSPECT: '\u{1F50D}',  // magnifying glass
  HOME: '\u{1F3E0}',     // home
}

const ActionIcons = {
  inspect: '\u{1F50E}',  // magnifying glass tilted
  harvest: '\u2702',      // scissors
  dose: '\u{1F9EA}',     // test tube
}

export default function SystemControls({ authToken, onLogin, onLogout }) {
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [loggingIn, setLoggingIn] = useState(false)

  const [doseAmounts, setDoseAmounts] = useState({ ph_up: '1.0', ph_down: '1.0', nutrient_a: '2.0', nutrient_b: '2.0' })
  const [lightIntensity, setLightIntensity] = useState(80)
  const [inspectionLight, setInspectionLight] = useState(false)
  const [growthStage, setGrowthStage] = useState('vegetative')
  const [confirmReset, setConfirmReset] = useState(false)
  const [status, setStatus] = useState('')
  const [activeTransport, setActiveTransport] = useState(null)

  const feedback = (msg) => { setStatus(msg); setTimeout(() => setStatus(''), 3000) }

  const api = (path, method = 'POST', body = null) =>
    fetch(path, {
      method,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    }).then(r => {
      if (r.status === 401) {
        onLogout()
        throw new Error('Session expired')
      }
      return r.json()
    })

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoggingIn(true)
    setLoginError('')
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (res.ok) {
        const data = await res.json()
        onLogin(data.token)
        setPassword('')
      } else if (res.status === 401) {
        setLoginError('Incorrect password')
      } else {
        setLoginError(`Server error (${res.status})`)
      }
    } catch {
      setLoginError('Cannot reach backend \u2014 is the server running?')
    }
    setLoggingIn(false)
  }

  /* ── Login gate ──────────────────────────────────────────────────────────── */
  if (!authToken) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        minHeight: 400,
      }}>
        <div style={{
          width: '100%', maxWidth: 380, padding: 36,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg, 16px)',
          boxShadow: 'var(--shadow-lg, 0 8px 32px rgba(0,0,0,0.2))',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent, #4ade80)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary, #fff)' }}>
              Owner Access
            </span>
          </div>
          <p style={{
            fontSize: 13, color: 'var(--text-muted, rgba(255,255,255,0.4))',
            margin: '0 0 24px', lineHeight: 1.5,
          }}>
            Enter the system password to unlock controls. Viewers can see all data but cannot operate the system.
          </p>
          <form onSubmit={handleLogin}>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password"
              autoFocus
              style={{
                width: '100%', padding: '12px 16px',
                fontSize: 14, borderRadius: 'var(--radius-md, 10px)',
                background: 'var(--bg-app, #121010)',
                border: loginError
                  ? '1px solid var(--red, #ef4444)'
                  : '1px solid var(--border, rgba(255,255,255,0.08))',
                color: 'var(--text-primary, #fff)',
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.15s ease',
              }}
            />
            {loginError && (
              <div style={{
                fontSize: 12, color: 'var(--red, #ef4444)',
                marginTop: 8, fontWeight: 500,
              }}>
                {loginError}
              </div>
            )}
            <button
              type="submit"
              disabled={loggingIn || !password}
              className="btn-primary"
              style={{
                width: '100%', padding: '12px 20px',
                fontSize: 14, fontWeight: 600, marginTop: 16,
                borderRadius: 'var(--radius-md, 10px)',
                opacity: loggingIn || !password ? 0.5 : 1,
                cursor: loggingIn || !password ? 'not-allowed' : 'pointer',
              }}
            >
              {loggingIn ? 'Authenticating...' : 'Unlock Controls'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  /* ── Authenticated controls ──────────────────────────────────────────────── */
  const emergencyStop = () => {
    if (!window.confirm('Confirm EMERGENCY STOP \u2014 all operations will halt immediately.')) return
    api('/api/emergency_stop').then(() => feedback('Emergency stop sent'))
  }

  const transportTo = (pos) => {
    setActiveTransport(pos)
    api('/api/transport_to', 'POST', { position: pos })
      .then(() => { feedback(`Transport \u2192 ${pos}`); setTimeout(() => setActiveTransport(null), 2000) })
  }

  const forceDose = (pump_id) => {
    const ml = parseFloat(doseAmounts[pump_id])
    if (isNaN(ml) || ml <= 0) { feedback('Invalid dose amount'); return }
    api('/api/force_dose', 'POST', { pump_id, amount_ml: ml })
      .then(() => feedback(`Dosed ${pump_id}: ${ml} mL`))
  }

  const setLight = (intensity) => {
    api('/api/set_grow_light_intensity', 'POST', { intensity_percent: intensity })
      .then(() => feedback(`Grow light \u2192 ${intensity}%`))
  }

  const triggerInspection = () => {
    api('/api/trigger_inspection').then(() => feedback('Inspection triggered'))
  }

  const triggerHarvest = () => {
    api('/api/trigger_harvest', 'POST').then(() => feedback('Harvest triggered'))
  }

  const applyGrowthStage = () => {
    api('/api/set_growth_stage', 'POST', { stage: growthStage })
      .then(() => feedback(`Growth stage \u2192 ${growthStage}`))
  }

  const resetCropCycle = () => {
    api('/api/reset_crop_cycle').then(() => { feedback('Crop cycle reset'); setConfirmReset(false) })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Auth status bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 16px', borderRadius: 'var(--radius-md, 10px)',
        background: 'rgba(74,222,128,0.06)',
        border: '1px solid rgba(74,222,128,0.12)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <span style={{ fontSize: 12, fontWeight: 600, color: '#4ade80' }}>Owner access active</span>
        </div>
        <button
          onClick={onLogout}
          style={{
            fontSize: 12, fontWeight: 500, padding: '4px 12px',
            borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)',
            background: 'transparent', color: 'var(--text-muted, rgba(255,255,255,0.4))',
            cursor: 'pointer',
          }}
        >
          Lock
        </button>
      </div>

      {/* Status feedback */}
      {status && (
        <div className="alert-banner alert-banner-info" style={{ animation: 'fadeIn 0.2s ease' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
          </svg>
          <span style={{ fontWeight: 500 }}>{status}</span>
        </div>
      )}

      {/* Emergency stop */}
      <div style={{ display: 'flex', gap: 12 }}>
        <button className="btn-danger" onClick={emergencyStop}
          style={{ padding: '12px 28px', fontSize: 14, fontWeight: 700, borderRadius: 'var(--radius-md)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>
          </svg>
          EMERGENCY STOP
        </button>
      </div>

      {/* Transport Controls (matching mockup 3 layout) */}
      <div>
        <div className="section-label">Transport Controls</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <ActionRow icon={TransportIcons.WORK} label="Move to WORK"
            active={activeTransport === 'WORK'} onClick={() => transportTo('WORK')}/>
          <ActionRow icon={TransportIcons.GROW} label="Move to GROW"
            active={activeTransport === 'GROW'} onClick={() => transportTo('GROW')}/>
          <ActionRow icon={TransportIcons.INSPECT} label="Move to INSPECT"
            active={activeTransport === 'INSPECT'} onClick={() => transportTo('INSPECT')}/>
          <ActionRow icon={TransportIcons.HOME} label="Home Rail"
            active={activeTransport === 'HOME'} onClick={() => transportTo('HOME')}/>
        </div>
      </div>

      {/* Actions */}
      <div>
        <div className="section-label">Actions</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <ActionRow icon={ActionIcons.inspect} label="Trigger Inspection" onClick={triggerInspection}/>
          <ActionRow icon={ActionIcons.harvest} label="Trigger Harvest" onClick={triggerHarvest}/>
          <ActionRow icon={ActionIcons.dose} label="Force pH Dose"
            onClick={() => forceDose('ph_up')}/>
        </div>
      </div>

      {/* Manual Dosing */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 18 }}>
          Manual Nutrient Dosing
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {[
            { id: 'ph_up',      label: 'pH Up',      color: 'var(--blue)' },
            { id: 'ph_down',    label: 'pH Down',     color: 'var(--purple)' },
            { id: 'nutrient_a', label: 'Nutrient A',  color: 'var(--accent)' },
            { id: 'nutrient_b', label: 'Nutrient B',  color: 'var(--teal)' },
          ].map(({ id, label, color }) => (
            <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 4, height: 32, borderRadius: 2, background: color, flexShrink: 0 }}/>
              <span style={{ width: 90, fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>{label}</span>
              <input
                type="number" min="0.1" max="50" step="0.1"
                value={doseAmounts[id]}
                onChange={e => setDoseAmounts(prev => ({ ...prev, [id]: e.target.value }))}
                style={{ width: 80 }}
              />
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>mL</span>
              <button className="btn-primary" style={{ padding: '6px 16px', fontSize: 12 }}
                onClick={() => forceDose(id)}>
                Dose
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Lighting */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 18 }}>
          Lighting
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, width: 120 }}>Grow Intensity</span>
            <input type="range" min="0" max="100" value={lightIntensity}
              onChange={e => setLightIntensity(parseInt(e.target.value))}
              style={{ flex: 1, maxWidth: 200 }}/>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--yellow)', width: 40 }}>{lightIntensity}%</span>
            <button className="btn-ghost" onClick={() => setLight(lightIntensity)}
              style={{ fontSize: 12, padding: '6px 14px' }}>Apply</button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, width: 120 }}>Inspection Light</span>
            <button
              className={inspectionLight ? 'btn-success' : 'btn-ghost'}
              onClick={() => {
                const next = !inspectionLight
                setInspectionLight(next)
                api('/api/set_inspection_light', 'POST', { on: next })
                  .then(() => feedback(`Inspection light ${next ? 'ON' : 'OFF'}`))
              }}
              style={{ fontSize: 12, padding: '6px 16px' }}>
              {inspectionLight ? 'ON' : 'OFF'}
            </button>
          </div>
        </div>
      </div>

      {/* Growth Stage Override */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 18 }}>
          Growth Stage Override
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <select value={growthStage} onChange={e => setGrowthStage(e.target.value)}
            style={{ padding: '8px 12px' }}>
            <option value="seedling">Seedling</option>
            <option value="vegetative">Vegetative</option>
            <option value="mature">Mature</option>
          </select>
          <button className="btn-primary" onClick={applyGrowthStage}
            style={{ fontSize: 13, padding: '8px 20px' }}>Apply</button>
        </div>
      </div>

      {/* Danger zone */}
      <div className="card" style={{ borderColor: 'rgba(239,68,68,0.2)' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--red)', marginBottom: 14 }}>
          Danger Zone
        </div>
        {!confirmReset ? (
          <button className="btn-danger" onClick={() => setConfirmReset(true)}
            style={{ fontSize: 13 }}>
            Reset Crop Cycle...
          </button>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 13, color: 'var(--red)', fontWeight: 500 }}>
              This will reset all plant data. Are you sure?
            </span>
            <button className="btn-danger" onClick={resetCropCycle}
              style={{ fontSize: 13, fontWeight: 700 }}>Confirm Reset</button>
            <button className="btn-ghost" onClick={() => setConfirmReset(false)}
              style={{ fontSize: 13 }}>Cancel</button>
          </div>
        )}
      </div>
    </div>
  )
}
