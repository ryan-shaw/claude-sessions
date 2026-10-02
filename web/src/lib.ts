import type { Edge, EdgeType, Folder, PRInfo, PRState, Session } from './types'

export const FILE_CAP = 15
export const TRUNK = new Set(['main', 'master', 'develop', 'HEAD'])
export type PRFilter = '' | 'any' | 'open' | 'merged' | 'unmerged'
export type Filters = { project: string; pr: PRFilter; file: string | null; range: [string, string] | null }
export const LIVE_SECS = 120
export const isLive = (s: Session, nowMs: number) => nowMs / 1000 - s.mtime < LIVE_SECS
export const prStates = (s: Session, prs: Record<string, PRInfo>): PRState[] => s.prs.map(p => prs[p.url]?.state ?? 'unknown')
export function prSummaryState(states: PRState[]): PRState | null {
  if (!states.length) return null
  if (states.includes('open')) return 'open'
  if (states.includes('merged')) return 'merged'
  return states.every(s => s === 'closed') ? 'closed' : 'unknown'
}

export const folderId = (p: string) => 'f:' + p
export const groupOf = (project: string) => project.split('/')[0]
export const day = (t: string | null) => (t ?? '').slice(0, 10)

function pairEdges(sessions: Session[], keysOf: (s: Session) => string[], type: EdgeType, out: Edge[], seen: Set<string>) {
  const groups = new Map<string, string[]>()
  for (const s of sessions)
    for (const k of new Set(keysOf(s))) {
      let g = groups.get(k)
      if (!g) groups.set(k, (g = []))
      g.push(s.id)
    }
  for (const [k, ids] of groups) {
    if (ids.length < 2 || ids.length > FILE_CAP) continue // ponytail: cap stops CLAUDE.md-style hubs from hairballing
    for (let i = 0; i < ids.length; i++)
      for (let j = i + 1; j < ids.length; j++) {
        const key = type + ':' + [ids[i], ids[j]].sort().join('|')
        if (!seen.has(key)) {
          seen.add(key)
          out.push({ source: ids[i], target: ids[j], type, key: k })
        }
      }
  }
}

export function buildEdges(sessions: Session[]): Edge[] {
  const out: Edge[] = []
  const seen = new Set<string>()
  pairEdges(sessions, s => s.file_keys, 'files', out, seen)
  pairEdges(sessions, s => [...s.prs.map(p => p.url), ...s.branches.filter(b => !TRUNK.has(b)).map(b => 'branch:' + b)], 'pr', out, seen)
  const ids = new Set(sessions.map(s => s.id))
  for (const s of sessions)
    for (const r of s.related) {
      const key = 'related:' + [s.id, r.id].sort().join('|')
      if (ids.has(r.id) && !seen.has(key)) {
        seen.add(key)
        out.push({ source: s.id, target: r.id, type: 'related' })
      }
    }
  return out
}

export function laneOrder(sessions: Session[]): string[] {
  const latest = new Map<string, string>()
  for (const s of sessions) {
    const e = s.end ?? ''
    if (!latest.has(s.project) || e > latest.get(s.project)!) latest.set(s.project, e)
  }
  return [...latest.keys()].sort((a, b) => latest.get(b)!.localeCompare(latest.get(a)!) || a.localeCompare(b))
}

export function groupColors(sessions: Session[]): Record<string, string> {
  const groups = [...new Set(sessions.map(s => groupOf(s.project)))].sort()
  // golden-angle hues: adjacent groups get far-apart colours
  return Object.fromEntries(groups.map((g, i) => [g, `hsl(${Math.round((i * 137.5) % 360)}, 62%, 58%)`]))
}

// one colour per top-level folder, so a folder's subprojects read as one family
export function projectColors(sessions: Session[]): Record<string, string> {
  const g = groupColors(sessions)
  return Object.fromEntries(sessions.map(s => [s.project, g[groupOf(s.project)]]))
}

const split = (p: string) => p.replace(/\/+$/, '').split('/').filter(Boolean)
const join = (segs: string[]) => '/' + segs.join('/')

// Folder hierarchy of every session cwd, rooted at their deepest common ancestor. Folders with no
// sessions and a single child are collapsed into their child (label 'a/…/z'), so deep repo paths
// don't become ladders of empty nodes.
export function buildFolderTree(sessions: Session[]): { folders: Folder[]; links: Edge[] } {
  if (!sessions.length) return { folders: [], links: [] }
  const paths = sessions.map(s => split(s.cwd))
  let depth = 0
  while (paths.every(p => p.length > depth && p[depth] === paths[0][depth])) depth++
  type T = { segs: string[]; count: number; own: number; groups: Set<string>; kids: Set<string> }
  const nodes = new Map<string, T>()
  sessions.forEach((s, i) => {
    const segs = paths[i]
    for (let d = depth; d <= segs.length; d++) {
      const key = join(segs.slice(0, d))
      let n = nodes.get(key)
      if (!n) nodes.set(key, (n = { segs: segs.slice(0, d), count: 0, own: 0, groups: new Set(), kids: new Set() }))
      n.count++
      n.groups.add(groupOf(s.project))
      if (d < segs.length) n.kids.add(join(segs.slice(0, d + 1)))
      else n.own++
    }
  })
  const rootKey = join(paths[0].slice(0, depth))
  const kept = (k: string) => k === rootKey || nodes.get(k)!.own > 0 || nodes.get(k)!.kids.size > 1
  const folders: Folder[] = []
  const links: Edge[] = []
  for (const [key, n] of nodes) {
    if (!kept(key)) continue
    let up = n.segs.length - 1
    while (up >= depth && !kept(join(n.segs.slice(0, up)))) up--
    const rel = n.segs.slice(up)
    const label = key === rootKey ? key : rel.length > 2 ? `${rel[0]}/…/${rel[rel.length - 1]}` : rel.join('/')
    folders.push({ id: folderId(key), path: key, label, count: n.count, group: n.groups.size === 1 ? [...n.groups][0] : null })
    if (key !== rootKey) links.push({ source: folderId(key), target: folderId(join(n.segs.slice(0, up))), type: 'folder' })
  }
  sessions.forEach((s, i) => links.push({ source: s.id, target: folderId(join(paths[i])), type: 'folder' }))
  folders.sort((a, b) => a.path.localeCompare(b.path))
  return { folders, links }
}

export function matches(s: Session, f: Filters, hits: Map<string, string> | null, prs: Record<string, PRInfo> = {}) {
  const d = day(s.start)
  const st = prStates(s, prs)
  const prOk = !f.pr || (st.length > 0 && (f.pr === 'any' || (f.pr === 'unmerged' ? !st.includes('merged') : st.includes(f.pr))))
  return (!f.project || s.project === f.project) && prOk && (!f.file || s.file_keys.includes(f.file)) &&
    (!hits || hits.has(s.id)) && (!f.range || (d >= f.range[0] && d <= f.range[1]))
}

export function neighbours(edges: Edge[], id: string, shown: Set<EdgeType>): Set<string> {
  const out = new Set([id])
  for (const e of edges) {
    if (!shown.has(e.type)) continue
    if (e.source === id) out.add(e.target)
    else if (e.target === id) out.add(e.source)
  }
  return out
}

const ENT: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
export const esc = (s: string) => s.replace(/[&<>"']/g, c => ENT[c])
export const resumeCommand = (s: Session) => `cd '${s.cwd.replace(/'/g, `'\\''`)}' && claude --resume ${s.id}`
export const fmtDate = (t: string | null) => (t ? new Date(t).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '')
export function ago(t: string | null) {
  if (!t) return ''
  const d = (Date.now() - +new Date(t)) / 864e5
  return d < 1 ? 'today' : d < 2 ? 'yesterday' : d < 30 ? `${Math.floor(d)}d ago` : new Date(t).toLocaleDateString()
}

// Reuse node objects by id so the force layout keeps positions (x/y live on the objects) across polls.
export function reuseNodes<T extends { id: string }>(cache: Map<string, T>, next: T[]): T[] {
  const out = next.map(n => {
    const old = cache.get(n.id)
    return old ? Object.assign(old, n) : n
  })
  cache.clear()
  for (const n of out) cache.set(n.id, n)
  return out
}

// Identity of the graph's shape: new graphData (which restarts the simulation) only when this changes.
export const graphSig = (nodes: { id: string }[], links: { source: string; target: string; type: string }[]) =>
  nodes.map(n => n.id).join(',') + '|' + links.map(l => `${l.source}>${l.target}:${l.type}`).join(',')

export function weekRange(offset: number, now = new Date()): [Date, Date] {
  const a = new Date(now)
  a.setHours(0, 0, 0, 0)
  a.setDate(a.getDate() - ((a.getDay() + 6) % 7) + offset * 7) // back to Monday
  const b = new Date(a)
  b.setDate(b.getDate() + 7)
  return [a, b]
}

export const inRange = (s: Session, from: Date, to: Date) =>
  !!s.start && s.start >= from.toISOString().slice(0, 19) && s.start < to.toISOString().slice(0, 19)

export const linkCitations = (md: string, byId: Map<string, Session>) =>
  md.replace(/\[\[([\w-]+)\]\]/g, (m, id: string) => {
    const s = byId.get(id)
    return s ? `[${s.title.replace(/[[\]]/g, '')}](#s:${id})` : m
  })

export type View = 'graph' | 'timeline' | 'digest'
export type UrlState = { view: View; selected: string | null; query: string; filters: Filters }
export const NO_FILTERS: Filters = { project: '', pr: '', file: null, range: null }
const PR_FILTERS = ['any', 'open', 'merged', 'unmerged']

// view, selection, search and filters live in the URL hash so reloads and bookmarks keep your place
export function toHash({ view, selected, query, filters: f }: UrlState): string {
  const p = new URLSearchParams()
  if (view !== 'graph') p.set('view', view)
  if (selected) p.set('s', selected)
  if (query) p.set('q', query)
  if (f.project) p.set('project', f.project)
  if (f.pr) p.set('pr', f.pr)
  if (f.file) p.set('file', f.file)
  if (f.range) p.set('range', f.range.join('..'))
  return p.toString()
}

export function fromHash(hash: string): UrlState {
  const p = new URLSearchParams(hash.replace(/^#/, ''))
  const view = p.get('view'), pr = p.get('pr') ?? '', range = p.get('range')?.split('..')
  return {
    view: view === 'timeline' || view === 'digest' ? view : 'graph',
    selected: p.get('s'), query: p.get('q') ?? '',
    filters: { project: p.get('project') ?? '', pr: (PR_FILTERS.includes(pr) ? pr : '') as PRFilter, file: p.get('file'),
      range: range?.length === 2 ? [range[0], range[1]] : null },
  }
}

// next/previous id in the list for ↑/↓; from no (or a filtered-out) selection, start at the near end
export function step(ids: string[], cur: string | null, d: 1 | -1): string | null {
  const i = cur ? ids.indexOf(cur) : -1
  if (i < 0) return ids[d > 0 ? 0 : ids.length - 1] ?? null
  return ids[Math.min(ids.length - 1, Math.max(0, i + d))]
}
