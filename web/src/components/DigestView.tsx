import { useMemo, useState } from 'react'
import type { PRInfo, Session } from '../types'
import { groupOf, inRange, weekRange } from '../lib'
import Md from '../Md'
import { PRBadge } from './PRBadge'

type Props = { sessions: Session[]; colors: Record<string, string>; prs: Record<string, PRInfo>; onSelect: (id: string) => void }

export default function DigestView({ sessions, colors, prs, onSelect }: Props) {
  const [offset, setOffset] = useState(0)
  const [from, to] = useMemo(() => weekRange(offset), [offset])
  const [md, setMd] = useState<{ key: string; text?: string; err?: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const week = useMemo(() => sessions.filter(s => inRange(s, from, to)).sort((a, b) => (a.start ?? '').localeCompare(b.start ?? '')), [sessions, from, to])
  const groups = useMemo(() => {
    const g = new Map<string, Session[]>()
    for (const s of week) { const k = groupOf(s.project); g.set(k, [...(g.get(k) ?? []), s]) }
    return [...g.entries()].sort((a, b) => b[1].length - a[1].length)
  }, [week])
  const key = from.toISOString()
  const label = `${from.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} – ${new Date(+to - 1).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}`

  const write = () => {
    setMd({ key }); setCopied(false)
    fetch('/api/digest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from: from.toISOString(), to: to.toISOString() }) })
      .then(async r => (r.ok ? r.json() : Promise.reject(new Error((await r.json().catch(() => ({}))).error ?? `HTTP ${r.status}`))))
      .then(d => setMd({ key, text: d.markdown }))
      .catch(e => setMd({ key, err: String(e.message ?? e) }))
  }
  const current = md?.key === key ? md : null

  return (
    <div className="absolute inset-0 overflow-y-auto px-6 py-4">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button onClick={() => setOffset(o => o - 1)} className="rounded-md border border-zinc-200 px-2 py-0.5 dark:border-zinc-700">‹</button>
        <h2 className="text-base font-semibold">{label}</h2>
        <button onClick={() => setOffset(o => Math.min(0, o + 1))} disabled={offset === 0} className="rounded-md border border-zinc-200 px-2 py-0.5 disabled:opacity-30 dark:border-zinc-700">›</button>
        <span className="text-xs text-zinc-500">{week.length} sessions · ${week.reduce((a, s) => a + s.cost, 0).toFixed(2)}</span>
        <button onClick={write} disabled={!week.length || (!!current && !current.text && !current.err)}
          className="ml-auto rounded-md bg-zinc-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900">
          {current && !current.text && !current.err ? 'Writing…' : 'Write digest'}
        </button>
      </div>
      {current?.err && <p className="mb-4 text-sm text-red-500">{current.err}</p>}
      {current?.text && (
        <div className="mb-6 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
          <div className="mb-2 flex justify-end">
            <button onClick={() => navigator.clipboard.writeText(current.text!).then(() => setCopied(true))} className="rounded-md border border-zinc-300 px-2 py-0.5 text-xs dark:border-zinc-700">{copied ? 'Copied ✓' : 'Copy markdown'}</button>
          </div>
          <div className="md text-sm"><Md text={current.text} /></div>
        </div>
      )}
      {!week.length && <p className="text-sm text-zinc-500">No sessions this week.</p>}
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(320px,1fr))]">
        {groups.map(([g, list]) => (
          <section key={g} className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <span className="size-2 rounded-full" style={{ background: colors[list[0].project] }} />{g}
              <span className="font-normal text-zinc-500">· {list.length}</span>
            </h3>
            {list.map(s => (
              <button key={s.id} onClick={() => onSelect(s.id)} className="mb-1 block w-full rounded-lg px-2 py-1.5 text-left hover:bg-zinc-50 dark:hover:bg-zinc-900">
                <div className="text-sm font-medium">{s.title}</div>
                {s.summary && <div className="mt-0.5 text-xs text-zinc-600 dark:text-zinc-400">{s.summary}</div>}
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
                  {new Date(s.start!).toLocaleDateString(undefined, { weekday: 'short' })} · ${s.cost.toFixed(2)}
                  {s.prs.map(p => <PRBadge key={p.url} state={prs[p.url]?.state ?? 'unknown'}>#{p.number}</PRBadge>)}
                </div>
              </button>
            ))}
          </section>
        ))}
      </div>
    </div>
  )
}
