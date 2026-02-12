import React from 'react'

const LEVEL_COLORS = {
    1: '#00ff88',
    2: '#00d4ff',
    3: '#ffaa00',
    4: '#ff006e',
}

export default function ControllerPanel({ controllers }) {
    if (!controllers || controllers.length === 0) {
        return <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No controllers</div>
    }

    return (
        <div className="controller-grid">
            {controllers.map(ctrl => {
                const levelColor = LEVEL_COLORS[ctrl.level] || '#666'
                return (
                    <div key={ctrl.id} className="ctrl-card">
                        <div className="ctrl-badge" style={{
                            background: `${levelColor}20`,
                            color: levelColor,
                            border: `1px solid ${levelColor}40`
                        }}>
                            {ctrl.id}
                        </div>
                        <div className="ctrl-info">
                            <div className="ctrl-name">
                                <span>{ctrl.id}</span>
                                <span className="level-badge" style={{
                                    background: `${levelColor}20`,
                                    color: levelColor,
                                    border: `1px solid ${levelColor}40`
                                }}>
                                    {ctrl.level_label}
                                </span>
                            </div>
                            <div className="ctrl-detail">
                                {ctrl.switch_count} switches · {ctrl.load_percentage?.toFixed(1)}% load
                            </div>

                            {/* Resource bars */}
                            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                                <ResourceBar label="CPU" value={ctrl.cpu_utilization} color="#00d4ff" />
                                <ResourceBar label="MEM" value={ctrl.mem_utilization} color="#a855f7" />
                                <ResourceBar label="BW" value={ctrl.bw_utilization} color="#00ff88" />
                            </div>

                            {/* Load bar */}
                            <div className="ctrl-load-bar">
                                <div className="ctrl-load-fill" style={{
                                    width: `${Math.min(ctrl.load_percentage || 0, 100)}%`,
                                    background: `linear-gradient(90deg, ${levelColor}80, ${levelColor})`
                                }} />
                            </div>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

function ResourceBar({ label, value, color }) {
    const v = Math.min(value || 0, 100)
    return (
        <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-muted)', marginBottom: 2 }}>
                <span>{label}</span>
                <span style={{ color: v > 70 ? '#ff006e' : 'var(--text-secondary)' }}>{v.toFixed(0)}%</span>
            </div>
            <div style={{
                width: '100%', height: 3, background: 'rgba(255,255,255,0.06)',
                borderRadius: 2, overflow: 'hidden'
            }}>
                <div style={{
                    height: '100%', width: `${v}%`,
                    background: v > 70 ? '#ff006e' : color,
                    borderRadius: 2,
                    transition: 'width 0.5s ease'
                }} />
            </div>
        </div>
    )
}
