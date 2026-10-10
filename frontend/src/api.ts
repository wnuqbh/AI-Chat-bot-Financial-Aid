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

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
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

  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && token) onUnauthorized()
    throw new ApiError(response.status, data.error ?? `Request failed (${response.status})`, data.details)
  }
  return data as T
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
  sendMessage: (conversationId: number, content: string) =>
    request<{ user_message: Message; assistant_message: Message }>('POST', '/chat/message', {
      conversation_id: conversationId,
      content,
    }),

  portfolio: () => request<{ portfolio: { id: number; name: string; holdings: Holding[] } }>('GET', '/portfolio/'),
  addHolding: (symbol: string, quantity: string, average_cost: string) =>
    request<{ holding: Holding }>('POST', '/portfolio/holding', { symbol, quantity, average_cost }),
  updateHolding: (id: number, quantity: string, average_cost: string) =>
    request<{ holding: Holding }>('PUT', `/portfolio/holding/${id}`, { quantity, average_cost }),
  deleteHolding: (id: number) => request<void>('DELETE', `/portfolio/holding/${id}`),
}
