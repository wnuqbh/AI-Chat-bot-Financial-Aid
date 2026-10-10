import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ApiError, api, type AdminUser, type AuditLog, type Page } from '../api'

const PER_PAGE = 50 // matches the backend's default page size
const dateTime = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' })

const ACTIONS = [
  'register',
  'login',
  'login_failed',
  'login_blocked_locked',
  'account_unlocked',
  'holding_added',
  'holding_updated',
  'holding_deleted',
]

export default function AdminPage() {
  const [tab, setTab] = useState<'users' | 'logs'>('users')
  const tabClass = (active: boolean) =>
    `rounded-md px-3 py-1.5 text-sm font-medium ${active ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="text-2xl font-semibold">Admin</h1>
        <div className="mt-4 inline-flex gap-1 rounded-lg bg-slate-100 p-1">
          <button className={tabClass(tab === 'users')} onClick={() => setTab('users')}>
            Users
          </button>
          <button className={tabClass(tab === 'logs')} onClick={() => setTab('logs')}>
            Audit log
          </button>
        </div>
        <div className="mt-6">{tab === 'users' ? <UsersTab /> : <AuditLogTab />}</div>
      </div>
    </div>
  )
}

function usePaged<T>(load: (page: number) => Promise<Page<T>>) {
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<T> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    load(page)
      .then((result) => {
        setData(result)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load data'))
  }, [load, page])

  useEffect(refresh, [refresh])
  return { page, setPage, data, setData, error, refresh }
}

function UsersTab() {
  const { page, setPage, data, setData, error } = usePaged(api.adminUsers)
  const [actionError, setActionError] = useState<string | null>(null)

  async function unlock(user: AdminUser) {
    try {
      const { user: updated } = await api.unlockUser(user.id)
      setData((prev) => prev && { ...prev, items: prev.items.map((u) => (u.id === updated.id ? updated : u)) })
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Could not unlock user')
    }
  }

  return (
    <Panel error={error ?? actionError} loading={!data}>
      {data && (
        <>
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Joined</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((user) => (
                <tr key={user.id}>
                  <td className="px-4 py-3">
                    {user.email}
                    {user.is_admin && (
                      <span className="ml-2 rounded bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
                        admin
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{user.full_name || '–'}</td>
                  <td className="px-4 py-3 text-slate-600">{dateTime.format(new Date(user.created_at))}</td>
                  <td className="px-4 py-3">
                    {user.account_locked ? (
                      <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700">Locked</span>
                    ) : (
                      <span className="text-xs text-slate-500">Active</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {user.account_locked && (
                      <button
                        onClick={() => unlock(user)}
                        className="rounded-md bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-700"
                      >
                        Unlock
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} total={data.total} onPage={setPage} />
        </>
      )}
    </Panel>
  )
}

function AuditLogTab() {
  const [action, setAction] = useState('')
  const load = useCallback((page: number) => api.auditLogs(page, action), [action])
  const { page, setPage, data, error } = usePaged<AuditLog>(load)

  return (
    <>
      <label className="mb-3 flex items-center gap-2 text-sm text-slate-600">
        Action
        <select
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setPage(1)
          }}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
        >
          <option value="">All</option>
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
      </label>
      <Panel error={error} loading={!data}>
        {data &&
          (data.items.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-500">No entries</p>
          ) : (
            <>
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Time</th>
                    <th className="px-4 py-3 font-medium">Action</th>
                    <th className="px-4 py-3 font-medium">User ID</th>
                    <th className="px-4 py-3 font-medium">Details</th>
                    <th className="px-4 py-3 font-medium">IP address</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((log) => (
                    <tr key={log.id}>
                      <td className="whitespace-nowrap px-4 py-2.5 text-slate-600">
                        {dateTime.format(new Date(log.created_at))}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                            log.action.includes('fail') || log.action.includes('locked')
                              ? 'bg-amber-50 text-amber-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {log.action.replaceAll('_', ' ')}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">{log.user_id ?? '–'}</td>
                      <td className="px-4 py-2.5 text-slate-600">{log.details ?? ''}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{log.ip_address ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pager page={page} total={data.total} onPage={setPage} />
            </>
          ))}
      </Panel>
    </>
  )
}

function Panel({ error, loading, children }: { error: string | null; loading: boolean; children: ReactNode }) {
  return (
    <>
      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
        {loading && !error ? <p className="p-6 text-center text-sm text-slate-400">Loading…</p> : children}
      </div>
    </>
  )
}

function Pager({ page, total, onPage }: { page: number; total: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / PER_PAGE))
  if (pages === 1) return <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">{total} total</p>
  const button = 'rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40'
  return (
    <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
      <span>
        {total} total · page {page} of {pages}
      </span>
      <span>
        <button className={button} disabled={page <= 1} onClick={() => onPage(page - 1)}>
          ← Previous
        </button>
        <button className={button} disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next →
        </button>
      </span>
    </div>
  )
}
