import Markdown from 'react-markdown'

export const MAX_CHARS = 20_000
export const clip = (t: string): [string, boolean] => (t.length > MAX_CHARS ? [t.slice(0, MAX_CHARS), true] : [t, false])

// no <img>: a prompt-injected transcript could exfiltrate via image URLs the moment the drawer opens
export default function Md({ text, onSession }: { text: string; onSession?: (id: string) => void }) {
  return (
    <Markdown disallowedElements={['img']}
      components={{
        a: ({ node: _, href, children, ...p }) =>
          href?.startsWith('#s:') && onSession
            ? <button type="button" onClick={() => onSession(href.slice(3))} className="font-medium text-blue-600 underline dark:text-blue-400">{children}</button>
            : <a {...p} href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
      }}>
      {text}
    </Markdown>
  )
}
