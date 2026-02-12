import React, { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const LEVEL_COLORS = {
    1: '#00ff88',
    2: '#00d4ff',
    3: '#ffaa00',
    4: '#ff006e',
}

const BAR_COLORS = ['#00d4ff', '#ff006e', '#00ff88', '#ffaa00', '#a855f7', '#f97316', '#06b6d4']

export default function ImbalanceChart({ controllers, timeseries }) {
    const barData = useMemo(() => {
        if (!controllers || controllers.length === 0) return []
        return controllers.map(c => ({
            name: c.id,
            load: c.load_percentage || 0,
            level: c.level,
            switches: c.switch_count || 0,
        }))
    }, [controllers])

    if (barData.length === 0) {
        return <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>No data</div>
    }

    return (
        <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} margin={{ top: 10, right: 10, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="name" tick={{ fill: '#888', fontSize: 11 }}
                        axisLine={{ stroke: 'rgba(255,255,255,0.1)' }} />
                    <YAxis domain={[0, 100]} tick={{ fill: '#555', fontSize: 10 }}
                        axisLine={{ stroke: 'rgba(255,255,255,0.1)' }} />
                    <Tooltip
                        contentStyle={{
                            background: 'rgba(10,10,30,0.95)', border: '1px solid rgba(0,212,255,0.3)',
                            borderRadius: 8, fontSize: 12, color: '#e8e8f0'
                        }}
                        formatter={(value, name) => [`${value.toFixed(1)}%`, 'Load']}
                    />
                    <Bar dataKey="load" radius={[6, 6, 0, 0]} animationDuration={500}>
                        {barData.map((entry, i) => (
                            <Cell key={i}
                                fill={LEVEL_COLORS[entry.level] || BAR_COLORS[i % BAR_COLORS.length]}
                                fillOpacity={0.7}
                            />
                        ))}
                    </Bar>
                    {/* Threshold reference lines via a transparent bar trick won't work, use annotations */}
                </BarChart>
            </ResponsiveContainer>
            {/* Legend below chart */}
            <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 4 }}>
                {[{ l: 'Idle', c: '#00ff88' }, { l: 'Normal', c: '#00d4ff' }, { l: 'High', c: '#ffaa00' }, { l: 'Overload', c: '#ff006e' }].map(({ l, c }) => (
                    <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text-secondary)' }}>
                        <div style={{ width: 8, height: 8, borderRadius: 2, background: c }} />
                        <span>{l}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}
