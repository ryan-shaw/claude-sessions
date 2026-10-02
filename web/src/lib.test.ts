import { expect, test } from 'vitest'
import { FILE_CAP, LIVE_SECS, buildEdges, buildFolderTree, esc, graphSig, inRange, isLive, linkCitations, weekRange, reuseNodes, laneOrder, matches, neighbours, prSummaryState, projectColors, resumeCommand, fromHash, step, toHash, NO_FILTERS, type Filters } from './lib'
import type { Session } from './types'

const mk = (id: string, o: Partial<Session> = {}): Session => ({
  id, cwd: '/x', project: 'a', branches: [], title: id, start: '2026-01-01T00:00:00Z', end: '2026-01-01T01:00:00Z',
  messages: 1, cost: 0, added: 0, removed: 0, prs: [], files: [], subagents: 0, mtime: 0, file_keys: [], related: [], ...o,
})
const of = (es: ReturnType<typeof buildEdges>, t: string) => es.filter(e => e.type === t).map(e => `${e.source}-${e.target}`).sort()

test('buildEdges no longer makes project edges (the folder tree does)', () => {
  expect(buildEdges([mk('s1'), mk('s2')])).toEqual([])
})

const tree = (...cwds: [string, string][]) => buildFolderTree(cwds.map(([id, cwd]) => mk(id, { cwd, project: cwd.split('/').slice(3).join('/') || 'h' })))
const pairs = (t: ReturnType<typeof buildFolderTree>) => t.links.map(e => `${e.source}>${e.target}`).sort()

test('folder tree roots at the common ancestor, collapsing empty single-child folders', () => {
  const t = tree(['a', '/h/Dev/dd/api'], ['b', '/h/Dev/dd/core'], ['c', '/h'])
  // /h/Dev has one child and no sessions, so it collapses into dd's label
  expect(t.folders.map(f => [f.path, f.label, f.count])).toEqual([
    ['/h', '/h', 3], ['/h/Dev/dd', 'Dev/dd', 2], ['/h/Dev/dd/api', 'api', 1], ['/h/Dev/dd/core', 'core', 1],
  ])
  expect(pairs(t)).toEqual(['a>f:/h/Dev/dd/api', 'b>f:/h/Dev/dd/core', 'c>f:/h', 'f:/h/Dev/dd/api>f:/h/Dev/dd', 'f:/h/Dev/dd/core>f:/h/Dev/dd', 'f:/h/Dev/dd>f:/h'].sort())
  expect(t.links.every(e => e.type === 'folder')).toBe(true)
})

test('long chains get a first/…/last label', () => {
  const t = tree(['a', '/h/a'], ['b', '/h/x/1/2/3/4'])
  expect(t.folders.find(f => f.path === '/h/x/1/2/3/4')?.label).toBe('x/…/4')
})

test('a folder holding sessions is kept even with a single child', () => {
  const t = tree(['a', '/h/a'], ['b', '/h/a/b'], ['c', '/h/c'])
  expect(pairs(t)).toContain('f:/h/a/b>f:/h/a')
})

test('folder group is shared when everything beneath is one top-level project, else null', () => {
  const t = buildFolderTree([mk('a', { cwd: '/h/D/dd/x', project: 'dd/x' }), mk('b', { cwd: '/h/D/dd/y', project: 'dd/y' }), mk('c', { cwd: '/h/D/tk', project: 'tk' })])
  const g = Object.fromEntries(t.folders.map(f => [f.path, f.group]))
  expect(g['/h/D/dd']).toBe('dd')
  expect(g['/h/D']).toBe(null)
})

test('projects in the same top-level folder share a colour', () => {
  const c = projectColors([mk('1', { project: 'dd' }), mk('2', { project: 'dd/api' }), mk('3', { project: 'tk/x' })])
  expect(c['dd']).toBe(c['dd/api'])
  expect(c['dd']).not.toBe(c['tk/x'])
})

test('sessions sharing several files are linked once', () => {
  expect(of(buildEdges([mk('s1', { file_keys: ['/f', '/g'] }), mk('s2', { file_keys: ['/f', '/g'] })]), 'files')).toEqual(['s1-s2'])
})

test('a file touched by more than FILE_CAP sessions makes no edges', () => {
  const many = Array.from({ length: FILE_CAP + 1 }, (_, i) => mk('s' + i, { file_keys: ['/CLAUDE.md'] }))
  expect(of(buildEdges(many), 'files')).toEqual([])
})

test('feature branches and PRs link, trunk branches do not', () => {
  const pr = { repo: 'r', number: 1, url: 'https://x/pull/1' }
  const es = buildEdges([
    mk('a1', { branches: ['main', 'DD-1'] }), mk('a2', { branches: ['main', 'DD-1'] }),
    mk('a3', { branches: ['main'], prs: [pr] }), mk('a4', { prs: [pr] }), mk('a5', { branches: ['main'] }),
  ])
  expect(of(es, 'pr')).toEqual(['a1-a2', 'a3-a4'])
})

test('laneOrder puts the most recently active project first', () => {
  expect(laneOrder([mk('1', { project: 'old', end: '2026-01-01T00:00:00Z' }), mk('2', { project: 'new', end: '2026-03-01T00:00:00Z' }),
    mk('3', { project: 'old', end: '2026-02-01T00:00:00Z' })])).toEqual(['new', 'old'])
})

test('matches applies project, PR state, file, search hits and an inclusive day range', () => {
  const pr = { repo: 'r', number: 1, url: 'https://github.com/r/x/pull/1' }
  const s = mk('s', { start: '2026-02-03T10:00:00Z', prs: [pr], file_keys: ['repo:a.py'] })
  const f: Filters = { project: '', pr: '', file: null, range: null }
  const prs = { [pr.url]: { state: 'open' as const, title: null } }
  expect(matches(s, f, null)).toBe(true)
  expect(matches(s, { ...f, project: 'b' }, null)).toBe(false)
  expect(matches(mk('n'), { ...f, pr: 'any' }, null)).toBe(false)
  expect(matches(s, { ...f, pr: 'open' }, null, prs)).toBe(true)
  expect(matches(s, { ...f, pr: 'merged' }, null, prs)).toBe(false)
  expect(matches(s, { ...f, pr: 'unmerged' }, null, prs)).toBe(true)
  expect(matches(s, { ...f, file: 'repo:a.py' }, null)).toBe(true)
  expect(matches(s, { ...f, file: 'repo:b.py' }, null)).toBe(false)
  expect(matches(s, f, new Map())).toBe(false)
  expect(matches(s, { ...f, range: ['2026-02-03', '2026-02-03'] }, null)).toBe(true)
  expect(matches(s, { ...f, range: ['2026-02-04', '2026-02-09'] }, null)).toBe(false)
})

test('isLive is true only within LIVE_SECS of the last write', () => {
  const now = 1_000_000_000
  expect(isLive(mk('a', { mtime: now / 1000 - 10 }), now)).toBe(true)
  expect(isLive(mk('a', { mtime: now / 1000 - LIVE_SECS - 1 }), now)).toBe(false)
})

test('prSummaryState prefers open, then merged, then all-closed, else unknown', () => {
  expect(prSummaryState([])).toBe(null)
  expect(prSummaryState(['merged', 'open'])).toBe('open')
  expect(prSummaryState(['closed', 'merged'])).toBe('merged')
  expect(prSummaryState(['closed', 'closed'])).toBe('closed')
  expect(prSummaryState(['closed', 'unknown'])).toBe('unknown')
})

test('related edges are deduped and PR edges carry their key', () => {
  const pr = { repo: 'r', number: 1, url: 'https://x/pull/1' }
  const es = buildEdges([
    mk('a', { related: [{ id: 'b', score: 0.5 }], prs: [pr] }),
    mk('b', { related: [{ id: 'a', score: 0.5 }, { id: 'gone', score: 0.9 }], prs: [pr] }),
  ])
  expect(of(es, 'related')).toEqual(['a-b'])
  expect(es.find(e => e.type === 'pr')?.key).toBe(pr.url)
})

test('neighbours only follows shown edge types', () => {
  const ss = [mk('s1', { file_keys: ['/f'] }), mk('s2', { file_keys: ['/f'] })]
  const es = [...buildFolderTree(ss).links, ...buildEdges(ss)]
  expect([...neighbours(es, 's1', new Set(['folder']))].sort()).toEqual(['f:/x', 's1'])
  expect([...neighbours(es, 's1', new Set(['files']))].sort()).toEqual(['s1', 's2'])
})

test('esc neutralises HTML for the graph tooltip', () => {
  expect(esc(`<img src=x onerror="a('b')">&`)).toBe('&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;&amp;')
})

test('resumeCommand quotes a cwd containing a single quote', () => {
  expect(resumeCommand(mk('abc', { cwd: "/Users/me/it's here" }))).toBe(`cd '/Users/me/it'\\''s here' && claude --resume abc`)
})

test('reuseNodes keeps existing node objects (and their layout positions) across polls', () => {
  const cache = new Map<string, { id: string; label: string; x?: number }>()
  const first = reuseNodes(cache, [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }])
  first[0].x = 42 // the force layout writes positions onto the objects
  const second = reuseNodes(cache, [{ id: 'a', label: 'A2' }, { id: 'c', label: 'C' }])
  expect(second[0]).toBe(first[0])
  expect(second[0]).toMatchObject({ x: 42, label: 'A2' })
  expect([...cache.keys()]).toEqual(['a', 'c'])
})

test('graphSig only changes when the node or link set changes', () => {
  const n = [{ id: 'a' }, { id: 'b' }]
  const l = [{ source: 'a', target: 'b', type: 'folder' as const }]
  expect(graphSig(n, l)).toBe(graphSig([{ id: 'a' }, { id: 'b' }], [{ source: 'a', target: 'b', type: 'folder' }]))
  expect(graphSig(n, l)).not.toBe(graphSig(n, []))
})

test('weekRange starts on Monday 00:00 local and spans 7 days', () => {
  const [a, b] = weekRange(0, new Date(2026, 9, 7, 15, 30)) // Wed 7 Oct 2026
  expect([a.getFullYear(), a.getMonth(), a.getDate(), a.getDay(), a.getHours()]).toEqual([2026, 9, 5, 1, 0])
  expect((+b - +a) / 864e5).toBeCloseTo(7, 1)
  const [p] = weekRange(-1, new Date(2026, 9, 5, 0, 0)) // Monday itself, previous week
  expect(p.getDate()).toBe(28)
})

test('inRange compares ISO start times to the half-open range', () => {
  const from = new Date('2026-10-05T00:00:00Z'), to = new Date('2026-10-12T00:00:00Z')
  expect(inRange(mk('a', { start: '2026-10-05T00:00:00Z' }), from, to)).toBe(true)
  expect(inRange(mk('a', { start: '2026-10-12T00:00:00Z' }), from, to)).toBe(false)
  expect(inRange(mk('a', { start: null }), from, to)).toBe(false)
})

test('linkCitations turns [[id]] into session links and leaves unknown ids alone', () => {
  const byId = new Map([['abc-123', mk('abc-123', { title: 'Fix [login]' })]])
  expect(linkCitations('See [[abc-123]] and [[nope]].', byId)).toBe('See [Fix login](#s:abc-123) and [[nope]].')
})

test('URL hash round-trips state and ignores junk', () => {
  const st = { view: 'timeline' as const, selected: 'abc', query: 'redis cache', filters: { project: 'acme/api', pr: 'open' as const, file: 'api:a b.py', range: ['2026-01-01', '2026-01-07'] as [string, string] } }
  expect(fromHash('#' + toHash(st))).toEqual(st)
  expect(toHash({ view: 'graph', selected: null, query: '', filters: NO_FILTERS })).toBe('')
  expect(fromHash('#view=evil&pr=nope&range=x')).toEqual({ view: 'graph', selected: null, query: '', filters: NO_FILTERS })
})

test('step moves through the list and clamps at the ends', () => {
  const ids = ['a', 'b', 'c']
  expect(step(ids, null, 1)).toBe('a')
  expect(step(ids, null, -1)).toBe('c')
  expect(step(ids, 'gone', 1)).toBe('a')
  expect(step(ids, 'b', 1)).toBe('c')
  expect(step(ids, 'c', 1)).toBe('c')
  expect(step(ids, 'a', -1)).toBe('a')
  expect(step([], null, 1)).toBe(null)
})
