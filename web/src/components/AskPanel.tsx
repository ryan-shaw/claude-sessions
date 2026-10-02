import { useEffect, useState } from 'react'
import type { Session } from '../types'
import { linkCitations } from '../lib'
import Md from '../Md'

type Props = { q: string; byId: Map<string, Session>; onSelect: (id: string) => void; onClose: () => void }

export default function AskPanel({ q, byId, onSelect, onClose }: Props) {
  const [res, setRes] = useState<{ answer: string; sources: string[] } | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    setRes(null); setErr('')
    const ctl = new AbortController()
    fetch('/api/ask', { method: 'POST', signal: ctl.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ q }) })
      .then(async r => (r.ok ? r.json() : Promise.reject(new Error((await r.json().catch(() => ({}))).error ?? `HTTP ${r.status}`))))
      .then(setRes)
      .catch(e => { if (e.name !== 'AbortError') setErr(String(e.message ?? e)) })
    return () => ctl.abort()
  }, [q])

  return (
    <div className="absolute inset-x-4 top-14 z-10 max-h-[70%] overflow-y-auto rounded-xl border border-zinc-200 bg-white/95 p-4 shadow-xl backdrop-blur dark:border-zinc-700 dark:bg-zinc-900/95">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="text-sm font-semibold">{q}</div>
        <button onClick={onClose} aria-label="Close" className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800">✕</button>
      </div>
      {!res && !err && <div className="flex items-center gap-2 text-sm text-zinc-500"><span className="size-3 animate-spin rounded-full border-2 border-zinc-300 border-t-transparent" />Reading your sessions…</div>}
      {err && <p className="text-sm text-red-500">{err}</p>}
      {res && (
        <>
          <div className="md text-sm"><Md text={linkCitations(res.answer, byId)} onSession={onSelect} /></div>
          {res.sources.length > 0 && (
            <div className="mt-3 border-t border-zinc-200 pt-2 text-xs text-zinc-500 dark:border-zinc-800">
              Searched: {res.sources.map((id, i) => (
                <button key={id} onClick={() => onSelect(id)} className="hover:underline">{i ? ', ' : ''}{byId.get(id)?.title ?? id}</button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
