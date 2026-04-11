import React, { useState } from 'react'

/* ── Action button row ───────────────────────────────────────────────────── */
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

export default function SystemControls({ authToken, onLogin, onLogout }) {
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [loggingIn, setLoggingIn] = useState(false)

  const [doseAmounts, setDoseAmounts] = useState({ ph_up: '1.0', ph_down: '1.0', nutrient_a: '2.0', nutrient_b: '2.0' })
  const [lightIntensity, setLightIntensity] = useState(80)
  const [probeInterval, setProbeInterval] = useState('300')
  const [confirmReset, setConfirmReset] = useState(false)
  const [status, setStatus] = useState('')
  const [activeAction, setActiveAction] = useState(null)

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
    api('/api/controls/estop').then(() => feedback('Emergency stop sent'))
  }

  const triggerProbe = () => {
    setActiveAction('probe')
    api('/api/controls/trigger_probe')
      .then(() => { feedback('Probe cycle triggered'); setTimeout(() => setActiveAction(null), 2000) })
      .catch(() => { feedback('Probe trigger failed'); setActiveAction(null) })
  }

  const triggerAeration = () => {
    setActiveAction('aeration')
    api('/api/controls/trigger_aeration')
      .then(() => { feedback('Aeration cycle triggered'); setTimeout(() => setActiveAction(null), 2000) })
      .catch(() => { feedback('Aeration trigger failed'); setActiveAction(null) })
  }

  const captureVision = () => {
    setActiveAction('vision')
    api('/api/controls/capture_vision')
      .then(() => { feedback('Vision capture triggered'); setTimeout(() => setActiveAction(null), 2000) })
      .catch(() => { feedback('Vision capture failed'); setActiveAction(null) })
  }

  const applyProbeInterval = () => {
    const secs = parseFloat(probeInterval)
    if (isNaN(secs) || secs <= 0) { feedback('Invalid interval'); return }
    api('/api/controls/set_probe_interval', 'POST', { interval_seconds: secs })
      .then(d => feedback(`Probe interval \u2192 ${d.applied_interval_seconds ?? secs}s`))
  }

  const forceDose = (pump_id) => {
    const ml = parseFloat(doseAmounts[pump_id])
    if (isNaN(ml) || ml <= 0) { feedback('Invalid dose amount'); return }
    api('/api/controls/dose', 'POST', { pump_id, amount_ml: ml })
      .then(() => feedback(`Dosed ${pump_id}: ${ml} mL`))
  }

  const setLight = (intensity) => {
    api(`/api/controls/light/${intensity}`)
      .then(() => feedback(`Grow light \u2192 ${intensity}%`))
  }

  const resetSystem = () => {
    api('/api/controls/estop').then(() => { feedback('System reset via E-STOP'); setConfirmReset(false) })
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

      {/* System Actions */}
      <div>
        <div className="section-label">System Actions</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <ActionRow icon="\u{1F9EA}" label="Trigger Probe Cycle"
            active={activeAction === 'probe'} onClick={triggerProbe}/>
          <ActionRow icon="\u{1F4A8}" label="Trigger Aeration Cycle"
            active={activeAction === 'aeration'} onClick={triggerAeration}/>
          <ActionRow icon="\u{1F4F7}" label="Capture Vision / NDVI"
            active={activeAction === 'vision'} onClick={captureVision}/>
        </div>
      </div>

      {/* Probe Interval */}
      <div className="card">
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 18 }}>
          Probe Interval
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, width: 120 }}>Cycle Interval</span>
          <input
            type="number" min="30" max="3600" step="30"
            value={probeInterval}
            onChange={e => setProbeInterval(e.target.value)}
            style={{ width: 90 }}
          />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>seconds</span>
          <button className="btn-primary" onClick={applyProbeInterval}
            style={{ fontSize: 12, padding: '6px 16px' }}>Apply</button>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500, width: 120 }}>Grow Intensity</span>
          <input type="range" min="0" max="100" value={lightIntensity}
            onChange={e => setLightIntensity(parseInt(e.target.value))}
            style={{ flex: 1, maxWidth: 200 }}/>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--yellow)', width: 40 }}>{lightIntensity}%</span>
          <button className="btn-ghost" onClick={() => setLight(lightIntensity)}
            style={{ fontSize: 12, padding: '6px 14px' }}>Apply</button>
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
            Reset System (E-STOP)...
          </button>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 13, color: 'var(--red)', fontWeight: 500 }}>
              This will publish an emergency stop. Are you sure?
            </span>
            <button className="btn-danger" onClick={resetSystem}
              style={{ fontSize: 13, fontWeight: 700 }}>Confirm</button>
            <button className="btn-ghost" onClick={() => setConfirmReset(false)}
              style={{ fontSize: 13 }}>Cancel</button>
          </div>
        )}
      </div>
    </div>
  )
}
