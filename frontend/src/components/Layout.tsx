import { NavLink, Outlet } from 'react-router'
import { useAuth } from '../auth'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? 'bg-emerald-50 text-emerald-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
  }`

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="mr-4 flex items-center gap-2 font-semibold">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-600 text-sm text-white">A</span>
          <span className="hidden sm:inline">Advisor</span>
        </div>
        <nav className="flex gap-1">
          <NavLink to="/chat" className={navLinkClass}>
            Chat
          </NavLink>
          <NavLink to="/portfolio" className={navLinkClass}>
            Portfolio
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden truncate text-sm text-slate-500 md:inline">{user?.full_name || user?.email}</span>
          <button
            onClick={logout}
            className="rounded-md px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            Log out
          </button>
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  )
}
