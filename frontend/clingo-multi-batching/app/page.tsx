'use client';
import { useState, useMemo, useCallback } from "react";

const RAW_OUTPUT = `freq(0,l1,l2,tr1,2) freq(0,l1,l2,tr2,0) freq(0,l1,l3,tr1,0) freq(0,l1,l3,tr2,4) freq(0,l1,l4,tr1,1) freq(0,l1,l4,tr2,0) freq(0,l2,l3,tr1,7) freq(0,l2,l3,tr2,0) freq(0,l2,l4,tr1,0) freq(0,l2,l4,tr2,0) freq(0,l2,l6,tr1,0) freq(0,l3,l5,tr1,0) freq(0,l3,l5,tr2,0) freq(0,l3,l6,tr1,13) freq(0,l3,l6,tr2,2) freq(0,l4,l5,tr1,2) freq(0,l4,l5,tr2,0) freq(0,l4,l6,tr1,0) freq(0,l4,l6,tr2,0) freq(1,l1,l2,tr1,3) freq(1,l1,l2,tr2,0) freq(1,l1,l3,tr1,0) freq(1,l1,l3,tr2,1) freq(1,l1,l4,tr1,4) freq(1,l1,l4,tr2,0) freq(1,l2,l3,tr1,7) freq(1,l2,l3,tr2,2) freq(1,l2,l4,tr1,0) freq(1,l2,l4,tr2,0) freq(1,l2,l6,tr1,0) freq(1,l3,l5,tr1,5) freq(1,l3,l5,tr2,0) freq(1,l3,l6,tr1,1) freq(1,l3,l6,tr2,0) freq(1,l4,l5,tr1,3) freq(1,l4,l5,tr2,0) freq(1,l4,l6,tr1,0) freq(1,l4,l6,tr2,0) pack(0,p1,0,l1,l2,tr1) pack(0,p1,0,l1,l2,tr2) pack(0,p1,0,l1,l4,tr2) pack(0,p1,0,l2,l4,tr2) pack(0,p1,0,l3,l5,tr2) pack(0,p1,0,l4,l5,tr2) pack(0,p1,0,l4,l6,tr2) pack(0,p1,1,l1,l2,tr1) pack(0,p1,1,l1,l2,tr2) pack(0,p1,1,l1,l3,tr1) pack(0,p1,1,l1,l3,tr2) pack(0,p1,1,l1,l4,tr2) pack(0,p1,1,l2,l4,tr2) pack(0,p1,1,l3,l5,tr2) pack(0,p1,1,l4,l5,tr2) pack(0,p1,1,l4,l6,tr2) pack(0,p2,0,l1,l4,tr2) pack(0,p2,0,l2,l3,tr1) pack(0,p2,0,l2,l3,tr2) pack(0,p2,0,l2,l4,tr1) pack(0,p2,0,l2,l4,tr2) pack(0,p2,0,l2,l6,tr1) pack(0,p2,0,l3,l5,tr2) pack(0,p2,0,l3,l6,tr1) pack(0,p2,0,l4,l6,tr2) pack(0,p2,1,l1,l2,tr2) pack(0,p2,1,l1,l4,tr2) pack(0,p2,1,l2,l3,tr1) pack(0,p2,1,l2,l3,tr2) pack(0,p2,1,l2,l4,tr1) pack(0,p2,1,l2,l4,tr2) pack(0,p2,1,l3,l5,tr2) pack(0,p2,1,l3,l6,tr2) pack(0,p2,1,l4,l6,tr2) pack(1,p1,0,l1,l3,tr1) pack(1,p1,0,l1,l4,tr1) pack(1,p1,0,l2,l3,tr1) pack(1,p1,0,l2,l4,tr1) pack(1,p1,0,l2,l6,tr1) pack(1,p1,0,l3,l5,tr1) pack(1,p1,0,l3,l6,tr1) pack(1,p1,0,l4,l5,tr1) pack(1,p1,0,l4,l6,tr1) pack(1,p1,1,l1,l4,tr1) pack(1,p1,1,l2,l3,tr1) pack(1,p1,1,l2,l4,tr1) pack(1,p1,1,l2,l6,tr1) pack(1,p1,1,l3,l5,tr1) pack(1,p1,1,l3,l6,tr1) pack(1,p1,1,l4,l5,tr1) pack(1,p1,1,l4,l6,tr1) pack(1,p2,0,l1,l2,tr2) pack(2,p2,0,l1,l2,tr1) pack(2,p2,0,l1,l3,tr1) pack(2,p2,0,l1,l4,tr1) pack(2,p2,0,l3,l5,tr1) pack(2,p2,0,l4,l5,tr1) pack(2,p2,0,l4,l6,tr1) pack(2,p2,1,l1,l2,tr1) pack(2,p2,1,l1,l3,tr1) pack(2,p2,1,l1,l4,tr1) pack(2,p2,1,l2,l6,tr1) pack(2,p2,1,l3,l5,tr1) pack(2,p2,1,l3,l6,tr1) pack(2,p2,1,l4,l5,tr1) pack(2,p2,1,l4,l6,tr1) pack(3,p1,0,l1,l3,tr2) pack(3,p1,0,l2,l3,tr2) pack(3,p1,0,l3,l6,tr2) pack(3,p1,1,l2,l3,tr2) pack(3,p1,1,l3,l6,tr2) pack(4,p2,0,l1,l3,tr2) pack(4,p2,0,l3,l6,tr2) pack(4,p2,0,l4,l5,tr2) pack(4,p2,1,l1,l3,tr2) pack(4,p2,1,l4,l5,tr2)`;

function parseOutput(raw) {
  const packs = [];
  const freqs = [];

  const packRe = /pack\((\d+),([\w]+),(\d+),([\w]+),([\w]+),([\w]+)\)/g;
  const freqRe = /freq\((\d+),([\w]+),([\w]+),([\w]+),(\d+)\)/g;

  let m;
  while ((m = packRe.exec(raw)) !== null) {
    packs.push({ n: parseInt(m[1]), part: m[2], binId: parseInt(m[3]), from: m[4], to: m[5], tr: m[6] });
  }
  while ((m = freqRe.exec(raw)) !== null) {
    freqs.push({ binId: parseInt(m[1]), from: m[2], to: m[3], tr: m[4], freq: parseInt(m[5]) });
  }

  return { packs, freqs };
}

function buildGraph(packs, freqs) {
  const locations = new Set();
  const edges = new Map();

  // Index frequencies by key
  const freqMap = new Map();
  for (const f of freqs) {
    const key = `${f.from}->${f.to}::${f.tr}::${f.binId}`;
    freqMap.set(key, f);
    if (f.freq > 0) {
      locations.add(f.from);
      locations.add(f.to);
      edges.set(key, { ...f });
    }
  }

  // Attach pack contents to edges — only non-zero packs
  const edgeContents = new Map();
  for (const p of packs) {
    if (p.n === 0) continue;
    const key = `${p.from}->${p.to}::${p.tr}::${p.binId}`;
    if (!edges.has(key)) continue;
    if (!edgeContents.has(key)) edgeContents.set(key, []);
    edgeContents.get(key).push({ part: p.part, qty: p.n });
  }

  // Consolidate: group by (from, to, tr, contents) and sum frequencies
  // Only include edges that have actual content packed
  const consolidated = new Map();
  for (const [key, edge] of edges) {
    const contents = edgeContents.get(key) || [];
    if (contents.length === 0) continue; // Skip edges with nothing packed
    const contentKey = contents.sort((a, b) => a.part.localeCompare(b.part)).map(c => `${c.qty}×${c.part}`).join(",");
    const consKey = `${edge.from}->${edge.to}::${edge.tr}::${contentKey}`;
    if (!consolidated.has(consKey)) {
      consolidated.set(consKey, { from: edge.from, to: edge.to, tr: edge.tr, contents: [...contents], totalFreq: 0 });
    }
    consolidated.get(consKey).totalFreq += edge.freq;
  }

  return { locations: [...locations].sort(), edges: [...consolidated.values()] };
}

// Layout: position nodes in a structured way
const NODE_POSITIONS = {
  l1: { x: 100, y: 280 },   // source — left center
  l2: { x: 370, y: 80 },    // hub — top 
  l3: { x: 370, y: 480 },   // hub — bottom
  l4: { x: 370, y: 280 },   // hub — middle
  l5: { x: 700, y: 120 },   // sink — top right
  l6: { x: 700, y: 440 },   // sink — bottom right
};

const PART_COLORS = {
  p1: "#3b82f6",
  p2: "#f59e0b",
  p3: "#10b981",
  p4: "#ef4444",
};

const TR_STYLES = {
  tr1: { dash: "", color: "#1e293b", label: "TR₁" },
  tr2: { dash: "6,4", color: "#7c3aed", label: "TR₂" },
};

function bezierMidpoint(x1, y1, x2, y2, cx, cy, t = 0.5) {
  const mt = 1 - t;
  return {
    x: mt * mt * x1 + 2 * mt * t * cx + t * t * x2,
    y: mt * mt * y1 + 2 * mt * t * cy + t * t * y2,
  };
}

function EdgeLabel({ edge, idx, totalForRoute }) {
  const p1 = NODE_POSITIONS[edge.from];
  const p2 = NODE_POSITIONS[edge.to];

  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  const len = Math.sqrt(dx * dx + dy * dy);
  const nx = -dy / len;
  const ny = dx / len;

  const offset = (idx - (totalForRoute - 1) / 2) * 40;
  const curveStrength = 35 + offset;

  const cx = (p1.x + p2.x) / 2 + nx * curveStrength;
  const cy = (p1.y + p2.y) / 2 + ny * curveStrength;

  const mid = bezierMidpoint(p1.x, p2.x, p2.x, p2.y, cx, cy, 0.45);
  const trStyle = TR_STYLES[edge.tr] || TR_STYLES.tr1;

  const labelX = (p1.x + p2.x) / 2 + nx * (curveStrength + 18);
  const labelY = (p1.y + p2.y) / 2 + ny * (curveStrength + 18);

  const path = `M ${p1.x} ${p1.y} Q ${cx} ${cy} ${p2.x} ${p2.y}`;
  const pathId = `edge-${edge.from}-${edge.to}-${edge.tr}-${idx}`;

  return (
    <g>
      <defs>
        <marker
          id={`arrow-${pathId}`}
          viewBox="0 0 10 7"
          refX="28"
          refY="3.5"
          markerWidth="8"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 3.5 L 0 7 z" fill={trStyle.color} />
        </marker>
      </defs>
      <path
        d={path}
        fill="none"
        stroke={trStyle.color}
        strokeWidth="1.8"
        strokeDasharray={trStyle.dash}
        markerEnd={`url(#arrow-${pathId})`}
        opacity="0.7"
      />
      <foreignObject
        x={labelX - 70}
        y={labelY - 24}
        width="140"
        height="52"
        style={{ overflow: "visible" }}
      >
        <div
          style={{
            background: "rgba(255,255,255,0.95)",
            border: `1px solid ${trStyle.color}33`,
            borderRadius: "6px",
            padding: "3px 7px",
            fontSize: "10px",
            fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
            color: "#1e293b",
            textAlign: "center",
            lineHeight: "1.35",
            backdropFilter: "blur(4px)",
            boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
          }}
        >
          <span style={{ fontWeight: 700, color: trStyle.color }}>{trStyle.label}</span>
          <span style={{ color: "#94a3b8", margin: "0 3px" }}>·</span>
          <span style={{ color: "#64748b" }}>f={edge.totalFreq}</span>
          <br />
          {edge.contents.map((c, i) => (
            <span key={i}>
              <span style={{ color: PART_COLORS[c.part] || "#666", fontWeight: 600 }}>
                {c.qty}×{c.part}
              </span>
              {i < edge.contents.length - 1 && <span style={{ color: "#cbd5e1" }}> · </span>}
            </span>
          ))}
        </div>
      </foreignObject>
    </g>
  );
}

function NetworkNode({ id, x, y, isSelected, onClick }) {
  return (
    <g
      onClick={() => onClick(id)}
      style={{ cursor: "pointer" }}
    >
      <circle
        cx={x}
        cy={y}
        r="24"
        fill={isSelected ? "#1e293b" : "#f8fafc"}
        stroke={isSelected ? "#3b82f6" : "#94a3b8"}
        strokeWidth={isSelected ? 2.5 : 1.5}
      />
      <text
        x={x}
        y={y + 1}
        textAnchor="middle"
        dominantBaseline="central"
        fill={isSelected ? "#f8fafc" : "#1e293b"}
        fontSize="13"
        fontWeight="700"
        fontFamily="'JetBrains Mono', 'SF Mono', monospace"
      >
        {id.toUpperCase()}
      </text>
    </g>
  );
}

function StatsPanel({ edges, filterNode }) {
  const filtered = filterNode
    ? edges.filter((e) => e.from === filterNode || e.to === filterNode)
    : edges;

  const totalShipments = filtered.reduce((s, e) => s + e.totalFreq, 0);
  const routeCount = filtered.length;
  const partTotals = {};
  for (const e of filtered) {
    for (const c of e.contents) {
      partTotals[c.part] = (partTotals[c.part] || 0) + c.qty * e.totalFreq;
    }
  }

  return (
    <div
      style={{
        background: "#0f172a",
        borderRadius: "10px",
        padding: "16px 20px",
        color: "#e2e8f0",
        fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
        fontSize: "12px",
        minWidth: "200px",
      }}
    >
      <div style={{ fontSize: "10px", textTransform: "uppercase", letterSpacing: "1.5px", color: "#64748b", marginBottom: "12px" }}>
        {filterNode ? `Node ${filterNode.toUpperCase()} Summary` : "Network Summary"}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "14px" }}>
        <div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: "#f8fafc" }}>{routeCount}</div>
          <div style={{ fontSize: "9px", color: "#64748b", textTransform: "uppercase" }}>Active Routes</div>
        </div>
        <div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: "#f8fafc" }}>{totalShipments}</div>
          <div style={{ fontSize: "9px", color: "#64748b", textTransform: "uppercase" }}>Total Trips</div>
        </div>
      </div>
      <div style={{ borderTop: "1px solid #1e293b", paddingTop: "10px" }}>
        <div style={{ fontSize: "9px", textTransform: "uppercase", letterSpacing: "1px", color: "#64748b", marginBottom: "6px" }}>
          Total Units Shipped
        </div>
        {Object.entries(partTotals)
          .sort()
          .map(([part, total]) => (
            <div key={part} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 0" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "2px",
                    background: PART_COLORS[part] || "#666",
                    display: "inline-block",
                  }}
                />
                {part}
              </span>
              <span style={{ fontWeight: 700, color: "#f8fafc" }}>{total}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

function RouteTable({ edges, filterNode }) {
  const filtered = filterNode
    ? edges.filter((e) => e.from === filterNode || e.to === filterNode)
    : edges;

  const sorted = [...filtered].sort((a, b) => b.totalFreq - a.totalFreq);

  return (
    <div
      style={{
        background: "#ffffff",
        borderRadius: "10px",
        border: "1px solid #e2e8f0",
        overflow: "hidden",
        fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
        fontSize: "11px",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "80px 60px 1fr 60px",
          gap: "0",
          padding: "8px 14px",
          background: "#f1f5f9",
          fontWeight: 700,
          fontSize: "9px",
          textTransform: "uppercase",
          letterSpacing: "1px",
          color: "#64748b",
        }}
      >
        <div>Route</div>
        <div>Type</div>
        <div>Contents</div>
        <div style={{ textAlign: "right" }}>Freq</div>
      </div>
      <div style={{ maxHeight: "240px", overflowY: "auto" }}>
        {sorted.map((e, i) => {
          const trStyle = TR_STYLES[e.tr] || TR_STYLES.tr1;
          return (
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "80px 60px 1fr 60px",
                padding: "7px 14px",
                borderBottom: "1px solid #f1f5f9",
                alignItems: "center",
              }}
            >
              <div style={{ fontWeight: 600 }}>
                {e.from.toUpperCase()}→{e.to.toUpperCase()}
              </div>
              <div>
                <span
                  style={{
                    background: `${trStyle.color}15`,
                    color: trStyle.color,
                    padding: "2px 6px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: 600,
                  }}
                >
                  {trStyle.label}
                </span>
              </div>
              <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                {e.contents.map((c, j) => (
                  <span
                    key={j}
                    style={{
                      background: `${PART_COLORS[c.part] || "#666"}18`,
                      color: PART_COLORS[c.part] || "#666",
                      padding: "1px 6px",
                      borderRadius: "3px",
                      fontWeight: 600,
                      fontSize: "10px",
                    }}
                  >
                    {c.qty}×{c.part}
                  </span>
                ))}
              </div>
              <div style={{ textAlign: "right", fontWeight: 700, color: "#1e293b" }}>
                {e.totalFreq}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function LogisticsViz() {
  const [selectedNode, setSelectedNode] = useState(null);

  const { packs, freqs } = useMemo(() => parseOutput(RAW_OUTPUT), []);
  const { locations, edges } = useMemo(() => buildGraph(packs, freqs), [packs, freqs]);

  const handleNodeClick = useCallback((id) => {
    setSelectedNode((prev) => (prev === id ? null : id));
  }, []);

  // Group edges by (from, to) for offset calculation
  const edgesByRoute = useMemo(() => {
    const map = new Map();
    for (const e of edges) {
      const rKey = [e.from, e.to].sort().join("-");
      if (!map.has(rKey)) map.set(rKey, []);
      map.get(rKey).push(e);
    }
    return map;
  }, [edges]);

  const filteredEdges = selectedNode
    ? edges.filter((e) => e.from === selectedNode || e.to === selectedNode)
    : edges;

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#f8fafc",
        fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
        padding: "24px",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: "20px" }}>
        <div
          style={{
            fontSize: "9px",
            textTransform: "uppercase",
            letterSpacing: "2.5px",
            color: "#94a3b8",
            marginBottom: "4px",
          }}
        >
          ASP Logistics Solver
        </div>
        <h1
          style={{
            fontSize: "28px",
            fontWeight: 800,
            color: "#0f172a",
            margin: 0,
            letterSpacing: "-0.5px",
          }}
        >
          Network Flow Visualization
        </h1>
        <p style={{ color: "#64748b", fontSize: "12px", margin: "6px 0 0" }}>
          {selectedNode
            ? `Filtering by node ${selectedNode.toUpperCase()} — click again to clear`
            : "Click a node to filter routes"}
        </p>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: "16px", marginBottom: "16px", flexWrap: "wrap" }}>
        {Object.entries(TR_STYLES).map(([tr, s]) => (
          <div key={tr} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "11px", color: "#475569" }}>
            <svg width="30" height="10">
              <line x1="0" y1="5" x2="30" y2="5" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
            </svg>
            {s.label}
          </div>
        ))}
        <div style={{ width: "1px", background: "#e2e8f0" }} />
        {Object.entries(PART_COLORS).map(([part, color]) => (
          <div key={part} style={{ display: "flex", alignItems: "center", gap: "5px", fontSize: "11px", color: "#475569" }}>
            <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: color, display: "inline-block" }} />
            {part}
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
        {/* Graph */}
        <div
          style={{
            flex: "1 1 540px",
            background: "#ffffff",
            borderRadius: "12px",
            border: "1px solid #e2e8f0",
            padding: "12px",
            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
          }}
        >
          <svg viewBox="0 0 840 560" style={{ width: "100%", height: "auto" }}>
            {/* Grid dots */}
            {Array.from({ length: 18 }, (_, i) =>
              Array.from({ length: 12 }, (_, j) => (
                <circle key={`${i}-${j}`} cx={i * 50 + 20} cy={j * 50 + 10} r="0.8" fill="#e2e8f0" />
              ))
            ).flat()}

            {/* Edges */}
            {edges.map((edge, i) => {
              const rKey = [edge.from, edge.to].sort().join("-");
              const siblings = edgesByRoute.get(rKey) || [edge];
              const idx = siblings.indexOf(edge);
              const isVisible = !selectedNode || edge.from === selectedNode || edge.to === selectedNode;

              return (
                <g key={i} opacity={isVisible ? 1 : 0.08}>
                  <EdgeLabel edge={edge} idx={idx} totalForRoute={siblings.length} />
                </g>
              );
            })}

            {/* Nodes */}
            {locations.map((loc) => {
              const pos = NODE_POSITIONS[loc];
              if (!pos) return null;
              return (
                <NetworkNode
                  key={loc}
                  id={loc}
                  x={pos.x}
                  y={pos.y}
                  isSelected={selectedNode === loc}
                  onClick={handleNodeClick}
                />
              );
            })}
          </svg>
        </div>

        {/* Side panel */}
        <div style={{ flex: "0 0 240px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <StatsPanel edges={edges} filterNode={selectedNode} />
        </div>
      </div>

      {/* Route table */}
      <div style={{ marginTop: "20px" }}>
        <div style={{ fontSize: "9px", textTransform: "uppercase", letterSpacing: "1.5px", color: "#94a3b8", marginBottom: "8px" }}>
          Route Details
        </div>
        <RouteTable edges={edges} filterNode={selectedNode} />
      </div>
    </div>
  );
}