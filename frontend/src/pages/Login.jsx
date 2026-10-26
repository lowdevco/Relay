import { motion } from 'framer-motion'
import { Bot, ShieldCheck, Workflow } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Input } from '../components/ui'
import { useAuth } from '../context/AuthContext'

const POINTS = [
  { icon: Bot, title: 'Gemini, DeepSeek or Groq', text: 'Pick the model that writes your replies. Switch any time.' },
  { icon: Workflow, title: 'You stay in control', text: 'Drafts, approvals, or automatic replies. Take over any chat in one click.' },
  { icon: ShieldCheck, title: 'Official WhatsApp API', text: "Uses Meta's WhatsApp Business Platform. No phone scraping." },
]

export default function Login({ register = false }) {
  const { login, register: signUp } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', password: '', business_name: '', email: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (register) await signUp(form)
      else await login(form.username, form.password)
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden overflow-hidden bg-ink-950 p-12 lg:flex lg:flex-col lg:justify-between">
        <div className="pointer-events-none absolute -right-32 -top-32 size-[420px] rounded-full bg-brand-500/20 blur-3xl" />
        <div className="relative flex items-center gap-2.5">
          <div className="grid size-9 place-items-center rounded-xl bg-brand-500 text-ink-950">
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h9M10 6l6 6-6 6M20 5v14" /></svg>
          </div>
          <span className="font-display text-lg font-semibold text-white">Relay</span>
        </div>
        <div className="relative max-w-md">
          <h1 className="font-display text-4xl font-semibold leading-tight text-white">
            Customer replies in your voice, <span className="text-brand-400">on WhatsApp.</span>
          </h1>
          <div className="mt-10 space-y-6">
            {POINTS.map((p, i) => (
              <motion.div key={p.title} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 + i * 0.08 }} className="flex gap-4">
                <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/5 text-brand-300 ring-1 ring-white/10"><p.icon className="size-5" /></div>
                <div>
                  <p className="font-medium text-white">{p.title}</p>
                  <p className="text-sm text-white/55">{p.text}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-white/35">Local development build</p>
      </div>

      <div className="flex items-center justify-center p-6">
        <motion.form onSubmit={submit} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm space-y-4">
          <div className="mb-2">
            <h2 className="font-display text-2xl font-semibold">{register ? 'Create your workspace' : 'Welcome back'}</h2>
            <p className="mt-1 text-sm text-stone-500">{register ? 'Set up your business in under a minute.' : 'Sign in to your business inbox.'}</p>
          </div>
          {error && <Alert tone="error">{error}</Alert>}
          {register && <Input label="Business name" value={form.business_name} onChange={set('business_name')} required maxLength={120} />}
          <Input label="Username" value={form.username} onChange={set('username')} required autoComplete="username" />
          {register && <Input label="Email (optional)" type="email" value={form.email} onChange={set('email')} />}
          <Input label="Password" type="password" value={form.password} onChange={set('password')} required
            autoComplete={register ? 'new-password' : 'current-password'} hint={register ? 'At least 8 characters, not too common.' : undefined} />
          <Button type="submit" className="w-full" size="lg" loading={busy}>{register ? 'Create workspace' : 'Sign in'}</Button>
          <p className="text-center text-sm text-stone-500">
            {register ? 'Already have an account? ' : 'New here? '}
            <Link to={register ? '/login' : '/register'} className="font-medium text-brand-700 hover:underline">
              {register ? 'Sign in' : 'Create a workspace'}
            </Link>
          </p>
        </motion.form>
      </div>
    </div>
  )
}
