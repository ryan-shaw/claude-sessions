export type PR = { repo: string | null; number: number | null; url: string }
export type Session = {
  id: string; cwd: string; project: string; branches: string[]; title: string
  start: string | null; end: string | null; messages: number
  cost: number; added: number; removed: number
  prs: PR[]; artifacts: string[]; files: string[]; subagents: number
  mtime: number; file_keys: string[]; related: { id: string; score: number }[]
  summary?: string | null
}
export type Tool = { name: string; input_preview: string }
export type Message = { role: 'user' | 'assistant'; ts: string | null; text: string; tools: Tool[] }
export type SessionDetail = { summary: Session; messages: Message[]; subagents: { name: string; messages: Message[] }[] }
export type EdgeType = 'folder' | 'files' | 'pr' | 'related'
export type Edge = { source: string; target: string; type: EdgeType; key?: string }
export type PRState = 'open' | 'merged' | 'closed' | 'unknown'
export type PRInfo = { state: PRState; title: string | null }
export type Folder = { id: string; path: string; label: string; count: number; group: string | null }
