import React, { useMemo, useState, useRef, useCallback } from 'react'

const LEVEL_COLORS = {
    1: '#00ff88', // idle
    2: '#00d4ff', // normal
    3: '#ffaa00', // high
    4: '#ff006e', // overload
}

const CTRL_COLORS = [
    '#00d4ff', '#ff006e', '#00ff88', '#ffaa00', '#a855f7', '#f97316', '#06b6d4'
]

export default function TopologyView({ topology, recentMigration }) {
    const [tooltip, setTooltip] = useState(null)

    // Zoom & Pan state
    const [scale, setScale] = useState(1)
    const [translate, setTranslate] = useState({ x: 0, y: 0 })
    const [isPanning, setIsPanning] = useState(false)
    const panStart = useRef({ x: 0, y: 0 })

    // Node drag state
    const [dragNodeId, setDragNodeId] = useState(null)
    const [nodePositions, setNodePositions] = useState({})
    const svgRef = useRef(null)

    const { nodes, links, ctrlColorMap } = useMemo(() => {
        if (!topology) return { nodes: [], links: [], ctrlColorMap: {} }

        const controllers = topology.nodes.filter(n => n.type === 'controller')
        const colorMap = {}
        controllers.forEach((c, i) => { colorMap[c.id] = CTRL_COLORS[i % CTRL_COLORS.length] })

        return {
            nodes: topology.nodes,
            links: topology.links,
            ctrlColorMap: colorMap,
        }
    }, [topology])

    // Get node position (override with drag state if available)
    const getNodePos = useCallback((node) => {
        if (nodePositions[node.id]) {
            return nodePositions[node.id]
        }
        return { x: node.x, y: node.y }
    }, [nodePositions])

    // Convert screen coords to SVG coords
    const screenToSvg = useCallback((clientX, clientY) => {
        const svg = svgRef.current
        if (!svg) return { x: 0, y: 0 }
        const rect = svg.getBoundingClientRect()
        const svgX = (clientX - rect.left) / rect.width * 900
        const svgY = (clientY - rect.top) / rect.height * 700
        return {
            x: (svgX - translate.x) / scale,
            y: (svgY - translate.y) / scale,
        }
    }, [scale, translate])

    // Zoom via mouse wheel
    const handleWheel = useCallback((e) => {
        e.preventDefault()
        const delta = e.deltaY > 0 ? -0.1 : 0.1
        setScale(prev => Math.min(Math.max(prev + delta, 0.3), 3))
    }, [])

    // Pan handlers (background drag)
    const handleMouseDown = useCallback((e) => {
        if (e.target.closest('.topo-switch, .topo-controller')) return
        setIsPanning(true)
        panStart.current = { x: e.clientX - translate.x, y: e.clientY - translate.y }
    }, [translate])

    const handleMouseMove = useCallback((e) => {
        if (dragNodeId) {
            // Node dragging
            const pos = screenToSvg(e.clientX, e.clientY)
            setNodePositions(prev => ({
                ...prev,
                [dragNodeId]: { x: pos.x, y: pos.y }
            }))
            return
        }
        if (isPanning) {
            const svg = svgRef.current
            if (!svg) return
            const rect = svg.getBoundingClientRect()
            const dx = (e.clientX - panStart.current.x) / rect.width * 900
            const dy = (e.clientY - panStart.current.y) / rect.height * 700
            setTranslate({ x: dx, y: dy })
        }
    }, [isPanning, dragNodeId, screenToSvg])

    const handleMouseUp = useCallback(() => {
        setIsPanning(false)
        setDragNodeId(null)
    }, [])

    // Node drag start
    const handleNodeDragStart = useCallback((e, nodeId) => {
        e.stopPropagation()
        setDragNodeId(nodeId)
    }, [])

    // Reset view
    const resetView = useCallback(() => {
        setScale(1)
        setTranslate({ x: 0, y: 0 })
        setNodePositions({})
    }, [])

    if (!topology) {
        return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>Loading topology...</div>
    }

    const nodeMap = {}
    nodes.forEach(n => { nodeMap[n.id] = n })
    const controllers = nodes.filter(n => n.type === 'controller')
    const switches = nodes.filter(n => n.type === 'switch')

    // Domain links only
    const domainLinks = links.filter(l => l.type === 'domain')
    const infraLinks = links.filter(l => !l.type)

    const handleMouseEnter = (e, node) => {
        const rect = e.currentTarget.closest('svg').getBoundingClientRect()
        const x = e.clientX - rect.left + 15
        const y = e.clientY - rect.top - 10
        setTooltip({ node, x, y })
    }

    return (
        <div className="topology-svg" style={{ position: 'relative' }}>
            {/* Zoom controls */}
            <div style={{
                position: 'absolute', top: 8, right: 8, zIndex: 10,
                display: 'flex', gap: 4
            }}>
                <button className="topo-ctrl-btn" onClick={() => setScale(s => Math.min(s + 0.2, 3))} title="Zoom In">＋</button>
                <button className="topo-ctrl-btn" onClick={() => setScale(s => Math.max(s - 0.2, 0.3))} title="Zoom Out">−</button>
                <button className="topo-ctrl-btn" onClick={resetView} title="Reset View">⟲</button>
            </div>

            <svg ref={svgRef}
                viewBox="0 0 900 700" preserveAspectRatio="xMidYMid meet"
                style={{ width: '100%', height: '100%', cursor: isPanning ? 'grabbing' : (dragNodeId ? 'move' : 'grab') }}
                onWheel={handleWheel}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
            >
                <defs>
                    {controllers.map(c => (
                        <radialGradient key={`grad-${c.id}`} id={`ctrl-grad-${c.id}`}>
                            <stop offset="0%" stopColor={ctrlColorMap[c.id]} stopOpacity="0.9" />
                            <stop offset="100%" stopColor={ctrlColorMap[c.id]} stopOpacity="0.4" />
                        </radialGradient>
                    ))}
                    <filter id="glow">
                        <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                        <feMerge>
                            <feMergeNode in="coloredBlur" />
                            <feMergeNode in="SourceGraphic" />
                        </feMerge>
                    </filter>
                    <filter id="shadow">
                        <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.3" />
                    </filter>
                </defs>

                <g transform={`translate(${translate.x}, ${translate.y}) scale(${scale})`}>
                    {/* Infrastructure links */}
                    {infraLinks.map((link, i) => {
                        const src = nodeMap[link.source]
                        const tgt = nodeMap[link.target]
                        if (!src || !tgt) return null
                        const srcPos = getNodePos(src)
                        const tgtPos = getNodePos(tgt)
                        return (
                            <line key={`infra-${i}`} className="topo-link"
                                x1={srcPos.x} y1={srcPos.y} x2={tgtPos.x} y2={tgtPos.y} />
                        )
                    })}

                    {/* Domain links (switch to controller) */}
                    {domainLinks.map((link, i) => {
                        const src = nodeMap[link.source]
                        const tgt = nodeMap[link.target]
                        if (!src || !tgt) return null
                        const srcPos = getNodePos(src)
                        const tgtPos = getNodePos(tgt)
                        const isMigrating = recentMigration &&
                            ((link.source === recentMigration.switch_id && link.target === recentMigration.target_controller) ||
                                (link.source === recentMigration.switch_id && link.target === recentMigration.source_controller))
                        return (
                            <line key={`dom-${i}`}
                                className={`topo-link domain ${isMigrating ? 'migration' : ''}`}
                                x1={srcPos.x} y1={srcPos.y} x2={tgtPos.x} y2={tgtPos.y}
                                stroke={isMigrating ? '#ff006e' : ctrlColorMap[tgt.id] || ctrlColorMap[src.controller_id] || 'rgba(0,212,255,0.2)'}
                                strokeOpacity={isMigrating ? 0.8 : 0.25}
                            />
                        )
                    })}

                    {/* Switches */}
                    {switches.map(sw => {
                        const color = ctrlColorMap[sw.controller_id] || '#666'
                        const isMigrating = recentMigration && sw.id === recentMigration.switch_id
                        const size = 5 + (sw.resource_usage || 0) / 20
                        const pos = getNodePos(sw)
                        return (
                            <g key={sw.id} className={`topo-switch ${isMigrating ? 'pulse' : ''}`}
                                onMouseDown={e => handleNodeDragStart(e, sw.id)}
                                onMouseEnter={e => handleMouseEnter(e, sw)}
                                onMouseLeave={() => setTooltip(null)}>
                                <rect x={pos.x - size} y={pos.y - size}
                                    width={size * 2} height={size * 2}
                                    rx={3} fill={color} fillOpacity={0.5}
                                    stroke={isMigrating ? '#ff006e' : color}
                                    strokeWidth={isMigrating ? 2 : 1}
                                    strokeOpacity={0.8}
                                />
                                <text x={pos.x} y={pos.y + size + 12} className="topo-label" fontSize="8">
                                    {sw.id}
                                </text>
                            </g>
                        )
                    })}

                    {/* Controllers */}
                    {controllers.map(ctrl => {
                        const color = ctrlColorMap[ctrl.id]
                        const levelColor = LEVEL_COLORS[ctrl.level] || '#666'
                        const r = 22
                        const pos = getNodePos(ctrl)
                        return (
                            <g key={ctrl.id} className="topo-controller"
                                onMouseDown={e => handleNodeDragStart(e, ctrl.id)}
                                onMouseEnter={e => handleMouseEnter(e, ctrl)}
                                onMouseLeave={() => setTooltip(null)}
                                filter="url(#shadow)">
                                {/* Outer glow ring for level */}
                                <circle cx={pos.x} cy={pos.y} r={r + 6}
                                    fill="none" stroke={levelColor} strokeWidth={2}
                                    strokeOpacity={0.3}
                                    strokeDasharray={ctrl.level >= 3 ? '4 3' : 'none'}
                                    className={ctrl.level >= 3 ? 'pulse' : ''}
                                />
                                {/* Main circle */}
                                <circle cx={pos.x} cy={pos.y} r={r}
                                    fill={`url(#ctrl-grad-${ctrl.id})`}
                                    stroke={color} strokeWidth={2} strokeOpacity={0.8}
                                />
                                {/* Load arc */}
                                {(() => {
                                    const load = ctrl.load || 0
                                    const angle = (load / 100) * 360
                                    const rad = angle * Math.PI / 180
                                    const arcR = r - 4
                                    const endX = pos.x + arcR * Math.sin(rad)
                                    const endY = pos.y - arcR * Math.cos(rad)
                                    const largeArc = angle > 180 ? 1 : 0
                                    if (load <= 0) return null
                                    return (
                                        <path d={`M ${pos.x} ${pos.y - arcR} A ${arcR} ${arcR} 0 ${largeArc} 1 ${endX} ${endY}`}
                                            fill="none" stroke={levelColor} strokeWidth={3}
                                            strokeLinecap="round" strokeOpacity={0.9}
                                        />
                                    )
                                })()}
                                {/* Label */}
                                <text x={pos.x} y={pos.y + 2} className="topo-label" fontSize="12" fontWeight="700"
                                    fill="white">
                                    {ctrl.id}
                                </text>
                                <text x={pos.x} y={pos.y + r + 16} className="topo-label" fontSize="9">
                                    {ctrl.load?.toFixed(0) ?? 0}%
                                </text>
                                <text x={pos.x} y={pos.y + r + 28} className="topo-sub-label">
                                    {ctrl.level_label} · {ctrl.switch_count}sw
                                </text>
                            </g>
                        )
                    })}
                </g>
            </svg>

            {/* Tooltip */}
            {tooltip && (
                <div className="tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
                    <div className="tooltip-title">{tooltip.node.id} ({tooltip.node.type})</div>
                    {tooltip.node.type === 'controller' ? (
                        <>
                            <div className="tooltip-row"><span>Load</span><span>{tooltip.node.load?.toFixed(1)}%</span></div>
                            <div className="tooltip-row"><span>Level</span><span>{tooltip.node.level_label}</span></div>
                            <div className="tooltip-row"><span>Switches</span><span>{tooltip.node.switch_count}</span></div>
                            <div className="tooltip-row"><span>CPU Cap</span><span>{tooltip.node.capacity_cpu}</span></div>
                            <div className="tooltip-row"><span>Mem Cap</span><span>{tooltip.node.capacity_mem} MB</span></div>
                            <div className="tooltip-row"><span>BW Cap</span><span>{tooltip.node.capacity_bw} Mbps</span></div>
                        </>
                    ) : (
                        <>
                            <div className="tooltip-row"><span>Controller</span><span>{tooltip.node.controller_id}</span></div>
                            <div className="tooltip-row"><span>Pkt/s</span><span>{tooltip.node.packet_in_rate?.toFixed(1)}</span></div>
                            <div className="tooltip-row"><span>CPU Load</span><span>{tooltip.node.load_cpu?.toFixed(1)}</span></div>
                            <div className="tooltip-row"><span>Mem Load</span><span>{tooltip.node.load_mem?.toFixed(1)}</span></div>
                            <div className="tooltip-row"><span>BW Load</span><span>{tooltip.node.load_bw?.toFixed(1)}</span></div>
                            <div className="tooltip-row"><span>Usage</span><span>{tooltip.node.resource_usage?.toFixed(1)}%</span></div>
                        </>
                    )}
                </div>
            )}
        </div>
    )
}
