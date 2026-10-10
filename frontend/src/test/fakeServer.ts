import { vi } from 'vitest'

type Handler = (body: unknown) => Response | Promise<Response>

export const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

/** A text/event-stream response whose body arrives in the given chunks (which may split events). */
export const eventStream = (chunks: string[]) =>
  new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk))
        controller.close()
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )

export const sse = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`

/**
 * Replace global fetch with a router keyed by "METHOD /path" (path without the /api prefix or query).
 * Unmatched requests fail the test loudly. Returns the mock for call assertions.
 */
export function fakeServer(routes: Record<string, Handler>) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace(/^\/api/, '').split('?')[0]
    const key = `${init?.method ?? 'GET'} ${path}`
    const handler = routes[key]
    if (!handler) throw new Error(`Unexpected request: ${key}`)
    return handler(init?.body ? JSON.parse(init.body as string) : undefined)
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
