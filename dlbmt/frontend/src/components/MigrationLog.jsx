import React from 'react'

export default function MigrationLog({ migrations }) {
    if (!migrations || migrations.length === 0) {
        return <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 10 }}>No migrations yet. Waiting for load imbalance...</div>
    }

    // Show most recent first
    const sorted = [...migrations].reverse()

    return (
        <div className="migration-log">
            {sorted.map((m, i) => (
                <div key={i} className="migration-entry fade-in">
                    <span className="migration-time">{m.time_str}</span>
                    <span className="migration-switch">{m.switch_id}</span>
                    <span className="migration-ctrl">{m.source_controller}</span>
                    <span className="migration-arrow">→</span>
                    <span className="migration-ctrl">{m.target_controller}</span>
                    <span className="migration-loads">
                        {m.source_load_before?.toFixed(0)}→{m.source_load_after?.toFixed(0)}% |
                        {m.target_load_before?.toFixed(0)}→{m.target_load_after?.toFixed(0)}%
                    </span>
                </div>
            ))}
        </div>
    )
}
