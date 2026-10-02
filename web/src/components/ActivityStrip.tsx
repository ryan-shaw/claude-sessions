import { useMemo, useRef, useState } from 'react'
import type { Session } from '../types'
import { day } from '../lib'

type Props = { sessions: Session[]; colors: Record<string, string>; range: [string, string] | null; onRange: (r: [string, string] | null) => void }
const H = 44

export default function ActivityStrip({ sessions, colors, range, onRange }: Props) {
  const { days, byDay, max } = useMemo(() => {
    const byDay = new Map<string, Session[]>()
    for (const s of sessions) {
      const d = day(s.start)
      if (!d) continue
      let g = byDay.get(d)
      if (!g) byDay.set(d, (g = []))
      g.push(s)
    }
    const keys = [...byDay.keys()].sort()
    const days: string[] = []
    if (keys.length)
      for (const d = new Date(keys[0]); d <= new Date(keys[keys.length - 1]); d.setUTCDate(d.getUTCDate() + 1)) days.push(d.toISOString().slice(0, 10))
    for (const g of byDay.values()) g.sort((a, b) => a.project.localeCompare(b.project))
    return { days, byDay, max: Math.max(1, ...[...byDay.values()].map(g => g.length)) }
  }, [sessions])
  const svg = useRef<SVGSVGElement>(null)
  const [drag, setDragState] = useState<[number, number] | null>(null)
  const dragRef = useRef<[number, number] | null>(null) // handlers read the ref: pointerup can land before a re-render
  const setDrag = (v: [number, number] | null) => { dragRef.current = v; setDragState(v) }
  const [hover, setHover] = useState<number | null>(null)
  if (!days.length) return null

  const idxAt = (clientX: number) => {
    const r = svg.current!.getBoundingClientRect()
    return Math.max(0, Math.min(days.length - 1, Math.floor(((clientX - r.left) / r.width) * days.length)))
  }
  const sel = drag ? [Math.min(...drag), Math.max(...drag)] : range ? [days.indexOf(range[0]), days.indexOf(range[1])] : null
  const finish = () => {
    const g = dragRef.current
    if (!g) return
    const a = Math.min(...g), b = Math.max(...g)
    setDrag(null)
    onRange(a === b && range ? null : [days[a], days[b]]) // click clears an active range; click with none = that day
  }

  return (
    <div className="border-b border-zinc-200 px-4 pt-2 pb-1 dark:border-zinc-800">
      <svg ref={svg} viewBox={`0 0 ${days.length} ${H}`} preserveAspectRatio="none" className="block h-11 w-full cursor-crosshair touch-none select-none"
        onPointerDown={e => { const i = idxAt(e.clientX); setDrag([i, i]) }}
        onPointerMove={e => { const i = idxAt(e.clientX); setHover(i); if (dragRef.current) setDrag([dragRef.current[0], i]) }}
        onPointerUp={finish}
        onPointerLeave={() => { setHover(null); finish() }}>
        {sel && <rect x={sel[0]} width={sel[1] - sel[0] + 1} y={0} height={H} className="fill-zinc-400/25" />}
        {days.flatMap((d, i) => {
          let y = H
          const h = (H - 2) / max
          return (byDay.get(d) ?? []).map(s => {
            y -= h
            return <rect key={s.id} x={i + 0.1} y={y} width={0.8} height={h} fill={colors[s.project]} opacity={sel && (i < sel[0] || i > sel[1]) ? 0.25 : 1} />
          })
        })}
      </svg>
      <div className="mt-0.5 flex justify-between text-[10px] text-zinc-500">
        <span>{days[0]}</span>
        <span>{hover !== null ? `${days[hover]} · ${(byDay.get(days[hover]) ?? []).length} sessions`
          : range ? `${range[0]} → ${range[1]} · click to clear` : 'Drag to filter by date'}</span>
        <span>{days[days.length - 1]}</span>
      </div>
    </div>
  )
}
