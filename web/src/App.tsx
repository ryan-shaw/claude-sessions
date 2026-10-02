import { useEffect, useMemo, useRef, useState } from 'react'
import type { PRInfo, Session } from './types'
import { buildEdges, isLive, matches, projectColors, type Filters, type PRFilter } from './lib'
import ActivityStrip from './components/ActivityStrip'
import SessionList from './components/SessionList'
import GraphView from './components/GraphView'
import TimelineView from './components/TimelineView'
import Drawer from './components/Drawer'
import DigestView from './components/DigestView'
import AskPanel from './components/AskPanel'

const control = 'rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-sm outline-none focus:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900 dark:focus:border-zinc-600'
const POLL_MS = 3000

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [prs, setPrs] = useState<Record<string, PRInfo>>({})
  const [now, setNow] = useState(() => Date.now())
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Map<string, string> | null>(null)
  const [filters, setFilters] = useState<Filters>({ project: '', pr: '', file: null, range: null })
  const [view, setView] = useState<'graph' | 'timeline' | 'digest'>('graph')
  const [selected, setSelected] = useState<string | null>(null)
  const [mode, setMode] = useState<'search' | 'ask'>('search')
  const [asked, setAsked] = useState<{ q: string; n: number } | null>(null) // n: each submit re-asks, even the same text
  const searchRef = useRef<HTMLInputElement>(null)

  // poll a cheap version endpoint; refetch only what changed
  useEffect(() => {
    let seen = { sessions: -1, prs: -1, summaries: -1 }
    let stop = false
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      try {
        const v: { sessions: number; prs: number; summaries: number } = await (await fetch('/api/version')).json()
        if (v.sessions !== seen.sessions || v.summaries !== seen.summaries) setSessions(await (await fetch('/api/sessions')).json())
        if (v.sessions !== seen.sessions || v.prs !== seen.prs) setPrs(await (await fetch('/api/prs')).json())
        seen = v
        setError('')
      } catch (e) {
        setError(String((e as Error).message ?? e))
      }
      setNow(Date.now())
      if (!stop) timer = setTimeout(tick, POLL_MS)
    }
    timer = setTimeout(tick, 0)
    return () => { stop = true; clearTimeout(timer) }
  }, [])

  useEffect(() => {
    const q = mode === 'ask' ? '' : query.trim()
    if (!q) { setHits(null); return }
    const ctl = new AbortController()
    const t = setTimeout(() => {
      fetch('/api/search?q=' + encodeURIComponent(q), { signal: ctl.signal }).then(r => r.json())
        .then((res: { id: string; snippet: string }[]) => setHits(new Map(res.map(h => [h.id, h.snippet]))))
        .catch(() => {})
    }, 250)
    return () => { clearTimeout(t); ctl.abort() }
  }, [query, mode])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); searchRef.current?.focus() }
      if (e.key === 'Escape') setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const colors = useMemo(() => projectColors(sessions), [sessions])
  const edges = useMemo(() => buildEdges(sessions), [sessions])
  const projects = Object.keys(colors).sort()
  const byId = useMemo(() => new Map(sessions.map(s => [s.id, s])), [sessions])
  const live = useMemo(() => new Set(sessions.filter(s => isLive(s, now)).map(s => s.id)), [sessions, now])
  const visible = useMemo(() => sessions.filter(s => matches(s, filters, hits, prs)), [sessions, filters, hits, prs])
  const visibleIds = useMemo(() => new Set(visible.map(s => s.id)), [visible])
  const totalCost = sessions.reduce((a, s) => a + s.cost, 0)

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-200 px-4 py-2.5 dark:border-zinc-800">
        <div className="flex items-baseline gap-2">
          <h1 className="text-[15px] font-semibold tracking-tight">Claude Sessions</h1>
          <span className="text-xs text-zinc-500">{sessions.length} sessions · {projects.length} projects · ${totalCost.toFixed(2)}</span>
        </div>
        {live.size > 0 && (
          <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <span className="size-2 animate-pulse rounded-full bg-emerald-500" />{live.size} live
          </span>
        )}
        <form className="relative flex max-w-xl min-w-64 flex-1" onSubmit={e => { e.preventDefault(); if (mode === 'ask' && query.trim()) setAsked({ q: query.trim(), n: Date.now() }) }}>
          <button type="button" onClick={() => setMode(m => (m === 'ask' ? 'search' : 'ask'))} title="Toggle Ask your history"
            className={`mr-1.5 shrink-0 rounded-lg px-2.5 text-xs font-medium ${mode === 'ask' ? 'bg-blue-600 text-white' : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'}`}>
            {mode === 'ask' ? 'Ask ✦' : 'Ask'}
          </button>
          <input ref={searchRef} value={query} onChange={e => setQuery(e.target.value)}
            placeholder={mode === 'ask' ? 'Ask your history… (Enter)' : 'Search every session…'} className={`${control} w-full pr-12`} />
          <kbd className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 rounded border border-zinc-300 px-1 text-[10px] text-zinc-500 dark:border-zinc-700">⌘K</kbd>
        </form>
        <select value={filters.project} onChange={e => setFilters(f => ({ ...f, project: e.target.value }))} className={`${control} max-w-56`}>
          <option value="">All projects</option>
          {projects.map(p => <option key={p}>{p}</option>)}
        </select>
        <select value={filters.pr} onChange={e => setFilters(f => ({ ...f, pr: e.target.value as PRFilter }))} className={control}>
          <option value="">All sessions</option>
          <option value="any">Has PR</option>
          <option value="open">PR open</option>
          <option value="merged">PR merged</option>
          <option value="unmerged">PR not merged</option>
        </select>
        {filters.file && (
          <button onClick={() => setFilters(f => ({ ...f, file: null }))} title={filters.file}
            className="flex max-w-72 items-center gap-1 rounded-full bg-blue-500/15 px-2.5 py-1 text-xs text-blue-700 dark:text-blue-300">
            <span className="truncate">file: {filters.file}</span> ✕
          </button>
        )}
        <div className="ml-auto flex rounded-lg bg-zinc-100 p-0.5 text-sm dark:bg-zinc-900">
          {(['graph', 'timeline', 'digest'] as const).map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`rounded-md px-3 py-1 capitalize ${view === v ? 'bg-white shadow-sm dark:bg-zinc-700' : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'}`}>{v}</button>
          ))}
        </div>
      </header>
      <ActivityStrip sessions={sessions} colors={colors} range={filters.range} onRange={range => setFilters(f => ({ ...f, range }))} />
      {error && <p className="px-4 py-1 text-xs text-red-500">Can't reach the server: {error}</p>}
      <main className="flex min-h-0 flex-1">
        <SessionList sessions={visible} colors={colors} hits={hits} selected={selected} live={live} prs={prs} onSelect={setSelected} />
        <div className="relative min-w-0 flex-1">
          {view === 'graph'
            ? <GraphView sessions={sessions} edges={edges} colors={colors} visibleIds={visibleIds} selected={selected} live={live} prs={prs} onSelect={setSelected} />
            : view === 'timeline'
              ? <TimelineView sessions={sessions} colors={colors} visibleIds={visibleIds} selected={selected} live={live} onSelect={setSelected} />
              : <DigestView sessions={visible} colors={colors} prs={prs} onSelect={setSelected} />}
          {asked && <AskPanel key={asked.n} q={asked.q} byId={byId} onSelect={setSelected} onClose={() => setAsked(null)} />}
        </div>
        {selected && (
          <Drawer id={selected} mtime={byId.get(selected)?.mtime ?? 0} colors={colors} byId={byId} prs={prs}
            onClose={() => setSelected(null)} onSelect={setSelected} onFile={file => setFilters(f => ({ ...f, file }))} />
        )}
      </main>
    </div>
  )
}
