import { useEffect, useState } from 'react'
import type { Message, PRInfo, Session, SessionDetail } from '../types'
import { fmtDate, resumeCommand } from '../lib'
import Md, { clip } from '../Md'
import { PRBadge } from './PRBadge'

const PAGE = 200
type Props = {
  id: string; mtime: number; colors: Record<string, string>; byId: Map<string, Session>; prs: Record<string, PRInfo>
  onClose: () => void; onSelect: (id: string) => void; onFile: (key: string) => void
}

export default function Drawer({ id, mtime, colors, byId, prs, onClose, onSelect, onFile }: Props) {
  const [d, setD] = useState<SessionDetail | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const [opened, setOpened] = useState('')

  useEffect(() => { setD(null); setErr(''); setCopied(false); setOpened('') }, [id])
  // refetch when the session file changes, so a live session's transcript keeps up
  useEffect(() => {
    const ctl = new AbortController()
    fetch('/api/session/' + encodeURIComponent(id), { signal: ctl.signal })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status === 404 ? 'Session not found' : `HTTP ${r.status}`))))
      .then(setD)
      .catch(e => { if (e.name !== 'AbortError') setErr(String(e.message ?? e)) })
    return () => ctl.abort()
  }, [id, mtime])

  const openInIterm = () => {
    setOpened('Opening…')
    fetch('/api/resume/' + encodeURIComponent(id), { method: 'POST' })
      .then(async r => setOpened(r.ok ? 'Opened ✓' : `Failed: ${(await r.json().catch(() => ({}))).error ?? r.status}`))
      .catch(e => setOpened(`Failed: ${e.message ?? e}`))
  }

  const s = d?.summary
  const cmd = s ? resumeCommand(s) : ''
  return (
    <section className="flex w-[480px] shrink-0 flex-col border-l border-zinc-200 dark:border-zinc-800">
      <div className="flex items-start justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h2 className="text-base leading-snug font-semibold">{s?.title ?? (err || 'Loading…')}</h2>
        <button onClick={onClose} aria-label="Close" className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800">✕</button>
      </div>
      {s && d && (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {s.summary && <p className="mb-2 rounded-lg bg-blue-500/10 px-3 py-2 text-sm text-zinc-700 dark:text-zinc-300">{s.summary}</p>}
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="size-2 rounded-full" style={{ background: colors[s.project] }} />{s.project}
          </div>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs [&>dt]:text-zinc-500">
            <dt>Directory</dt><dd className="font-mono break-all">{s.cwd}</dd>
            {s.branches.length > 0 && <><dt>Branches</dt><dd className="font-mono break-all">{s.branches.join(', ')}</dd></>}
            <dt>When</dt><dd>{fmtDate(s.start)} → {fmtDate(s.end)}</dd>
            <dt>Usage</dt>
            <dd>${s.cost.toFixed(2)} · <span className="text-emerald-600">+{s.added}</span> <span className="text-red-500">−{s.removed}</span> · {s.messages} msgs · {s.subagents} subagents</dd>
          </dl>
          {s.prs.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {s.prs.filter(p => p.url.startsWith('https://')).map(p => {
                const info = prs[p.url]
                return (
                  <PRBadge key={p.url} state={info?.state ?? 'unknown'} href={p.url} title={info?.title ?? p.url}>
                    {p.repo && p.number ? `${p.repo}#${p.number}` : p.url} · {info?.state ?? '…'}
                  </PRBadge>
                )
              })}
            </div>
          )}
          {s.artifacts.length > 0 && (
            <ul className="mt-2 space-y-1">
              {s.artifacts.map(a => (
                <li key={a.url} className="text-xs">
                  <a href={a.url} target="_blank" rel="noopener noreferrer" title={a.url} className="font-medium text-blue-600 hover:underline dark:text-blue-400">
                    ↗ {a.title || a.url.split('/').pop()?.slice(0, 8)}
                  </a>
                  {a.description && <span className="text-zinc-500"> · {a.description}</span>}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-zinc-100 p-2 dark:bg-zinc-900">
            <code className="min-w-0 flex-1 truncate text-[11px]" title={cmd}>{cmd}</code>
            <button onClick={() => navigator.clipboard.writeText(cmd).then(() => setCopied(true))}
              className="shrink-0 rounded-md border border-zinc-300 px-2.5 py-1 text-xs font-medium dark:border-zinc-700">{copied ? 'Copied ✓' : 'Copy'}</button>
            <button onClick={openInIterm}
              className="shrink-0 rounded-md bg-zinc-900 px-2.5 py-1 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-900">Open in iTerm</button>
          </div>
          {opened && <div className="mt-1 text-right text-[11px] text-zinc-500">{opened}</div>}
          {s.related.length > 0 && (
            <div className="mt-3">
              <h3 className="mb-1 text-xs font-semibold tracking-wide text-zinc-500 uppercase">Related sessions</h3>
              {s.related.map(r => {
                const o = byId.get(r.id)
                return o && (
                  <button key={r.id} onClick={() => onSelect(r.id)}
                    className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-zinc-100 dark:hover:bg-zinc-800">
                    <span className="size-1.5 shrink-0 rounded-full" style={{ background: colors[o.project] }} />
                    <span className="truncate">{o.title}</span>
                    <span className="ml-auto shrink-0 text-zinc-500">{Math.round(r.score * 100)}%</span>
                  </button>
                )
              })}
            </div>
          )}
          {s.files.length > 0 && (
            <details className="mt-3 text-xs">
              <summary className="cursor-pointer text-zinc-500">{s.files.length} files edited</summary>
              <ul className="mt-1 space-y-0.5 font-mono">
                {s.files.map((f, i) => (
                  <li key={f}>
                    <button onClick={() => onFile(s.file_keys[i] ?? f)} title={`${f}\nShow every session that edited this file`}
                      className="text-left break-all hover:underline">{s.file_keys[i] ?? f}</button>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {d.subagents.map((a, i) => <Subagent key={i} name={a.name} messages={a.messages} />)}
          <h3 className="mt-4 mb-2 text-xs font-semibold tracking-wide text-zinc-500 uppercase">Transcript</h3>
          <Transcript messages={d.messages} />
        </div>
      )}
    </section>
  )
}

function Transcript({ messages }: { messages: Message[] }) {
  const [all, setAll] = useState(false)
  // ponytail: render cap instead of virtualisation; virtualise if 'Show all' on huge sessions gets sluggish
  const shown = all ? messages : messages.slice(0, PAGE)
  return (
    <div className="space-y-3">
      {shown.map((m, i) => (
        <div key={i} className={m.role === 'user' ? 'ml-8 rounded-xl rounded-tr-sm bg-orange-500/10 px-3 py-2 text-sm' : 'text-sm'}>
          <div className="mb-0.5 text-[10px] text-zinc-500">{m.role === 'user' ? 'You' : 'Claude'} · {fmtDate(m.ts)}</div>
          {m.text && <Text text={m.text} markdown={m.role === 'assistant'} />}
          {m.tools.map((t, j) => (
            <details key={j} className="mt-1 text-xs">
              <summary className="cursor-pointer text-zinc-500">⚙ {t.name}</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-zinc-100 p-2 text-[11px] break-all whitespace-pre-wrap dark:bg-zinc-900">{t.input_preview}</pre>
            </details>
          ))}
        </div>
      ))}
      {!all && messages.length > PAGE && (
        <button onClick={() => setAll(true)} className="w-full rounded-lg border border-zinc-200 py-1.5 text-xs text-zinc-500 dark:border-zinc-800">
          Show all {messages.length} messages
        </button>
      )}
    </div>
  )
}

// closed <details> still mounts children, so only render the transcript once opened
function Subagent({ name, messages }: { name: string; messages: Message[] }) {
  const [open, setOpen] = useState(false)
  return (
    <details onToggle={e => setOpen(e.currentTarget.open)} className="mt-2 rounded-lg border border-zinc-200 p-2 text-xs dark:border-zinc-800">
      <summary className="cursor-pointer font-medium">Subagent: {name} <span className="text-zinc-500">({messages.length})</span></summary>
      {open && <Transcript messages={messages} />}
    </details>
  )
}

function Text({ text, markdown }: { text: string; markdown: boolean }) {
  const [full, setFull] = useState(false)
  const [clipped, cut] = clip(text)
  const t = full ? text : clipped
  return (
    <>
      {markdown ? <div className="md break-words"><Md text={t} /></div> : <div className="break-words whitespace-pre-wrap">{t}</div>}
      {cut && !full && <button onClick={() => setFull(true)} className="mt-1 text-xs text-zinc-500 underline">Show full message ({Math.round(text.length / 1000)}k chars)</button>}
    </>
  )
}
