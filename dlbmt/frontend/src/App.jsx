import React, { useState, useEffect, useCallback, useRef } from 'react'
import { io } from 'socket.io-client'
import TopologyView from './components/TopologyView'
import ControllerPanel from './components/ControllerPanel'
import LoadChart from './components/LoadChart'
import MigrationLog from './components/MigrationLog'

const BACKEND = ''  // proxied via vite

export default function App() {
    const [topology, setTopology] = useState(null)
    const [controllers, setControllers] = useState([])
    const [stats, setStats] = useState(null)
    const [timeseries, setTimeseries] = useState([])
    const [migrations, setMigrations] = useState([])

    const [trafficPattern, setTrafficPattern] = useState('wave')
    const [intensity, setIntensity] = useState(1.0)
    const [selectedTopology, setSelectedTopology] = useState('atlanta')
    const [connected, setConnected] = useState(false)
    const [simSpeed, setSimSpeed] = useState(1.0)
    const [recentMigration, setRecentMigration] = useState(null)
    const socketRef = useRef(null)
    const pollRef = useRef(null)

    // Fetch data from REST API
    const fetchData = useCallback(async () => {
        try {
            const [topoRes, ctrlRes, statsRes, tsRes, migRes] = await Promise.all([
                fetch(`${BACKEND}/api/topology`),
                fetch(`${BACKEND}/api/controllers`),
                fetch(`${BACKEND}/api/stats/summary`),
                fetch(`${BACKEND}/api/stats/timeseries?limit=60`),
                fetch(`${BACKEND}/api/migration/history?limit=50`),
            ])
            const [topo, ctrl, st, ts, mig] = await Promise.all([
                topoRes.json(), ctrlRes.json(), statsRes.json(), tsRes.json(), migRes.json()
            ])
            setTopology(topo)
            setControllers(ctrl)
            setStats(st)
            setTimeseries(ts)
            setMigrations(mig)
        } catch (e) {
            console.error('Fetch error:', e)
        }
    }, [])

    // WebSocket connection
    useEffect(() => {
        const socket = io(window.location.origin, { transports: ['websocket', 'polling'] })
        socketRef.current = socket

        socket.on('connect', () => {
            setConnected(true)
            fetchData()
            // Ensure auto-migration is always enabled
            fetch(`${BACKEND}/api/migration/auto`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: true })
            }).catch(() => { })
        })

        socket.on('disconnect', () => setConnected(false))

        socket.on('state_update', (data) => {
            if (data.migration) {
                setRecentMigration(data.migration)
                setMigrations(prev => [...prev.slice(-49), data.migration])
                setTimeout(() => setRecentMigration(null), 3000)
            }
            // Refresh data on each update
            fetchData()
        })

        socket.on('topology', (data) => {
            setTopology(data)
        })

        return () => socket.disconnect()
    }, [fetchData])

    // Polling fallback (every 2s)
    useEffect(() => {
        pollRef.current = setInterval(fetchData, 2000)
        return () => clearInterval(pollRef.current)
    }, [fetchData])

    // Actions

    const changeTraffic = async (pattern, newIntensity) => {
        await fetch(`${BACKEND}/api/config/traffic`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pattern, intensity: parseFloat(newIntensity) })
        })
        setTrafficPattern(pattern)
        setIntensity(newIntensity)
    }

    const changeTopology = async (topo) => {
        await fetch(`${BACKEND}/api/config/topology`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topology: topo })
        })
        setSelectedTopology(topo)
        setMigrations([])
        setTimeseries([])
        fetchData()
    }

    const changeSpeed = async (speed) => {
        await fetch(`${BACKEND}/api/config/speed`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ speed: parseFloat(speed) })
        })
        setSimSpeed(speed)
    }

    return (
        <div className="app">
            {/* ===== Header ===== */}
            <header className="header">
                <div className="header-title">
                    <h1>⚡ DLBMT Dashboard</h1>
                    <span className="subtitle">Distributed Load Balancing with Multi-level Threshold</span>
                    <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`}
                        title={connected ? 'Connected' : 'Disconnected'}></span>
                </div>
                {/* <div className="header-controls">
                    <select className="btn" value={selectedTopology}
                        onChange={e => changeTopology(e.target.value)}>
                        <option value="atlanta">Atlanta (15 nodes)</option>
                        <option value="arn">ARN (30 nodes)</option>
                        <option value="germany50">Germany50 (50 nodes)</option>
                        <option value="interroute">Interroute (110 nodes)</option>
                    </select>

                    <select className="btn" value={trafficPattern}
                        onChange={e => changeTraffic(e.target.value, intensity)}>
                        <option value="wave">🌊 Wave</option>
                        <option value="uniform">📊 Uniform</option>
                        <option value="hotspot">🔥 Hotspot</option>
                        <option value="burst">💥 Burst</option>
                        <option value="stress">⚠️ Stress</option>
                    </select>

                    <select className="btn" value={intensity}
                        onChange={e => changeTraffic(trafficPattern, e.target.value)}>
                        <option value="0.5">0.5x</option>
                        <option value="1.0">1.0x</option>
                        <option value="1.5">1.5x</option>
                        <option value="2.0">2.0x</option>
                        <option value="3.0">3.0x</option>
                    </select>

                    <select className="btn" value={simSpeed}
                        onChange={e => changeSpeed(e.target.value)}>
                        <option value="0.5">⏱ 0.5x</option>
                        <option value="1">⏱ 1x</option>
                        <option value="2">⏱ 2x</option>
                        <option value="5">⏱ 5x</option>
                    </select>

                </div> */}
            </header>

            {/* ===== Main ===== */}
            <div className="main-content">
                {/* Stats Row */}
                <div className="stats-row">
                    <div className="glass-card stat-card">
                        <div className="stat-icon cyan">🎛</div>
                        <div className="stat-info">
                            <div className="stat-value">{stats?.total_controllers ?? '-'}</div>
                            <div className="stat-label">Controllers</div>
                        </div>
                    </div>
                    <div className="glass-card stat-card">
                        <div className="stat-icon green">🔀</div>
                        <div className="stat-info">
                            <div className="stat-value">{stats?.total_switches ?? '-'}</div>
                            <div className="stat-label">Switches</div>
                        </div>
                    </div>
                    <div className="glass-card stat-card">
                        <div className="stat-icon amber">📈</div>
                        <div className="stat-info">
                            <div className="stat-value">{stats?.avg_load ?? '-'}%</div>
                            <div className="stat-label">Avg Load</div>
                        </div>
                    </div>

                    <div className="glass-card stat-card">
                        <div className="stat-icon cyan">🔄</div>
                        <div className="stat-info">
                            <div className="stat-value">{stats?.total_migrations ?? 0}</div>
                            <div className="stat-label">Migrations</div>
                        </div>
                    </div>
                </div>

                {/* Topology */}
                <div className="topology-panel glass-card">
                    <div className="card-header">
                        <span className="card-title">🗺 Network Topology — {topology?.topology_name ?? ''}</span>
                    </div>
                    <TopologyView topology={topology} recentMigration={recentMigration} />
                </div>

                {/* Right Panel */}
                <div className="right-panel">
                    <div className="glass-card">
                        <div className="card-header">
                            <span className="card-title">🎛 Controllers</span>
                        </div>
                        <ControllerPanel controllers={controllers} />
                    </div>
                    <div className="glass-card">
                        <div className="card-header">
                            <span className="card-title">📊 Load Over Time</span>
                        </div>
                        <LoadChart timeseries={timeseries} />
                    </div>
                </div>

                {/* Bottom Panel */}
                <div className="bottom-panel">
                    <div className="glass-card">
                        <div className="card-header">
                            <span className="card-title">📋 Migration Log</span>
                            <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{migrations.length} events</span>
                        </div>
                        <MigrationLog migrations={migrations} />
                    </div>
                </div>
            </div>
        </div>
    )
}

{/* <span className="card-title">⚖ Load Distribution</span>
                        </div >
    <ImbalanceChart controllers={controllers} timeseries={timeseries} />
                    </div >
                </div >
            </div >
        </div >
    )
} */}
