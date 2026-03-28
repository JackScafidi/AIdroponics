import React from 'react'

const STATE_COLOR = {
  RUNNING: 'var(--accent)',
  PAUSED:  'var(--yellow)',
  ERROR:   'var(--red)',
  STARTUP: 'var(--blue)',
  IDLE:    'var(--text-muted)',
}

const STATE_BG = {
  RUNNING: 'var(--accent-subtle)',
  PAUSED:  'var(--yellow-light)',
  ERROR:   'var(--red-light)',
  STARTUP: 'var(--blue-light)',
  IDLE:    'rgba(255,248,235,0.04)',
}

// Static tree matching main_tree.xml
const STATIC_TREE = {
  name: 'HydroponicsMain', type: 'Sequence', children: [
    { name: 'PublishSystemStatus', type: 'Action' },
    { name: 'SafetyGuard', type: 'ReactiveSequence', children: [
      { name: 'CheckSystemSafe', type: 'Condition' },
      { name: 'CheckNoDiseaseDetected', type: 'Condition' },
      { name: 'Operations', type: 'Sequence', children: [
        { name: 'MaybeInspect', type: 'Fallback', children: [
          { name: 'InspectionCycle', type: 'Sequence', children: [
            { name: 'TransportTo(INSPECT)', type: 'Action' },
            { name: 'SetInspectionLight(on)', type: 'Action' },
            { name: 'TriggerInspection', type: 'Action' },
            { name: 'SetInspectionLight(off)', type: 'Action' },
            { name: 'TransportTo(GROW)', type: 'Action' },
            { name: 'HarvestCycle', type: 'SubTree' },
          ]},
        ]},
        { name: 'NutrientCheck', type: 'SubTree', children: [
          { name: 'CheckNutrientStatus(water)', type: 'Condition' },
          { name: 'PhControl', type: 'Fallback' },
          { name: 'EcControl', type: 'Fallback' },
          { name: 'TempCheck', type: 'Fallback' },
        ]},
      ]},
    ]},
  ]
}

const TYPE_STYLE = {
  Sequence:         { color: '#3b82f6', bg: 'rgba(59,130,246,0.1)',  label: 'SEQ' },
  Fallback:         { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', label: 'FB' },
  ReactiveSequence: { color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)', label: 'REACT' },
  Action:           { color: '#16a34a', bg: 'rgba(22,163,74,0.1)',  label: 'ACT' },
  Condition:        { color: '#06b6d4', bg: 'rgba(6,182,212,0.1)',  label: 'CND' },
  SubTree:          { color: '#f97316', bg: 'rgba(249,115,22,0.1)', label: 'SUB' },
}

function TreeNode({ node, runningNodes = [], failedNodes = [], depth = 0 }) {
  const isRunning = runningNodes.some(n => n.includes(node.name))
  const isFailed  = failedNodes.some(n => n.includes(node.name))
  const style = TYPE_STYLE[node.type] ?? { color: '#64748b', bg: 'rgba(255,248,235,0.05)', label: '?' }

  return (
    <div style={{ marginLeft: depth * 20 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '5px 10px', borderRadius: 'var(--radius-sm)', marginBottom: 2,
        background: isRunning ? 'rgba(22,163,74,0.06)' : isFailed ? 'rgba(239,68,68,0.06)' : 'transparent',
        transition: 'background 0.2s ease',
      }}>
        {/* Connector line */}
        {depth > 0 && (
          <div style={{
            width: 12, height: 1, background: 'var(--border)', flexShrink: 0,
            marginLeft: -14,
          }}/>
        )}
        {/* Type badge */}
        <span style={{
          fontSize: 9, padding: '2px 6px', borderRadius: 'var(--radius-full)',
          background: style.bg, color: style.color, fontWeight: 700,
          letterSpacing: '0.03em', flexShrink: 0,
        }}>
          {style.label}
        </span>
        {/* Node name */}
        <span style={{
          fontSize: 12, fontFamily: "'SF Mono', 'Fira Code', monospace",
          color: isFailed ? 'var(--red)' : isRunning ? 'var(--accent)' : 'var(--text-secondary)',
          fontWeight: isRunning || isFailed ? 600 : 400,
        }}>
          {isRunning && '\u25b6 '}
          {isFailed && '\u2717 '}
          {node.name}
        </span>
      </div>
      {node.children?.map((child, i) => (
        <TreeNode key={i} node={child} runningNodes={runningNodes} failedNodes={failedNodes} depth={depth + 1}/>
      ))}
    </div>
  )
}

export default function BehaviorTreeStatus({ btStatus }) {
  const state        = btStatus?.system_state ?? 'IDLE'
  const activePath   = btStatus?.active_node_path ?? ''
  const runningNodes = btStatus?.running_nodes ?? []
  const failedNodes  = btStatus?.failed_nodes ?? []
  const color        = STATE_COLOR[state] ?? 'var(--text-muted)'
  const bg           = STATE_BG[state] ?? 'rgba(255,248,235,0.04)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Status cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
        <div className="card" style={{ padding: '20px 24px' }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8 }}>
            System State
          </div>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '6px 14px', borderRadius: 'var(--radius-sm)',
            background: bg,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%', background: color,
              boxShadow: state === 'RUNNING' ? `0 0 8px ${color}` : 'none',
            }}/>
            <span style={{ fontSize: 16, fontWeight: 700, color: color }}>
              {state}
            </span>
          </div>
        </div>
        <div className="card" style={{ padding: '20px 24px' }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: 8 }}>
            Active Node Path
          </div>
          <div style={{
            fontSize: 12, color: 'var(--accent)',
            fontFamily: "'SF Mono', 'Fira Code', monospace",
            wordBreak: 'break-all', lineHeight: 1.6,
          }}>
            {activePath || '\u2014 idle \u2014'}
          </div>
          {runningNodes.length > 0 && (
            <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {runningNodes.map((n, i) => (
                <span key={i} className="badge badge-green">{n}</span>
              ))}
            </div>
          )}
          {failedNodes.length > 0 && (
            <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {failedNodes.map((n, i) => (
                <span key={i} className="badge badge-red">{n}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Tree visualization */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
            Behavior Tree Structure
          </span>
          {/* Legend */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {Object.entries(TYPE_STYLE).map(([type, s]) => (
              <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{
                  fontSize: 8, padding: '1px 5px', borderRadius: 'var(--radius-full)',
                  background: s.bg, color: s.color, fontWeight: 700,
                }}>
                  {s.label}
                </span>
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{type}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
          <TreeNode node={STATIC_TREE} runningNodes={runningNodes} failedNodes={failedNodes}/>
        </div>
      </div>
    </div>
  )
}
