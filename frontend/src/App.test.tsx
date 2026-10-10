import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'
import { eventStream, fakeServer, json, sse } from './test/fakeServer'

const user = { id: 1, email: 'me@example.com', full_name: 'Sam', is_admin: false }
const message = (id: number, role: 'user' | 'assistant', content: string) => ({ id, role, content, created_at: '' })

function renderAt(path: string) {
  window.history.pushState({}, '', path)
  return render(<App />)
}

describe('login', () => {
  it('shows the server error for bad credentials', async () => {
    fakeServer({ 'POST /auth/login': () => json({ error: 'Invalid email or password' }, 401) })
    renderAt('/login')

    await userEvent.type(screen.getByLabelText('Email'), 'me@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('Invalid email or password')).toBeInTheDocument()
  })

  it('logs in and lands on the chat page', async () => {
    fakeServer({
      'POST /auth/login': () => json({ user, access_token: 'token' }),
      'GET /chat/sessions': () => json({ sessions: [] }),
    })
    renderAt('/login')

    await userEvent.type(screen.getByLabelText('Email'), 'me@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'password123')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('What would you like to know?')).toBeInTheDocument()
    expect(localStorage.getItem('advisor_token')).toBe('token')
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
  })
})

describe('chat', () => {
  it('starts a conversation and shows the streamed reply', async () => {
    localStorage.setItem('advisor_token', 'token')
    const server = fakeServer({
      'GET /auth/me': () => json({ user }),
      'GET /chat/sessions': () => json({ sessions: [] }),
      'POST /chat/session': () => json({ session: { id: 3, title: null, created_at: '', conversation_ids: [9] }, conversation_id: 9 }, 201),
      'POST /chat/message/stream': (body) =>
        eventStream([
          sse({ type: 'delta', text: 'Spread your ' }),
          sse({ type: 'delta', text: '**risk**.' }),
          sse({
            type: 'done',
            user_message: message(1, 'user', (body as { content: string }).content),
            assistant_message: message(2, 'assistant', 'Spread your **risk**.'),
          }),
        ]),
    })
    renderAt('/chat')

    await userEvent.type(await screen.findByPlaceholderText(/Ask about investing/), 'How do I diversify?{Enter}')

    expect(await screen.findByText('How do I diversify?')).toBeInTheDocument()
    expect(await screen.findByText('risk', { selector: 'strong' })).toBeInTheDocument() // markdown rendered
    expect(window.location.pathname).toBe('/chat/9')
    const streamCall = server.mock.calls.find(([url]) => url.endsWith('/chat/message/stream'))
    expect(JSON.parse(streamCall![1]!.body as string)).toEqual({ conversation_id: 9, content: 'How do I diversify?' })
  })

  it('keeps the typed message and shows the error when sending fails', async () => {
    localStorage.setItem('advisor_token', 'token')
    fakeServer({
      'GET /auth/me': () => json({ user }),
      'GET /chat/sessions': () => json({ sessions: [{ id: 3, title: 'Old chat', created_at: '', conversation_ids: [9] }] }),
      'GET /chat/history/9': () => json({ conversation_id: 9, messages: [] }),
      'POST /chat/message/stream': () => json({ error: 'Too many requests (10 per 1 minute).' }, 429),
    })
    renderAt('/chat/9')

    const input = await screen.findByPlaceholderText(/Ask about investing/)
    await userEvent.type(input, 'Another question{Enter}')

    expect(await screen.findByText('Too many requests (10 per 1 minute).')).toBeInTheDocument()
    expect(input).toHaveValue('Another question')
  })
})

describe('portfolio', () => {
  it('shows live value and gain', async () => {
    localStorage.setItem('advisor_token', 'token')
    fakeServer({
      'GET /auth/me': () => json({ user: { ...user, is_admin: true } }),
      'GET /portfolio/': () =>
        json({ portfolio: { id: 1, name: 'Mine', holdings: [{ id: 1, symbol: 'VTI', quantity: '10.000000', average_cost: '200.0000' }] } }),
      'GET /portfolio/quotes': () => json({ enabled: true, quotes: { VTI: { price: 250, previous_close: 250, currency: 'USD' } } }),
    })
    renderAt('/portfolio')

    expect(await screen.findAllByText('$2,500.00')).not.toHaveLength(0) // market value
    expect(screen.getAllByText('+$500.00')).not.toHaveLength(0) // gain
    expect(screen.getByRole('link', { name: 'Admin' })).toBeInTheDocument()
  })

  it('ignores a slow, outdated price response', async () => {
    localStorage.setItem('advisor_token', 'token')
    const vti = { id: 1, symbol: 'VTI', quantity: '1', average_cost: '1' }
    const quote = (price: number) => ({ price, previous_close: price, currency: 'USD' })
    let quoteCalls = 0
    let releaseFirst!: () => void
    fakeServer({
      'GET /auth/me': () => json({ user }),
      'GET /portfolio/': () => json({ portfolio: { id: 1, name: 'Mine', holdings: [vti] } }),
      'POST /portfolio/holding': () => json({ holding: { id: 2, symbol: 'AAPL', quantity: '1', average_cost: '1' } }, 201),
      'GET /portfolio/quotes': async () => {
        quoteCalls += 1
        if (quoteCalls === 1) {
          // The first request (VTI only) is slow and finishes after the second.
          await new Promise<void>((resolve) => (releaseFirst = resolve))
          return json({ enabled: true, quotes: { VTI: quote(10) } })
        }
        return json({ enabled: true, quotes: { VTI: quote(10), AAPL: quote(123.45) } })
      },
    })
    renderAt('/portfolio')

    await screen.findByRole('cell', { name: 'VTI' })
    await userEvent.type(screen.getByLabelText('Symbol'), 'AAPL')
    await userEvent.type(screen.getByLabelText('Shares'), '1')
    await userEvent.type(screen.getByLabelText('Average cost per share'), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findAllByText('$123.45')).not.toHaveLength(0)

    releaseFirst()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.getAllByText('$123.45')).not.toHaveLength(0)
  })
})
