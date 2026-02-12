import React, { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

const CTRL_COLORS = ['#00d4ff', '#ff006e', '#00ff88', '#ffaa00', '#a855f7', '#f97316', '#06b6d4']

export default function LoadChart({ timeseries }) {
    const chartData = useMemo(() => {
        if (!timeseries || timeseries.length === 0) return { data: [], keys: [] }

        const keys = new Set()
        const data = timeseries.map((snap, i) => {
            const point = { idx: i }
            if (snap.controllers) {
                Object.entries(snap.controllers).forEach(([id, info]) => {
                    point[id] = info.load
                    keys.add(id)
                })
            }
            point['avg'] = snap.avg_load
            return point
        })

        return { data, keys: Array.from(keys).sort() }
    }, [timeseries])

    if (chartData.data.length === 0) {
        return <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 20, textAlign: 'center' }}>Collecting data...</div>
    }

    return (
        <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData.data} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="idx" tick={false} axisLine={{ stroke: 'rgba(255,255,255,0.1)' }} />
                    <YAxis domain={[0, 100]} tick={{ fill: '#555', fontSize: 10 }}
                        axisLine={{ stroke: 'rgba(255,255,255,0.1)' }} />
                    <Tooltip contentStyle={{
                        background: 'rgba(10,10,30,0.95)', border: '1px solid rgba(0,212,255,0.3)',
                        borderRadius: 8, fontSize: 12, color: '#e8e8f0'
                    }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {chartData.keys.map((key, i) => (
                        <Line key={key} type="monotone" dataKey={key}
                            stroke={CTRL_COLORS[i % CTRL_COLORS.length]}
                            strokeWidth={2} dot={false}
                            animationDuration={300}
                        />
                    ))}
                    <Line type="monotone" dataKey="avg" stroke="#ffffff"
                        strokeWidth={1.5} strokeDasharray="5 3" dot={false}
                        name="Average" animationDuration={300}
                    />
                    {/* Threshold lines */}
                    <Line type="monotone" dataKey={() => 25} stroke="#00ff8840"
                        strokeDasharray="2 4" dot={false} name="Idle (25)" strokeWidth={1} />
                    <Line type="monotone" dataKey={() => 50} stroke="#00d4ff40"
                        strokeDasharray="2 4" dot={false} name="Normal (50)" strokeWidth={1} />
                    <Line type="monotone" dataKey={() => 75} stroke="#ff006e40"
                        strokeDasharray="2 4" dot={false} name="High (75)" strokeWidth={1} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    )
}
