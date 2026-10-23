import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  BookOpen,
  Bot,
  LayoutDashboard,
  LogOut,
  Menu,
  MessagesSquare,
  Mic,
  Plug,
  Sparkles,
  Workflow,
  X,
} from 'lucide-react'
import { Suspense, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useApi } from '../lib/hooks'
import { Loading, cx } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/inbox', label: 'Inbox', icon: MessagesSquare, badge: 'inbox' },
  { section: 'Assistant' },
  { to: '/ai', label: 'AI provider', icon: Bot },
  { to: '/personalization', label: 'Personalization', icon: Sparkles },
  { to: '/knowledge', label: 'Knowledge base', icon: BookOpen },
  { to: '/automation', label: 'Automation', icon: Workflow },
  { to: '/voice', label: 'Voice notes', icon: Mic },
  { section: 'Workspace' },
  { to: '/integrations', label: 'Integrations', icon: Plug },
  { to: '/activity', label: 'Activity log', icon: Activity },
]

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <div className="grid size-8 place-items-center rounded-xl bg-brand-500 text-ink-950 shadow-[0_0_0_4px_rgba(16,185,129,0.15)]">
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 12h9M10 6l6 6-6 6M20 5v14" />
        </svg>
      </div>
      <div>
        <p className="font-display text-[15px] font-semibold leading-none text-white">Relay</p>
        <p className="mt-0.5 text-[11px] text-white/45">WhatsApp AI assistant</p>
      </div>
    </div>
  )
}

function SidebarContent({ onNavigate }) {
  const { user, workspace, workspaces, selectWorkspace, logout } = useAuth()
  const { data: stats } = useApi('/dashboard/', { interval: 15000 })
  const attention = (stats?.totals?.needs_attention ?? 0) + (stats?.totals?.drafts_pending ?? 0)
  return (
    <div className="flex h-full flex-col bg-ink-950 px-3 py-4">
      <Logo />
      {workspaces.length > 1 ? (
        <select
          className="mx-1 mt-5 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-sm text-white"
          value={workspace?.id}
          onChange={(e) => {
            selectWorkspace(Number(e.target.value))
            window.location.reload()
          }}
        >
          {workspaces.map((w) => (
            <option key={w.id} value={w.id} className="text-ink-900">{w.name}</option>
          ))}
        </select>
      ) : (
        <div className="mx-1 mt-5 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
          <p className="text-[11px] uppercase tracking-wider text-white/40">Workspace</p>
          <p className="truncate text-sm font-medium text-white">{workspace?.name}</p>
        </div>
      )}
      <nav className="scroll-thin mt-4 flex-1 space-y-0.5 overflow-y-auto">
        {NAV.map((item, i) =>
          item.section ? (
            <p key={i} className="px-3 pb-1 pt-5 text-[11px] font-medium uppercase tracking-wider text-white/35">{item.section}</p>
          ) : (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cx(
                  'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                  isActive ? 'bg-white/10 text-white' : 'text-white/60 hover:bg-white/5 hover:text-white',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <motion.span layoutId="nav-active" className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-brand-400" />}
                  <item.icon className="size-4" />
                  <span className="flex-1">{item.label}</span>
                  {item.badge === 'inbox' && attention > 0 && (
                    <span className="rounded-full bg-brand-500 px-1.5 text-[11px] font-semibold text-ink-950">{attention}</span>
                  )}
                </>
              )}
            </NavLink>
          ),
        )}
      </nav>
      <div className="mt-3 flex items-center gap-3 rounded-lg border border-white/10 px-3 py-2.5">
        <div className="grid size-8 place-items-center rounded-full bg-brand-500/20 text-sm font-semibold text-brand-200">
          {user?.username?.[0]?.toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-white">{user?.username}</p>
          <p className="text-[11px] capitalize text-white/40">{workspace?.role}</p>
        </div>
        <button onClick={logout} className="rounded-md p-1.5 text-white/50 hover:bg-white/10 hover:text-white" aria-label="Sign out" title="Sign out">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  )
}

export default function Layout() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const fullBleed = location.pathname.startsWith('/inbox')
  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 lg:block">
        <SidebarContent />
      </aside>
      <AnimatePresence>
        {open && (
          <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-ink-950/50" onClick={() => setOpen(false)} />
            <motion.aside initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }} transition={{ type: 'spring', stiffness: 400, damping: 40 }}
              className="absolute inset-y-0 left-0 w-64">
              <SidebarContent onNavigate={() => setOpen(false)} />
              <button onClick={() => setOpen(false)} className="absolute right-3 top-4 rounded-md p-1 text-white/60" aria-label="Close menu">
                <X className="size-5" />
              </button>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-line bg-white px-4 lg:hidden">
          <button onClick={() => setOpen(true)} className="rounded-md p-1.5 hover:bg-stone-100" aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <span className="font-display font-semibold">Relay</span>
        </header>
        <main className={cx('min-h-0 flex-1', fullBleed ? 'overflow-hidden' : 'scroll-thin overflow-y-auto')}>
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.18 }}
            className={fullBleed ? 'h-full' : 'mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8'}
          >
            <Suspense fallback={<Loading />}>
              <Outlet />
            </Suspense>
          </motion.div>
        </main>
      </div>
    </div>
  )
}
