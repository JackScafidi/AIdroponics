import React, { useState, useEffect, useRef, useCallback, Component } from 'react'

class PageErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return (
      <div style={{ padding: 32, color: 'var(--red)' }}>
        <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 15 }}>Something went wrong</div>
        <div style={{ fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap', color: 'var(--text-muted)' }}>
          {this.state.error.message}
        </div>
      </div>
    )
    return this.props.children
  }
}

import HomePage           from './components/HomePage.jsx'
import Dashboard          from './components/ChannelOverview.jsx'
import SensorGauges       from './components/SensorGauges.jsx'
import InspectionViewer   from './components/InspectionViewer.jsx'
import GrowthCurves       from './components/GrowthCurves.jsx'
import YieldAnalytics     from './components/YieldAnalytics.jsx'
import NutrientHistory    from './components/NutrientHistory.jsx'
import BehaviorTreeStatus from './components/BehaviorTreeStatus.jsx'
import SystemControls     from './components/SystemControls.jsx'
import AlertPanel         from './components/AlertPanel.jsx'
import PlantProfileEditor from './components/PlantProfileEditor.jsx'



/* ── SVG Icons ───────────────────────────────────────────────────────────── */
const Icons = {
  dashboard: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1.5"/>
      <rect x="14" y="3" width="7" height="5" rx="1.5"/>
      <rect x="3" y="16" width="7" height="5" rx="1.5"/>
      <rect x="14" y="12" width="7" height="9" rx="1.5"/>
    </svg>
  ),
  sensors: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a4 4 0 0 0-4 4v6a4 4 0 0 0 8 0V6a4 4 0 0 0-4-4z"/>
      <path d="M12 16v6"/>
      <path d="M8 22h8"/>
    </svg>
  ),
  analytics: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18"/>
      <path d="M7 16l4-6 4 4 5-8"/>
    </svg>
  ),
  nutrients: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2c0 0-8 4-8 10a8 8 0 0 0 16 0c0-6-8-10-8-10z"/>
      <path d="M12 22v-6"/>
      <path d="M9 16l3-3 3 3"/>
    </svg>
  ),
  controls: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="4" y1="6" x2="20" y2="6"/>
      <line x1="4" y1="12" x2="20" y2="12"/>
      <line x1="4" y1="18" x2="20" y2="18"/>
      <circle cx="8" cy="6" r="2" fill="currentColor"/>
      <circle cx="16" cy="12" r="2" fill="currentColor"/>
      <circle cx="10" cy="18" r="2" fill="currentColor"/>
    </svg>
  ),
  settings: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
    </svg>
  ),
  search: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
}

/* ── Navigation config ───────────────────────────────────────────────────── */
const NAV_ITEMS = [
  { id: 'dashboard',  label: 'Dashboard',  icon: Icons.dashboard },
  { id: 'sensors',    label: 'Sensors',    icon: Icons.sensors },
  { id: 'analytics',  label: 'Analytics',  icon: Icons.analytics },
  { id: 'nutrients',  label: 'Nutrients',  icon: Icons.nutrients },
  { id: 'controls',   label: 'Controls',   icon: Icons.controls },
]

const PAGE_META = {
  dashboard:  { title: 'AIdroponics', accent: 'Dashboard', subtitle: 'Module 1 \u2014 Parsley Channel \u2014 Day 34 of Cycle' },
  sensors:    { title: 'System',      accent: 'Sensors',   subtitle: 'Real-time pH, EC, temperature, and pump monitoring' },
  analytics:  { title: 'Growth',      accent: 'Analytics',  subtitle: 'Plant growth curves, yield statistics, and inspection history', tabs: ['Growth Curves', 'Yield Report', 'Plant Health'] },
  nutrients:  { title: 'Nutrient',    accent: 'History',   subtitle: 'Dosing history and water chemistry log' },
  controls:   { title: 'System',      accent: 'Controls',  subtitle: 'Manual overrides, behavior tree status, and plant profiles', tabs: ['Controls', 'BT Status', 'Profiles', 'Alerts'] },
}

export default function App() {


  // --- ADD THIS SECTION ---
  useEffect(() => {
    // 1. Inject the Google Font Link
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@400;600;700&display=swap';
    document.head.appendChild(link);

    // 2. Inject a global style tag to force the font on EVERYTHING
    const style = document.createElement('style');
    style.innerHTML = `
      * {
        font-family: 'Zilla Slab', serif !important;
      }
    `;
    document.head.appendChild(style);
  }, []);





  
  const [page, setPage]                   = useState('home')
  const [activeTab, setActiveTab]         = useState(0)
  const [connected, setConnected]         = useState(false)
  const [nutrientStatus, setNutrient]     = useState(null)
  const [inspectionResult, setInspection] = useState(null)
  const [transportStatus, setTransport]   = useState(null)
  const [harvestEvents, setHarvest]       = useState([])
  const [alerts, setAlerts]               = useState([])
  const [btStatus, setBt]                 = useState(null)
  const [channelHealth, setChannel]       = useState(null)
  const [unreadAlerts, setUnread]         = useState(0)
  const [sidebarHover, setSidebarHover]   = useState(null)
  const [dropletsVisible, setDropletsVisible] = useState(false)

  // REMOVED: const [now, setNow] (The Phantom Clock CPU drain)

  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  
  // NEW: WebSocket Buffer for Raspberry Pi CPU optimization
  const wsBuffer = useRef({
    alerts: [],
    harvests: [],
    scalar: {}
  })

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws`)
    wsRef.current = ws
    ws.onopen  = () => { setConnected(true);  if (reconnectTimer.current) clearTimeout(reconnectTimer.current) }
    ws.onclose = () => { setConnected(false); reconnectTimer.current = setTimeout(connect, 3000) }
    ws.onerror = () => ws.close()
    ws.onmessage = (evt) => {
      try {
        const { type, data } = JSON.parse(evt.data)
        // Store data silently in the buffer instead of triggering React re-renders instantly
        if (type === 'harvest_event') {
          wsBuffer.current.harvests.push(data)
        } else if (type === 'alert') {
          wsBuffer.current.alerts.push(data)
        } else {
          wsBuffer.current.scalar[type] = data
        }
      } catch (_) {}
    }
  }, [])

  useEffect(() => {
    connect()
    return () => { wsRef.current?.close(); if (reconnectTimer.current) clearTimeout(reconnectTimer.current) }
  }, [connect])

  // NEW: Flush the WebSocket buffer to React state at a safe 1Hz frame rate
  useEffect(() => {
    const timer = setInterval(() => {
      const { alerts: newAlerts, harvests: newHarvests, scalar } = wsBuffer.current
      
      // Update individual states only if new data arrived
      if (scalar.nutrient_status) setNutrient(scalar.nutrient_status)
      if (scalar.inspection_result) setInspection(scalar.inspection_result)
      if (scalar.transport_status) setTransport(scalar.transport_status)
      if (scalar.bt_status) setBt(scalar.bt_status)
      if (scalar.channel_health) setChannel(scalar.channel_health)
      
      // Batch array updates
      if (newHarvests.length > 0) {
        setHarvest(prev => [...newHarvests, ...prev].slice(0, 50))
        wsBuffer.current.harvests = [] // Clear buffer
      }
      if (newAlerts.length > 0) {
        setAlerts(prev => [...newAlerts, ...prev].slice(0, 200))
        setUnread(n => n + newAlerts.length)
        wsBuffer.current.alerts = [] // Clear buffer
      }
      
      // Clear scalar buffer
      wsBuffer.current.scalar = {}
    }, 1000) // 1000ms ensures Pi doesn't get overwhelmed
    
    return () => clearInterval(timer)
  }, [])

  // Hide droplets on every page/tab change, then fade in after glass renders
  useEffect(() => {
    setDropletsVisible(false)
    if (page === 'home') return
    const t = setTimeout(() => setDropletsVisible(true), 250)
    return () => clearTimeout(t)
  }, [page, activeTab])

  const handleNav = (id) => {
    if (page === id) return // FIX: Prevent double-tap bug
    
    setDropletsVisible(false) 
    setPage(id)
    setActiveTab(0)
    if (id === 'controls') setUnread(0)
  }

  const isHome = page === 'home'
  const meta = PAGE_META[page] ?? {}
  const hasAlerts = unreadAlerts > 0

  const rainDrops = React.useMemo(() => {
    const colors = [
      'rgba(245,238,225,0.14)', 'rgba(235,225,205,0.10)',
      'rgba(245,238,225,0.12)', 'rgba(240,232,215,0.10)',
      'rgba(245,238,225,0.09)', 'rgba(235,225,205,0.10)',
      'rgba(245,238,225,0.08)', 'rgba(240,232,215,0.11)',
    ]
    return Array.from({ length: 25 }, (_, i) => ({
      x: Math.random() * 96 + 2,
      size: 12 + Math.random() * 25,
      duration: 5 + Math.random() * 7,
      delay: Math.random() * 12 - 6,
      color: colors[i % colors.length],
    }))
  }, [])

  const renderPage = () => {
    switch (page) {
      case 'dashboard':
        return <Dashboard transportStatus={transportStatus} channelHealth={channelHealth}
          harvestEvents={harvestEvents} nutrientStatus={nutrientStatus} btStatus={btStatus} alerts={alerts}/>
      case 'sensors':
        return <SensorGauges nutrientStatus={nutrientStatus}/>
      case 'analytics':
        switch (activeTab) {
          case 0: return <GrowthCurves harvestEvents={harvestEvents} inspectionResult={inspectionResult}/>
          case 1: return <YieldAnalytics/>
          case 2: return <InspectionViewer inspectionResult={inspectionResult}/>
          default: return null
        }
      case 'nutrients':
        return <NutrientHistory/>
      case 'controls':
        switch (activeTab) {
          case 0: return <SystemControls/>
          case 1: return <BehaviorTreeStatus btStatus={btStatus}/>
          case 2: return <PlantProfileEditor/>
          case 3: return <AlertPanel alerts={alerts}/>
          default: return null
        }
      default: return null
    }
  }

  return (
    
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden' }}>

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <nav style={{
        width: 64,
        background: isHome ? 'rgba(4,26,14,0.95)' : 'var(--bg-sidebar)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        flexShrink: 0,
        padding: '16px 0',
        position: 'relative',
        zIndex: 10,
        borderRight: isHome ? '1px solid rgba(255,255,255,0.05)' : 'none',
        transition: 'background 0.3s ease',
      }}>
        {/* Logo — navigates to Home */}
        <button
          title="AIdroponics Home"
          onClick={() => handleNav('home')}
          onMouseEnter={() => setSidebarHover('home')}
          onMouseLeave={() => setSidebarHover(null)}
          style={{
            width: 38, height: 38, borderRadius: 12,
            background: isHome
              ? 'linear-gradient(135deg, rgba(74,222,128,0.35) 0%, rgba(20,184,166,0.2) 100%)'
              : sidebarHover === 'home'
                ? 'linear-gradient(135deg, rgba(74,222,128,0.3) 0%, rgba(20,184,166,0.18) 100%)'
                : 'linear-gradient(135deg, rgba(22,163,74,0.25) 0%, rgba(20,184,166,0.15) 100%)',
            border: `1px solid ${isHome ? 'rgba(74,222,128,0.4)' : 'rgba(74,222,128,0.2)'}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, fontWeight: 800, color: '#4ade80',
            marginBottom: 28, flexShrink: 0,
            cursor: 'pointer', padding: 0,
            transition: 'all 0.2s ease',
            boxShadow: isHome ? '0 0 16px rgba(74,222,128,0.2)' : 'none',
          }}
        >
          <svg width="22" height="30" viewBox="-70 -125 140 215" fill="none" style={{ display: 'block' }}>
            <path d="M0,-120 C4,-116 65,-40 65,20 C65,56 36,85 0,85 C-36,85 -65,56 -65,20 C-65,-40 -4,-116 0,-120Z" fill="rgba(74,222,128,0.15)" stroke="#4ade80" strokeWidth="6"/>
            <line x1="0" y1="60" x2="0" y2="-40" stroke="#4ade80" strokeWidth="5" strokeLinecap="round"/>
            <path d="M0,28 C-8,18 -34,-2 -38,-22 C-38,-22 -16,-4 0,14Z" fill="#4ade80" opacity="0.9"/>
            <path d="M0,6 C8,-6 34,-28 40,-46 C40,-46 18,-22 0,-8Z" fill="#4ade80" opacity="0.8"/>
            <path d="M0,-12 C-6,-20 -26,-38 -30,-54 C-30,-54 -12,-36 0,-24Z" fill="#4ade80" opacity="0.7"/>
            <path d="M0,-30 C4,-38 14,-54 16,-66 C16,-66 6,-48 0,-40Z" fill="#4ade80" opacity="0.6"/>
            <path d="M0,-40 C-2,-46 -6,-58 -7,-66 C-7,-66 -1,-54 0,-46Z" fill="#4ade80" opacity="0.5"/>
          </svg>
        </button>

        {/* Nav items */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4, width: '100%', padding: '0 10px' }}>
          {NAV_ITEMS.map(item => {
            const isActive = page === item.id
            const isHover = sidebarHover === item.id
            return (
              <div key={item.id} style={{ position: 'relative' }}>
                <button
                  title={item.label}
                  onClick={() => handleNav(item.id)}
                  onMouseEnter={() => setSidebarHover(item.id)}
                  onMouseLeave={() => setSidebarHover(null)}
                  style={{
                    width: '100%', height: 42,
                    borderRadius: 10,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: 0,
                    background: isActive ? 'var(--bg-sidebar-active)' : isHover ? 'var(--bg-sidebar-hover)' : 'transparent',
                    border: 'none',
                    color: isActive ? '#4ade80' : isHover ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.35)',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {item.icon}
                </button>
                {isActive && (
                  <div style={{
                    position: 'absolute', left: -10, top: '50%', transform: 'translateY(-50%)',
                    width: 3, height: 20, borderRadius: '0 3px 3px 0',
                    background: '#4ade80',
                  }}/>
                )}
                {item.id === 'controls' && hasAlerts && (
                  <div style={{
                    position: 'absolute', top: 4, right: 4,
                    width: 8, height: 8, borderRadius: '50%',
                    background: '#ef4444',
                    border: '2px solid var(--bg-sidebar)',
                  }}/>
                )}
                {isHover && !isActive && (
                  <div style={{
                    position: 'absolute', left: '100%', top: '50%', transform: 'translateY(-50%)',
                    marginLeft: 12, padding: '5px 10px', borderRadius: 6,
                    background: '#1f2937', color: '#e5e7eb', fontSize: 12, fontWeight: 500,
                    whiteSpace: 'nowrap', pointerEvents: 'none', zIndex: 50,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                  }}>
                    {item.label}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Bottom: settings + connection */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          <button
            title="Settings"
            style={{
              width: 42, height: 42, borderRadius: 10, padding: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'transparent', border: 'none',
              color: 'rgba(255,255,255,0.3)',
            }}
          >
            {Icons.settings}
          </button>
          <div title={connected ? 'WebSocket Connected' : 'Disconnected'} style={{
            width: 9, height: 9, borderRadius: '50%',
            background: connected ? '#4ade80' : '#f87171',
            boxShadow: connected ? '0 0 8px rgba(74,222,128,0.7)' : '0 0 6px rgba(248,113,113,0.6)',
            transition: 'all 0.3s ease',
          }}/>
        </div>
      </nav>

      {/* ── Main area ────────────────────────────────────────────────────── */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative',
        background: 'linear-gradient(145deg, #161310 0%, #1c1915 30%, #201c16 50%, #181510 75%, #121010 100%)',
        isolation: 'isolate' 
      }}>

        {/* Animated rain decorations */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden',
          opacity: dropletsVisible ? 1 : 0,
          transition: dropletsVisible ? 'opacity 0.6s ease' : 'none',
          visibility: isHome ? 'hidden' : 'visible',
          willChange: 'opacity',
          transform: 'translateZ(0)'
        }}>
            {/* Falling rain droplets */}
            {rainDrops.map((drop, i) => (
              <svg key={i} width={drop.size} height={drop.size * 1.38} viewBox="0 0 80 110" style={{
                position: 'absolute', left: `${drop.x}%`, top: 0, opacity: 0,
                animation: `rainFall ${drop.duration}s linear ${drop.delay}s infinite`,
                willChange: 'transform',
              }}>
                <path d="M40 0C40 0 0 40 0 70a40 40 0 0 0 80 0C80 40 40 0 40 0Z" fill={drop.color}/>
              </svg>
            ))}
            {/* Warm radial glows */}
            <div style={{
              position: 'absolute', top: '5%', right: '15%',
              width: 500, height: 500, borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(245,238,225,0.04) 0%, transparent 65%)',
            }}/>
            <div style={{
              position: 'absolute', bottom: '0%', left: '10%',
              width: 400, height: 400, borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(235,225,205,0.03) 0%, transparent 65%)',
            }}/>
          </div>

        {/* Home page — full bleed, no header */}
        {isHome && (
          <HomePage
            onNavigate={handleNav}
            connected={connected}
            nutrientStatus={nutrientStatus}
            channelHealth={channelHealth}
            harvestEvents={harvestEvents}
          />
        )}

        {/* Regular pages — with header */}
        {!isHome && (
          <>
            <header style={{
              padding: '20px 32px 0',
              flexShrink: 0,
              position: 'relative',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                <div>
                  <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.2, margin: 0 }}>
                    {meta.title}{' '}
                    <span style={{ color: 'var(--accent)' }}>{meta.accent}</span>
                  </h1>
                  <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '4px 0 0', fontWeight: 400 }}>
                    {meta.subtitle}
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 14px', borderRadius: 'var(--radius-full)',
                    background: connected ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)',
                    backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
                    border: `1px solid ${connected ? 'rgba(74,222,128,0.2)' : 'rgba(248,113,113,0.2)'}`,
                  }}>
                    <div style={{
                      width: 7, height: 7, borderRadius: '50%',
                      background: connected ? '#4ade80' : '#f87171',
                      boxShadow: connected ? '0 0 8px rgba(74,222,128,0.6)' : '0 0 6px rgba(248,113,113,0.5)',
                    }}/>
                    <span style={{ fontSize: 12, fontWeight: 600, color: connected ? '#4ade80' : '#f87171' }}>
                      {connected ? 'System Online' : 'Offline'}
                    </span>
                  </div>
                  <button style={{
                    width: 36, height: 36, borderRadius: 'var(--radius-sm)', padding: 0,
                    background: 'var(--glass-bg)',
                    backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
                    border: '1px solid var(--glass-border)',
                    color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: 'var(--glass-shadow)',
                    position: 'relative',
                  }}>
                    {Icons.search}
                    {hasAlerts && (
                      <div style={{
                        position: 'absolute', top: -2, right: -2,
                        width: 8, height: 8, borderRadius: '50%',
                        background: 'var(--red)',
                        border: '2px solid var(--bg-app)',
                      }}/>
                    )}
                  </button>
                </div>
              </div>

              {meta.tabs && (
                <div className="tab-bar" style={{ marginTop: 16, marginBottom: 0 }}>
                  {meta.tabs.map((tab, i) => (
                    <button key={tab} className={`tab-btn ${activeTab === i ? 'active' : ''}`}
                      onClick={() => {
                        if (activeTab === i) return // FIX: Prevent double-tap bug on tabs
                        setDropletsVisible(false) 
                        setActiveTab(i)
                      }}>
                      {tab}
                    </button>
                  ))}
                </div>
              )}
            </header>

            <main style={{
              flex: 1, overflowY: 'auto',
              padding: '24px 32px 40px',
              position: 'relative',
            }}>
              <div className="fade-in" key={`${page}-${activeTab}`}>
                <PageErrorBoundary key={`${page}-${activeTab}`}>
                  {renderPage()}
                </PageErrorBoundary>
              </div>
            </main>
          </>
        )}
      </div>
    </div>
  )
}