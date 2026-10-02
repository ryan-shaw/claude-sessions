import { useEffect, useMemo, useRef, useState } from 'react'
import { scaleTime } from 'd3-scale'
import type { Session } from '../types'
import { fmtDate, laneOrder } from '../lib'
import { useSize } from '../useSize'

type Props = { sessions: Session[]; colors: Record<string, string>; visibleIds: Set<string>; selected: string | null; live: Set<string>; onSelect: (id: string) => void }
const LANE = 26, GUTTER = 210, AXIS = 26, MIN_SPAN = 10 * 60e3
const short = (p: string) => (p.length > 32 ? '…' + p.slice(-31) : p)

export default function TimelineView({ sessions, colors, visibleIds, selected, live, onSelect }: Props) {
  const [box, size] = useSize<HTMLDivElement>()
  const svgRef = useRef<SVGSVGElement>(null)
  const lanes = useMemo(() => laneOrder(sessions), [sessions])
  const dated = useMemo(() => sessions.filter(s => s.start && s.end), [sessions])
  const full = useMemo((): [number, number] => {
    const t0 = Math.min(...dated.map(s => +new Date(s.start!))), t1 = Math.max(...dated.map(s => +new Date(s.end!)))
    const pad = (t1 - t0) * 0.02 || 36e5
    return [t0 - pad, t1 + pad]
  }, [dated])
  const [domain, setDomain] = useState<[number, number] | null>(null)
  const [tip, setTip] = useState<{ s: Session; x: number; y: number } | null>(null)
  const drag = useRef<{ x: number; d: [number, number]; moved: boolean } | null>(null)
  const width = Math.max(0, size.width - GUTTER)
  const d = domain ?? full

  useEffect(() => {
    const el = svgRef.current
    if (!el || !width) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const left = el.getBoundingClientRect().left + GUTTER
      setDomain(cur => {
        const [a, b] = cur ?? full
        const span = b - a
        if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) { const dt = (e.deltaX / width) * span; return [a + dt, b + dt] }
        const t = a + ((e.clientX - left) / width) * span
        const k = Math.min(Math.max(span * Math.exp(e.deltaY * 0.002), MIN_SPAN), (full[1] - full[0]) * 1.5) / span
        return [t - (t - a) * k, t + (b - t) * k]
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [full, width])

  if (!dated.length) return <p className="p-6 text-sm text-zinc-500">No dated sessions.</p>
  const x = scaleTime().domain(d).range([0, width])
  const laneIdx = new Map(lanes.map((p, i) => [p, i]))
  const height = AXIS + lanes.length * LANE
  const ticks = x.ticks(Math.max(2, Math.floor(width / 110)))
  const tickFmt = x.tickFormat()

  return (
    <div ref={box} className="absolute inset-0 overflow-x-hidden overflow-y-auto">
      {size.width > 0 && (
        <svg ref={svgRef} width={size.width} height={Math.max(height, size.height)} className="cursor-grab touch-none select-none active:cursor-grabbing"
          onPointerDown={e => { drag.current = { x: e.clientX, d, moved: false } }}
          onPointerMove={e => {
            const g = drag.current
            if (!g) return
            if (Math.abs(e.clientX - g.x) > 3) g.moved = true
            const dt = ((e.clientX - g.x) / width) * (g.d[1] - g.d[0])
            if (g.moved) setDomain([g.d[0] - dt, g.d[1] - dt])
          }}
          onPointerUp={() => setTimeout(() => (drag.current = null))}
          onPointerLeave={() => (drag.current = null)}
          onDoubleClick={() => setDomain(null)}>
          {lanes.map((p, i) => (
            <g key={p} transform={`translate(0,${AXIS + i * LANE})`}>
              {i % 2 === 0 && <rect width={size.width} height={LANE} className="fill-zinc-500/5" />}
              <circle cx={14} cy={LANE / 2} r={4} fill={colors[p]} />
              <text x={24} y={LANE / 2} dominantBaseline="middle" className="fill-zinc-600 text-[11px] dark:fill-zinc-400"><title>{p}</title>{short(p)}</text>
            </g>
          ))}
          <g transform={`translate(${GUTTER},0)`}>
            {ticks.map(t => (
              <g key={+t} transform={`translate(${x(t)},0)`}>
                <line y1={AXIS - 4} y2={height} className="stroke-zinc-200 dark:stroke-zinc-800" />
                <text y={AXIS - 9} textAnchor="middle" className="fill-zinc-500 text-[10px]">{tickFmt(t)}</text>
              </g>
            ))}
          </g>
          <svg x={GUTTER} y={AXIS} width={width} height={lanes.length * LANE} overflow="hidden">
            {dated.map(s => {
              const x0 = x(new Date(s.start!)), x1 = x(new Date(s.end!))
              if (x1 < 0 || x0 > width) return null
              return (
                <rect key={s.id} x={x0} y={laneIdx.get(s.project)! * LANE + 5} width={Math.max(3, x1 - x0)} height={LANE - 10} rx={3}
                  fill={colors[s.project]} opacity={visibleIds.has(s.id) ? 0.9 : 0.15}
                  stroke={s.id === selected ? 'currentColor' : live.has(s.id) ? '#22c55e' : 'none'} strokeWidth={2}
                  className={`cursor-pointer ${live.has(s.id) ? 'animate-pulse' : ''}`}
                  onPointerEnter={e => setTip({ s, x: e.clientX, y: e.clientY })} onPointerLeave={() => setTip(null)}
                  onClick={() => { if (!drag.current?.moved) onSelect(s.id) }} />
              )
            })}
          </svg>
        </svg>
      )}
      {tip && (
        <div className="pointer-events-none fixed z-10 max-w-xs rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
          style={{ left: tip.x + 12, top: tip.y + 12 }}>
          <div className="font-medium">{tip.s.title}</div>
          <div className="mt-0.5 text-zinc-500">{fmtDate(tip.s.start)} → {fmtDate(tip.s.end)} · ${tip.s.cost.toFixed(2)}</div>
        </div>
      )}
      <div className="pointer-events-none absolute right-3 bottom-3 text-[10px] text-zinc-500">scroll to zoom · drag to pan · double-click to reset</div>
    </div>
  )
}
