import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import Markdown from 'react-markdown'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError, api, type ChatSession, type Message } from '../api'

const SUGGESTIONS = [
  'How diversified is my portfolio?',
  'Explain index funds vs. individual stocks',
  'How much should I keep in an emergency fund?',
  'What is dollar-cost averaging?',
]

export default function ChatPage() {
  const { conversationId: idParam } = useParams()
  const conversationId = idParam ? Number(idParam) : null
  const navigate = useNavigate()

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  // The advisor's reply as it streams in; replaced by the saved message once it completes.
  const [streamingText, setStreamingText] = useState('')
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // The conversation we just created while sending; its messages are already in state, so skip reloading it.
  const justCreatedId = useRef<number | null>(null)
  const activeIdRef = useRef(conversationId)
  useEffect(() => {
    activeIdRef.current = conversationId
  }, [conversationId])

  const refreshSessions = useCallback(() => {
    api
      .listSessions()
      .then(({ sessions }) => setSessions(sessions))
      .catch(() => {})
  }, [])

  useEffect(refreshSessions, [refreshSessions])

  useEffect(() => {
    setError(null)
    setSidebarOpen(false)
    if (conversationId === null) {
      setMessages([])
      return
    }
    if (justCreatedId.current === conversationId) {
      justCreatedId.current = null
      return
    }
    let cancelled = false
    setLoadingHistory(true)
    api
      .history(conversationId)
      .then(({ messages }) => !cancelled && setMessages(messages))
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) navigate('/chat', { replace: true })
        else setError(err instanceof ApiError ? err.message : 'Could not load this conversation')
      })
      .finally(() => !cancelled && setLoadingHistory(false))
    return () => {
      cancelled = true
    }
  }, [conversationId, navigate])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending, streamingText])

  async function send(text: string) {
    const content = text.trim()
    if (!content || sending) return
    setError(null)
    setInput('')
    setSending(true)

    const pending: Message = { id: -Date.now(), role: 'user', content, created_at: new Date().toISOString() }
    setMessages((prev) => [...prev, pending])

    try {
      let id = conversationId
      if (id === null) {
        // Only create a session once there's a first message, so empty chats don't pile up.
        id = (await api.createSession()).conversation_id
        justCreatedId.current = id
        // Mark it active now: the router applies navigation as a transition, and a fast reply could
        // otherwise arrive before the effect below updates the ref, and be dropped as "stale".
        activeIdRef.current = id
        navigate(`/chat/${id}`, { replace: true })
      }
      const conversation = id
      const { user_message, assistant_message } = await api.streamMessage(id, content, (text) => {
        if (activeIdRef.current === conversation) setStreamingText((prev) => prev + text)
      })
      refreshSessions()
      if (activeIdRef.current !== id) return
      setMessages((prev) => [...prev.filter((m) => m.id !== pending.id), user_message, assistant_message])
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== pending.id))
      setInput(content)
      setError(err instanceof ApiError ? err.friendlyMessage : 'Something went wrong')
    } finally {
      setSending(false)
      setStreamingText('')
      inputRef.current?.focus()
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    send(input)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      send(input)
    }
  }

  async function deleteSession(session: ChatSession) {
    try {
      await api.deleteSession(session.id)
    } catch {
      return
    }
    setSessions((prev) => prev.filter((s) => s.id !== session.id))
    if (conversationId !== null && session.conversation_ids.includes(conversationId)) navigate('/chat')
  }

  return (
    <div className="relative flex h-full">
      {sidebarOpen && (
        <div className="absolute inset-0 z-10 bg-slate-900/20 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      {/* Conversation list: fixed column on desktop, slide-over on mobile */}
      <aside
        className={`${
          sidebarOpen ? 'flex' : 'hidden'
        } absolute inset-y-0 left-0 z-20 w-72 flex-col border-r border-slate-200 bg-white md:static md:flex md:w-64`}
      >
        <div className="p-3">
          <Link
            to="/chat"
            onClick={() => setSidebarOpen(false)}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-50"
          >
            <span className="text-lg leading-none">+</span> New chat
          </Link>
        </div>
        <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {sessions.length === 0 && <li className="px-3 py-2 text-sm text-slate-400">No conversations yet</li>}
          {sessions.map((session) => {
            const firstId = session.conversation_ids[0]
            const active = firstId === conversationId
            return (
              <li key={session.id} className="group relative">
                <Link
                  to={`/chat/${firstId}`}
                  className={`block truncate rounded-md py-2 pl-3 pr-8 text-sm ${
                    active ? 'bg-emerald-50 font-medium text-emerald-800' : 'text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  {session.title || 'Untitled chat'}
                </Link>
                <button
                  onClick={() => deleteSession(session)}
                  title="Delete conversation"
                  aria-label="Delete conversation"
                  className="absolute right-1 top-1/2 hidden -translate-y-1/2 rounded px-2 py-1 text-slate-400 hover:bg-slate-200 hover:text-red-600 group-hover:block"
                >
                  ×
                </button>
              </li>
            )
          })}
        </ul>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-slate-200 bg-white px-4 py-2 md:hidden">
          <button onClick={() => setSidebarOpen(true)} className="text-sm font-medium text-slate-600">
            ☰ Conversations
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-4 py-6">
            {loadingHistory ? (
              <p className="text-center text-sm text-slate-400">Loading conversation…</p>
            ) : messages.length === 0 && !sending ? (
              <EmptyState onPick={send} />
            ) : (
              <div className="space-y-6">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
                {streamingText && (
                  <MessageBubble message={{ id: 0, role: 'assistant', content: streamingText, created_at: '' }} />
                )}
                {sending && !streamingText && (
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <span className="flex gap-1">
                      <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:-0.3s]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:-0.15s]" />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300" />
                    </span>
                    Advisor is thinking…
                  </div>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-slate-200 bg-white px-4 pb-4 pt-3">
          <div className="mx-auto max-w-3xl">
            {error && <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
            <form onSubmit={handleSubmit} className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                maxLength={4000}
                autoFocus
                placeholder="Ask about investing, your portfolio, saving…"
                className="max-h-40 min-h-[42px] flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none [field-sizing:content] focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20"
              />
              <button
                type="submit"
                disabled={sending || !input.trim()}
                className="h-[42px] rounded-xl bg-emerald-600 px-4 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                Send
              </button>
            </form>
            <p className="mt-2 text-center text-xs text-slate-400">
              For education only, not financial advice. Consult a licensed professional before making investment
              decisions.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="pt-10 text-center sm:pt-20">
      <h2 className="text-2xl font-semibold">What would you like to know?</h2>
      <p className="mt-2 text-sm text-slate-500">
        Ask about investing basics, or{' '}
        <Link to="/portfolio" className="text-emerald-700 hover:underline">
          add your holdings
        </Link>{' '}
        for answers tailored to your portfolio.
      </p>
      <div className="mx-auto mt-8 grid max-w-xl gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            onClick={() => onPick(text)}
            className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 shadow-sm hover:border-emerald-300 hover:bg-emerald-50/50"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-emerald-600 px-4 py-2.5 text-sm text-white">
          {message.content}
        </div>
      </div>
    )
  }
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-xs font-semibold text-emerald-700">
        A
      </span>
      <div className="prose prose-sm prose-slate min-w-0 max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5">
        <Markdown>{message.content}</Markdown>
      </div>
    </div>
  )
}
