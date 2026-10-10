// Thin client for the Flask API. In dev, Vite proxies /api to the backend (see vite.config.ts).
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'
const TOKEN_KEY = 'advisor_token'

export interface User {
  id: number
  email: string
  full_name: string | null
  is_admin: boolean
}

export interface ChatSession {
  id: number
  title: string | null
  created_at: string
  conversation_ids: number[]
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface Holding {
  id: number
  symbol: string
  quantity: string
  average_cost: string
}

export interface Quote {
  price: number
  previous_close: number | null
  currency: string
}

export interface AdminUser extends User {
  account_locked: boolean
  created_at: string
}

export interface AuditLog {
  id: number
  user_id: number | null
  action: string
  details: string | null
  ip_address: string | null
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
}

export class ApiError extends Error {
  status: number
  details?: Record<string, string[]>

  constructor(status: number, message: string, details?: Record<string, string[]>) {
    super(message)
    this.status = status
    this.details = details
  }

  /** The first field-level validation message, if any, else the general message. */
  get friendlyMessage(): string {
    const first = this.details && Object.entries(this.details)[0]
    return first ? `${first[0].replace('_', ' ')}: ${first[1][0]}` : this.message
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

// Set by AuthProvider so an expired/invalid token anywhere logs the user out.
let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

/** Make a request and throw ApiError for network failures and non-2xx responses. */
async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const token = getToken()
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: {
        ...(body !== undefined && { 'Content-Type': 'application/json' }),
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    if (response.status === 401 && token) onUnauthorized()
    throw new ApiError(response.status, data.error ?? `Request failed (${response.status})`, data.details)
  }
  return response
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await send(method, path, body)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export type StreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'done'; user_message: Message; assistant_message: Message }
  | { type: 'error'; error: string }

/**
 * Split buffered Server-Sent Events text into complete events and the unfinished remainder.
 * Events are separated by a blank line; each carries one `data: <json>` line.
 */
export function parseSSE(buffer: string): { events: StreamEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = blocks.pop() ?? ''
  const events = blocks
    .map((block) => block.split('\n').find((line) => line.startsWith('data: ')))
    .filter((line): line is string => line !== undefined)
    .map((line) => JSON.parse(line.slice('data: '.length)) as StreamEvent)
  return { events, rest }
}

/** Send a chat message and receive the reply incrementally; resolves once both messages are saved. */
async function streamMessage(
  conversationId: number,
  content: string,
  onDelta: (text: string) => void,
): Promise<{ user_message: Message; assistant_message: Message }> {
  const response = await send('POST', '/chat/message/stream', { conversation_id: conversationId, content })
  if (!response.body) throw new ApiError(0, 'Streaming is not supported by this browser')

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    const parsed = parseSSE(buffer + value)
    buffer = parsed.rest
    for (const event of parsed.events) {
      if (event.type === 'delta') onDelta(event.text)
      else if (event.type === 'done') return event
      else throw new ApiError(503, event.error)
    }
  }
  throw new ApiError(0, 'The connection closed before the reply finished')
}

interface AuthResponse {
  user: User
  access_token: string
}

export const api = {
  register: (email: string, password: string, full_name?: string) =>
    request<AuthResponse>('POST', '/auth/register', { email, password, ...(full_name && { full_name }) }),
  login: (email: string, password: string) => request<AuthResponse>('POST', '/auth/login', { email, password }),
  me: () => request<{ user: User }>('GET', '/auth/me'),

  listSessions: () => request<{ sessions: ChatSession[] }>('GET', '/chat/sessions'),
  createSession: () => request<{ session: ChatSession; conversation_id: number }>('POST', '/chat/session', {}),
  deleteSession: (sessionId: number) => request<void>('DELETE', `/chat/session/${sessionId}`),
  history: (conversationId: number) =>
    request<{ conversation_id: number; messages: Message[] }>('GET', `/chat/history/${conversationId}`),
  streamMessage,

  portfolio: () => request<{ portfolio: { id: number; name: string; holdings: Holding[] } }>('GET', '/portfolio/'),
  addHolding: (symbol: string, quantity: string, average_cost: string) =>
    request<{ holding: Holding }>('POST', '/portfolio/holding', { symbol, quantity, average_cost }),
  updateHolding: (id: number, quantity: string, average_cost: string) =>
    request<{ holding: Holding }>('PUT', `/portfolio/holding/${id}`, { quantity, average_cost }),
  deleteHolding: (id: number) => request<void>('DELETE', `/portfolio/holding/${id}`),
  quotes: () => request<{ enabled: boolean; quotes: Record<string, Quote | null> }>('GET', '/portfolio/quotes'),

  adminUsers: async (page = 1): Promise<Page<AdminUser>> => {
    const data = await request<{ users: AdminUser[]; total: number; page: number }>('GET', `/admin/users?page=${page}`)
    return { items: data.users, total: data.total, page: data.page }
  },
  unlockUser: (id: number) => request<{ user: AdminUser }>('POST', `/admin/users/${id}/unlock`),
  auditLogs: async (page = 1, action = ''): Promise<Page<AuditLog>> => {
    const query = new URLSearchParams({ page: String(page), ...(action && { action }) })
    const data = await request<{ audit_logs: AuditLog[]; total: number; page: number }>(
      'GET',
      `/admin/audit-logs?${query}`,
    )
    return { items: data.audit_logs, total: data.total, page: data.page }
  },
}
