import React from 'react'
import FallingLeaves from './FallingLeaves.jsx'

/* ── Glassmorphism card ──────────────────────────────────────────────────── */
function GlassCard({ children, style, onClick, hoverable = false }) {
  const [hovered, setHovered] = React.useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered && hoverable
          ? 'rgba(255,255,255,0.18)'
          : 'rgba(255,255,255,0.1)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.15)',
        borderRadius: 20,
        padding: 28,
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        cursor: onClick ? 'pointer' : 'default',
        transform: hovered && hoverable ? 'translateY(-4px)' : 'none',
        boxShadow: hovered && hoverable
          ? '0 12px 40px rgba(0,0,0,0.3)'
          : '0 4px 20px rgba(0,0,0,0.15)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/* ── Stat pill ───────────────────────────────────────────────────────────── */
function StatPill({ label, value, color }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 18px', borderRadius: 14,
      background: 'rgba(255,255,255,0.08)',
      border: '1px solid rgba(255,255,255,0.1)',
    }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: color, boxShadow: `0 0 8px ${color}`,
      }}/>
      <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', fontWeight: 500 }}>{label}</span>
      <span style={{ fontSize: 14, color: '#fff', fontWeight: 700, marginLeft: 'auto' }}>{value}</span>
    </div>
  )
}

/* ── Navigation card for quick access ────────────────────────────────────── */
function NavCard({ icon, title, description, onClick }) {
  return (
    <GlassCard hoverable onClick={onClick} style={{ flex: 1, minWidth: 180, padding: 24 }}>
      <div style={{
        width: 44, height: 44, borderRadius: 14,
        background: 'rgba(74,222,128,0.15)',
        border: '1px solid rgba(74,222,128,0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 16, color: '#4ade80',
      }}>
        {icon}
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: '#fff', marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', lineHeight: 1.5 }}>{description}</div>
    </GlassCard>
  )
}

/* ── Main Home Page ──────────────────────────────────────────────────────── */
export default function HomePage({ onNavigate, connected, nutrientStatus, channelHealth, harvestEvents }) {
  const ns = nutrientStatus ?? {}
  const plants = channelHealth?.plants ?? []
  const healthyCount = plants.filter(p => p?.health_state === 'healthy' || (!p?.health_state && p?.status !== 'EMPTY')).length
  const totalPlants = plants.filter(p => p?.status && p.status !== 'EMPTY').length
  const totalYield = harvestEvents?.reduce((s, h) => s + (h.weight_grams ?? 0), 0) ?? 0

  return (
    <div style={{
      position: 'absolute', inset: 0, overflow: 'auto',
      background: 'linear-gradient(145deg, #041a0e 0%, #0a2818 25%, #0d3320 50%, #082a16 75%, #031208 100%)',
      color: '#fff',
    }}>
      {/* Falling leaf decorations */}
      <FallingLeaves />

      {/* Radial glow effects */}
      <div style={{
        position: 'absolute', top: '-15%', left: '30%',
        width: 600, height: 600, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(22,163,74,0.12) 0%, transparent 70%)',
        pointerEvents: 'none',
      }}/>
      <div style={{
        position: 'absolute', bottom: '-10%', right: '20%',
        width: 400, height: 400, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(20,184,166,0.08) 0%, transparent 70%)',
        pointerEvents: 'none',
      }}/>

      {/* Content */}
      <div style={{
        position: 'relative', zIndex: 1,
        maxWidth: 1100, margin: '0 auto',
        padding: '60px 40px 80px',
      }}>
        {/* Top bar */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: 80,
        }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 12,
              background: 'linear-gradient(135deg, rgba(74,222,128,0.25) 0%, rgba(20,184,166,0.15) 100%)',
              border: '1px solid rgba(74,222,128,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="22" height="30" viewBox="-70 -125 140 215" fill="none" style={{ display: 'block' }}>
                <path d="M0,-120 C4,-116 65,-40 65,20 C65,56 36,85 0,85 C-36,85 -65,56 -65,20 C-65,-40 -4,-116 0,-120Z" fill="rgba(74,222,128,0.15)" stroke="#4ade80" strokeWidth="6"/>
                <line x1="0" y1="60" x2="0" y2="-40" stroke="#4ade80" strokeWidth="5" strokeLinecap="round"/>
                <path d="M0,28 C-8,18 -34,-2 -38,-22 C-38,-22 -16,-4 0,14Z" fill="#4ade80" opacity="0.9"/>
                <path d="M0,6 C8,-6 34,-28 40,-46 C40,-46 18,-22 0,-8Z" fill="#4ade80" opacity="0.8"/>
                <path d="M0,-12 C-6,-20 -26,-38 -30,-54 C-30,-54 -12,-36 0,-24Z" fill="#4ade80" opacity="0.7"/>
                <path d="M0,-30 C4,-38 14,-54 16,-66 C16,-66 6,-48 0,-40Z" fill="#4ade80" opacity="0.6"/>
                <path d="M0,-40 C-2,-46 -6,-58 -7,-66 C-7,-66 -1,-54 0,-46Z" fill="#4ade80" opacity="0.5"/>
              </svg>
            </div>
            <span style={{ fontSize: 16, fontWeight: 600, color: 'rgba(255,255,255,0.8)', letterSpacing: '-0.02em' }}>
              AIdroponics
            </span>
          </div>
          {/* Status */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 16px', borderRadius: 30,
            background: connected ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
            border: `1px solid ${connected ? 'rgba(74,222,128,0.25)' : 'rgba(248,113,113,0.25)'}`,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: connected ? '#4ade80' : '#f87171',
              boxShadow: connected ? '0 0 8px rgba(74,222,128,0.6)' : '0 0 6px rgba(248,113,113,0.5)',
            }}/>
            <span style={{ fontSize: 12, fontWeight: 600, color: connected ? '#4ade80' : '#f87171' }}>
              {connected ? 'System Online' : 'Offline'}
            </span>
          </div>
        </div>

        {/* Hero section */}
        <div style={{ marginBottom: 64 }}>
          {/* Logo icon */}
          <div style={{ marginBottom: 28 }}>
            <svg width="80" height="115" viewBox="-70 -125 140 215" fill="none">
              <path d="M0,-120 C4,-116 65,-40 65,20 C65,56 36,85 0,85 C-36,85 -65,56 -65,20 C-65,-40 -4,-116 0,-120Z" fill="rgba(74,222,128,0.08)" stroke="rgba(74,222,128,0.6)" strokeWidth="2.5"/>
              <line x1="0" y1="60" x2="0" y2="-40" stroke="#4ade80" strokeWidth="3" strokeLinecap="round"/>
              <path d="M0,28 C-8,18 -34,-2 -38,-22 C-38,-22 -16,-4 0,14Z" fill="#4ade80" opacity="0.9"/>
              <path d="M0,6 C8,-6 34,-28 40,-46 C40,-46 18,-22 0,-8Z" fill="#4ade80" opacity="0.8"/>
              <path d="M0,-12 C-6,-20 -26,-38 -30,-54 C-30,-54 -12,-36 0,-24Z" fill="#4ade80" opacity="0.7"/>
              <path d="M0,-30 C4,-38 14,-54 16,-66 C16,-66 6,-48 0,-40Z" fill="#4ade80" opacity="0.6"/>
              <path d="M0,-40 C-2,-46 -6,-58 -7,-66 C-7,-66 -1,-54 0,-46Z" fill="#4ade80" opacity="0.5"/>
            </svg>
          </div>
          <div style={{
            fontSize: 11, fontWeight: 600, letterSpacing: '0.15em', textTransform: 'uppercase',
            color: '#4ade80', marginBottom: 20, opacity: 0.8,
          }}>
            Autonomous Hydroponics Farming System
          </div>
          <h1 style={{
            fontSize: 64, fontWeight: 800, lineHeight: 1.05,
            letterSpacing: '-0.04em', margin: '0 0 24px',
            background: 'linear-gradient(135deg, #ffffff 0%, #4ade80 50%, #14b8a6 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>
            AIdroponics
          </h1>
          <p style={{
            fontSize: 18, lineHeight: 1.7, color: 'rgba(255,255,255,0.5)',
            maxWidth: 560, fontWeight: 400, margin: 0,
          }}>
            AI-powered precision agriculture with real-time monitoring,
            automated nutrient management, and machine vision plant health analysis.
          </p>

          {/* CTA */}
          <div style={{ display: 'flex', gap: 14, marginTop: 36 }}>
            <button onClick={() => onNavigate('dashboard')} style={{
              padding: '14px 32px', borderRadius: 14, fontSize: 14, fontWeight: 600,
              background: 'linear-gradient(135deg, #16a34a 0%, #14b8a6 100%)',
              color: '#fff', border: 'none', cursor: 'pointer',
              boxShadow: '0 4px 20px rgba(22,163,74,0.35)',
              transition: 'all 0.2s ease',
            }}>
              Open Dashboard
            </button>
            <button onClick={() => onNavigate('analytics')} style={{
              padding: '14px 28px', borderRadius: 14, fontSize: 14, fontWeight: 500,
              background: 'rgba(255,255,255,0.08)',
              backdropFilter: 'blur(10px)',
              color: 'rgba(255,255,255,0.8)',
              border: '1px solid rgba(255,255,255,0.15)',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}>
              View Analytics
            </button>
          </div>
        </div>

        {/* Live stats row */}
        <div style={{ marginBottom: 48 }}>
          <GlassCard style={{ padding: 24 }}>
            <div style={{
              fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase',
              color: 'rgba(255,255,255,0.4)', marginBottom: 16,
            }}>
              Live System Status
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
              <StatPill label="pH" value={ns.ph_current?.toFixed(2) ?? '--'} color="#3b82f6"/>
              <StatPill label="EC" value={ns.ec_current ? `${ns.ec_current.toFixed(2)} mS` : '--'} color="#16a34a"/>
              <StatPill label="Temp" value={ns.temperature_c ? `${ns.temperature_c.toFixed(1)}\u00b0C` : '--'} color="#f97316"/>
              <StatPill label="Plants" value={totalPlants > 0 ? `${healthyCount}/${totalPlants}` : '--'} color="#4ade80"/>
              <StatPill label="Yield" value={totalYield > 0 ? `${totalYield.toFixed(1)}g` : '--'} color="#8b5cf6"/>
              <StatPill label="Stage" value={ns.growth_stage ?? '--'} color="#14b8a6"/>
            </div>
          </GlassCard>
        </div>

        {/* Quick navigation cards */}
        <div style={{ marginBottom: 48 }}>
          <div style={{
            fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase',
            color: 'rgba(255,255,255,0.35)', marginBottom: 20,
          }}>
            Quick Access
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
            <NavCard
              onClick={() => onNavigate('dashboard')}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>
                  <rect x="3" y="16" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/>
                </svg>
              }
              title="Dashboard"
              description="System overview, KPIs, rail position, and plant status"
            />
            <NavCard
              onClick={() => onNavigate('sensors')}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a4 4 0 0 0-4 4v6a4 4 0 0 0 8 0V6a4 4 0 0 0-4-4z"/><path d="M12 16v6"/><path d="M8 22h8"/>
                </svg>
              }
              title="Sensors"
              description="Real-time pH, EC, temperature gauges and pump monitoring"
            />
            <NavCard
              onClick={() => onNavigate('analytics')}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 3v18h18"/><path d="M7 16l4-6 4 4 5-8"/>
                </svg>
              }
              title="Analytics"
              description="Growth curves, yield reports, and plant health trends"
            />
            <NavCard
              onClick={() => onNavigate('nutrients')}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2c0 0-8 4-8 10a8 8 0 0 0 16 0c0-6-8-10-8-10z"/><path d="M12 22v-6"/><path d="M9 16l3-3 3 3"/>
                </svg>
              }
              title="Nutrients"
              description="Dosing history, pH/EC trends, and water chemistry"
            />
            <NavCard
              onClick={() => onNavigate('controls')}
              icon={
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>
                  <circle cx="8" cy="6" r="2" fill="currentColor"/><circle cx="16" cy="12" r="2" fill="currentColor"/><circle cx="10" cy="18" r="2" fill="currentColor"/>
                </svg>
              }
              title="Controls"
              description="Transport, dosing, BT status, profiles, and alerts"
            />
          </div>
        </div>

        {/* Footer info */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          paddingTop: 32, borderTop: '1px solid rgba(255,255,255,0.06)',
          flexWrap: 'wrap', gap: 16,
        }}>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.25)' }}>
            ROS2 Humble &middot; BehaviorTree.CPP &middot; YOLOv8 Vision &middot; PID Control
          </div>
          <div style={{ display: 'flex', gap: 20 }}>
            {['Station-based Architecture', 'Linear Rail Transport', 'Auto Harvesting'].map(t => (
              <span key={t} style={{
                fontSize: 11, color: 'rgba(255,255,255,0.3)', fontWeight: 500,
                padding: '4px 12px', borderRadius: 20,
                border: '1px solid rgba(255,255,255,0.08)',
              }}>
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
