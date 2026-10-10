import { describe, expect, it, vi } from 'vitest'
import { ApiError, api, parseSSE, setToken, setUnauthorizedHandler } from './api'
import { eventStream, fakeServer, json, sse } from './test/fakeServer'

describe('parseSSE', () => {
  it('returns complete events and keeps the unfinished remainder', () => {
    const { events, rest } = parseSSE('data: {"type":"delta","text":"a"}\n\ndata: {"type":"del')
    expect(events).toEqual([{ type: 'delta', text: 'a' }])
    expect(rest).toBe('data: {"type":"del')
  })

  it('handles CRLF line endings', () => {
    const { events, rest } = parseSSE('data: {"type":"delta","text":"x"}\r\n\r\n')
    expect(events).toEqual([{ type: 'delta', text: 'x' }])
    expect(rest).toBe('')
  })
})

const message = (id: number, role: 'user' | 'assistant', content: string) => ({ id, role, content, created_at: '' })

describe('streamMessage', () => {
  it('reports deltas, including events split across chunks, and resolves with the saved messages', async () => {
    const done = sse({ type: 'done', user_message: message(1, 'user', 'q'), assistant_message: message(2, 'assistant', 'Hello there') })
    fakeServer({
      'POST /chat/message/stream': () =>
        eventStream([sse({ type: 'delta', text: 'Hello' }).slice(0, 12), sse({ type: 'delta', text: 'Hello' }).slice(12), sse({ type: 'delta', text: ' there' }) + done]),
    })
    const deltas: string[] = []

    const result = await api.streamMessage(7, 'q', (text) => deltas.push(text))

    expect(deltas).toEqual(['Hello', ' there'])
    expect(result.assistant_message.content).toBe('Hello there')
  })

  it('rejects with the server message on an error event', async () => {
    fakeServer({
      'POST /chat/message/stream': () => eventStream([sse({ type: 'delta', text: 'Par' }), sse({ type: 'error', error: 'The advisor service is unavailable' })]),
    })
    await expect(api.streamMessage(7, 'q', () => {})).rejects.toThrow('The advisor service is unavailable')
  })

  it('rejects with the JSON error before streaming starts (e.g. rate limited)', async () => {
    fakeServer({ 'POST /chat/message/stream': () => json({ error: 'Too many requests' }, 429) })
    const error = await api.streamMessage(7, 'q', () => {}).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(429)
  })
})

describe('request handling', () => {
  it('calls the unauthorized handler on 401 when logged in', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    setToken('expired')
    fakeServer({ 'GET /auth/me': () => json({ error: 'Token has expired' }, 401) })

    await expect(api.me()).rejects.toThrow('Token has expired')
    expect(handler).toHaveBeenCalledOnce()
  })

  it('exposes the first validation detail as a friendly message', async () => {
    fakeServer({
      'POST /auth/register': () => json({ error: 'Invalid input', details: { password: ['Shorter than minimum length 8.'] } }, 400),
    })
    const error = await api.register('a@example.com', 'short').catch((e) => e)
    expect(error.friendlyMessage).toBe('password: Shorter than minimum length 8.')
  })
})
