import type { PRInfo, Session } from '../types'
import { ago, prStates, prSummaryState } from '../lib'
import { PRBadge } from './PRBadge'

type Props = {
  sessions: Session[]; colors: Record<string, string>; hits: Map<string, string> | null; selected: string | null
  live: Set<string>; prs: Record<string, PRInfo>; onSelect: (id: string) => void
}

export default function SessionList({ sessions, colors, hits, selected, live, prs, onSelect }: Props) {
  return (
    <aside className="w-80 shrink-0 overflow-y-auto border-r border-zinc-200 p-2 dark:border-zinc-800">
      <div className="px-2 pb-1 text-xs text-zinc-500">{sessions.length} shown</div>
      {sessions.map(s => {
        const st = prSummaryState(prStates(s, prs))
        return (
          <button key={s.id} onClick={() => onSelect(s.id)}
            className={`mb-0.5 block w-full rounded-lg px-3 py-2 text-left transition-colors ${s.id === selected ? 'bg-zinc-100 dark:bg-zinc-800' : 'hover:bg-zinc-50 dark:hover:bg-zinc-900'}`}>
            <div className="flex items-start gap-2">
              <span className="mt-1.5 size-2 shrink-0 rounded-full" style={{ background: colors[s.project] }} />
              <div className="min-w-0">
                <div className="line-clamp-2 text-sm leading-snug font-medium">{s.title}</div>
                {s.summary && <div className="mt-0.5 line-clamp-2 text-xs text-zinc-600 dark:text-zinc-400">{s.summary}</div>}
                <div className="mt-0.5 truncate text-xs text-zinc-500">{s.project} · {ago(s.end)} · ${s.cost.toFixed(2)}</div>
                {(live.has(s.id) || st || s.artifacts.length > 0) && (
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    {live.has(s.id) && (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                        <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" />live
                      </span>
                    )}
                    {st && <PRBadge state={st}>PR ×{s.prs.length} · {st}</PRBadge>}
                    {s.artifacts.length > 0 && <PRBadge state="unknown">artifact ×{s.artifacts.length}</PRBadge>}
                  </div>
                )}
                {hits?.get(s.id) && <div className="mt-1 line-clamp-2 text-xs text-zinc-500">…{hits.get(s.id)}…</div>}
              </div>
            </div>
          </button>
        )
      })}
      {!sessions.length && <p className="p-3 text-sm text-zinc-500">No matching sessions.</p>}
    </aside>
  )
}
