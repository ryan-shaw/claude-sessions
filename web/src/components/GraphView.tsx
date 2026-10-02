import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d'
import type { Edge, EdgeType, PRInfo, PRState, Session } from '../types'
import { buildFolderTree, esc, graphSig, groupColors, neighbours, reuseNodes } from '../lib'
import { useSize } from '../useSize'

type N = { id: string; kind: 'folder' | 'session'; label: string; color: string; r: number; tip: string }
type L = { type: EdgeType; key?: string }
type Props = { sessions: Session[]; edges: Edge[]; colors: Record<string, string>; visibleIds: Set<string>; selected: string | null; live: Set<string>; prs: Record<string, PRInfo>; onSelect: (id: string | null) => void }
type LinkForce = { distance(f: (l: L) => number): LinkForce; strength(f: (l: L) => number): LinkForce }
type ChargeForce = { strength(n: number): ChargeForce }

const EDGE: Record<EdgeType, { label: string; color: string; solid: string }> = {
  folder: { label: 'Folders', color: 'rgba(161,161,170,0.3)', solid: 'rgb(161,161,170)' },
  files: { label: 'Shared files', color: 'rgba(96,165,250,0.6)', solid: 'rgb(96,165,250)' },
  related: { label: 'Related', color: 'rgba(251,191,36,0.6)', solid: 'rgb(251,191,36)' },
  pr: { label: 'PR / branch', color: 'rgba(248,113,113,0.75)', solid: 'rgb(248,113,113)' },
}
const DARK = window.matchMedia('(prefers-color-scheme: dark)').matches
const TEXT = DARK ? '#e4e4e7' : '#27272a'
const HALO = DARK ? '#09090b' : '#ffffff'
const MIXED = 'rgb(161,161,170)' // folder spanning several top-level groups
const PR_RGB: Record<PRState, string> = { open: '34,197,94', merged: '167,139,250', closed: '248,113,113', unknown: '161,161,170' }
const idOf = (x: unknown) => (typeof x === 'object' && x ? (x as N).id : (x as string))
const isFolderLink = (l: LinkObject<N, L>) => idOf(l.source).startsWith('f:') && idOf(l.target).startsWith('f:')

export default function GraphView({ sessions, edges, colors, visibleIds, selected, live, prs, onSelect }: Props) {
  const [box, size] = useSize<HTMLDivElement>()
  const fg = useRef<ForceGraphMethods<NodeObject<N>, LinkObject<N, L>> | undefined>(undefined)
  const [shown, setShown] = useState<Set<EdgeType>>(() => new Set(['folder']))
  const fitted = useRef(false)

  // node objects stay stable across edge toggles so the layout keeps its positions
  const tree = useMemo(() => buildFolderTree(sessions), [sessions])
  const groups = useMemo(() => groupColors(sessions), [sessions])
  const nodeCache = useRef(new Map<string, N>())
  const nodes = useMemo(() => {
    const out: N[] = tree.folders.map(f => ({ id: f.id, kind: 'folder', label: f.label, color: f.group ? groups[f.group] : MIXED,
      r: Math.min(18, 5 + Math.sqrt(f.count) * 1.2), tip: `${esc(f.path)}<br>${f.count} sessions` }))
    for (const s of sessions)
      out.push({ id: s.id, kind: 'session', label: s.title.slice(0, 48), color: colors[s.project],
        r: Math.min(16, 3 + Math.sqrt(s.messages) * 0.45), tip: `<b>${esc(s.title)}</b><br>${esc(s.project)}` })
    return reuseNodes(nodeCache.current, out) // keep layout positions across polls
  }, [sessions, colors, tree, groups])
  // folder links always stay in the simulation (they make the tree); others only when shown
  const links = useMemo(() => [...tree.links, ...edges.filter(e => shown.has(e.type))].map(e => ({ ...e })), [tree, edges, shown])
  // new graphData restarts the simulation, so only hand over a new object when the graph's shape changes
  const sig = graphSig(nodes, [...tree.links, ...edges.filter(e => shown.has(e.type))])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const data = useMemo(() => ({ nodes, links }), [sig])
  const focus = useMemo(() => (selected ? neighbours([...tree.links, ...edges], selected, shown) : null), [tree, edges, selected, shown])

  useEffect(() => {
    const g = fg.current
    if (!g) return
    ;(g.d3Force('link') as unknown as LinkForce | undefined)?.distance(l => (l.type !== 'folder' ? 90 : isFolderLink(l) ? 70 : 30)).strength(l => (l.type === 'folder' ? 0.7 : 0.03))
    ;(g.d3Force('charge') as unknown as ChargeForce | undefined)?.strength(-45)
    g.d3ReheatSimulation()
  }, [data, size.width > 0])

  useEffect(() => {
    const n = (selected ? nodeCache.current.get(selected) : undefined) as NodeObject<N> | undefined
    if (!fg.current || n?.x == null || n.y == null) return
    fg.current.centerAt(n.x, n.y, 600)
    fg.current.zoom(Math.max(fg.current.zoom(), 2.5), 600)
  }, [selected])

  const touches = (l: LinkObject<N, L>) => idOf(l.source) === selected || idOf(l.target) === selected

  return (
    <div ref={box} className="absolute inset-0">
      {size.width > 0 && (
        <ForceGraph2D ref={fg} width={size.width} height={size.height} graphData={data}
          backgroundColor="rgba(0,0,0,0)"
          cooldownTicks={200}
          onEngineStop={() => { if (!fitted.current) { fitted.current = true; fg.current?.zoomToFit(400, 40) } }}
          nodeLabel={n => n.tip}
          nodeCanvasObject={(n, ctx, scale) => {
            const x = n.x ?? 0, y = n.y ?? 0
            const dim = focus ? !focus.has(n.id) : n.kind === 'session' && !visibleIds.has(n.id)
            ctx.globalAlpha = dim ? 0.12 : 1
            ctx.fillStyle = n.color
            ctx.beginPath()
            if (n.kind === 'folder') ctx.roundRect(x - n.r, y - n.r, n.r * 2, n.r * 2, 2)
            else ctx.arc(x, y, n.r, 0, 2 * Math.PI)
            ctx.fill()
            if (n.id === selected) { ctx.lineWidth = 2 / scale; ctx.strokeStyle = TEXT; ctx.stroke() }
            if (n.kind === 'session' && live.has(n.id)) {
              // static halo: an animated ring would force 60fps redraws whenever anything is live
              ctx.beginPath()
              ctx.arc(x, y, n.r + 3 / scale + 1, 0, 2 * Math.PI)
              ctx.strokeStyle = 'rgba(34,197,94,0.9)'
              ctx.lineWidth = 2.5 / scale
              ctx.stroke()
            }
            ctx.globalAlpha = 1
          }}
          onRenderFramePost={(ctx, scale) => {
            // labels in a final pass so later-drawn nodes never cover them
            for (const n of nodes as NodeObject<N>[]) {
              const dim = focus ? !focus.has(n.id) : n.kind === 'session' && !visibleIds.has(n.id)
              if (!(n.kind === 'folder' ? !dim || !focus : n.id === selected || (scale >= 2 && !dim))) continue
              // world-unit font (shrinks when zoomed out) with a 9px on-screen floor, haloed for legibility
              const fs = Math.max(n.kind === 'folder' ? 9 : 4, 9 / scale)
              const x = n.x ?? 0, y = n.y ?? 0
              const ly = y + n.r + 1
              ctx.font = `${n.kind === 'folder' ? 600 : 400} ${fs}px system-ui, sans-serif`
              ctx.textAlign = 'center'
              ctx.textBaseline = 'top'
              ctx.lineJoin = 'round'
              ctx.lineWidth = fs / 3
              ctx.strokeStyle = HALO
              ctx.strokeText(n.label, x, ly)
              ctx.fillStyle = TEXT
              ctx.fillText(n.label, x, ly)
            }
          }}
          nodePointerAreaPaint={(n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x ?? 0, n.y ?? 0, n.r + 2, 0, 2 * Math.PI); ctx.fill() }}
          linkVisibility={l => shown.has(l.type)}
          linkColor={l => {
            const st = l.type === 'pr' && l.key ? prs[l.key]?.state : undefined
            const [c, solid] = st ? [`rgba(${PR_RGB[st]},0.75)`, `rgb(${PR_RGB[st]})`] : [EDGE[l.type].color, EDGE[l.type].solid]
            return !focus ? c : touches(l) ? solid : 'rgba(161,161,170,0.05)'
          }}
          linkLineDash={l => (l.type === 'related' ? [3, 2] : null)}
          linkWidth={l => (focus && touches(l) ? 2 : l.type === 'folder' ? 0.6 : 1.2)}
          onNodeClick={n => {
            if (n.kind === 'session') onSelect(n.id)
            else { fg.current?.centerAt(n.x, n.y, 600); fg.current?.zoom(3, 600) }
          }}
          onBackgroundClick={() => onSelect(null)}
        />
      )}
      <div className="absolute top-3 left-3 flex gap-1.5">
        {(Object.keys(EDGE) as EdgeType[]).map(t => (
          <button key={t} onClick={() => setShown(prev => { const next = new Set(prev); if (!next.delete(t)) next.add(t); return next })}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs backdrop-blur ${shown.has(t)
              ? 'border-zinc-300 bg-white/80 dark:border-zinc-600 dark:bg-zinc-800/80' : 'border-zinc-200 bg-white/40 text-zinc-400 dark:border-zinc-800 dark:bg-zinc-900/40'}`}>
            <span className="h-0.5 w-3 rounded" style={{ background: EDGE[t].solid }} />{EDGE[t].label}
          </button>
        ))}
      </div>
    </div>
  )
}
