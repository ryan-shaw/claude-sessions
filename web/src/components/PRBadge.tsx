import type { ReactNode } from 'react'
import type { PRState } from '../types'

const COLOR: Record<PRState, string> = {
  open: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  merged: 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  closed: 'bg-red-500/15 text-red-700 dark:text-red-400',
  unknown: 'bg-zinc-500/15 text-zinc-600 dark:text-zinc-400',
}

export function PRBadge({ state, children, href, title }: { state: PRState; children: ReactNode; href?: string; title?: string }) {
  const cls = `inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${COLOR[state]}`
  return href
    ? <a href={href} target="_blank" rel="noopener noreferrer" title={title} className={`${cls} hover:underline`}>{children}</a>
    : <span title={title} className={cls}>{children}</span>
}
