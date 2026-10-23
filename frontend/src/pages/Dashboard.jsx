import { motion } from 'framer-motion'
import { AlertCircle, ArrowRight, Bot, FileClock, Inbox, MessageCircle, Mic, Send, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Alert, Badge, Card, CardHeader, Loading, PageHeader, StatusDot } from '../components/ui'
import { MODE_LABEL, PROVIDER_LABEL, timeAgo, useApi } from '../lib/hooks'

function Stat({ label, value, icon: Icon, tone = 'stone', to, delay }) {
  const tones = {
    stone: 'bg-stone-100 text-stone-600',
    green: 'bg-brand-50 text-brand-700',
    amber: 'bg-amber-50 text-amber-700',
    red: 'bg-red-50 text-red-600',
    violet: 'bg-violet-50 text-violet-700',
  }
  const body = (
    <Card className="group h-full p-4 transition-shadow hover:shadow-pop">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-stone-500">{label}</span>
        <span className={`rounded-lg p-1.5 ${tones[tone]}`}><Icon className="size-4" /></span>
      </div>
      <p className="mt-3 font-display text-3xl font-semibold tabular-nums">{value ?? '—'}</p>
    </Card>
  )
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}>
      {to ? <Link to={to}>{body}</Link> : body}
    </motion.div>
  )
}

function DailyChart({ days }) {
  const max = Math.max(1, ...days.map((d) => Math.max(d.received, d.ai_sent)))
  return (
    <div>
      <div className="flex h-36 items-end gap-1.5">
        {days.map((d) => (
          <div key={d.date} className="group relative flex h-full flex-1 items-end gap-0.5" title={`${d.date}: ${d.received} received, ${d.ai_sent} AI replies`}>
            <motion.div initial={{ height: 0 }} animate={{ height: `${(d.received / max) * 100}%` }} className="flex-1 rounded-t bg-stone-300" />
            <motion.div initial={{ height: 0 }} animate={{ height: `${(d.ai_sent / max) * 100}%` }} className="flex-1 rounded-t bg-brand-500" />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-stone-400">
        <span>{days[0]?.date}</span>
        <span className="flex gap-3">
          <span className="flex items-center gap-1"><span className="size-2 rounded-sm bg-stone-300" /> Received</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-sm bg-brand-500" /> AI replies</span>
        </span>
        <span>today</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { data, loading, error } = useApi('/dashboard/', { interval: 10000 })
  const { data: activity } = useApi('/activity/', { interval: 15000 })
  const { data: integrations } = useApi('/integrations/')
  if (loading && !data) return <Loading />
  if (error) return <Alert tone="error" title="Could not load dashboard">{error.message}</Alert>
  const t = data.totals
  const wa = integrations?.whatsapp
  const providerOk = data.provider?.status?.configured

  return (
    <div>
      <PageHeader title="Dashboard" description="Live numbers from your WhatsApp inbox and assistant." />

      {integrations && (!wa?.integration || wa.status !== 'connected' || !providerOk) && (
        <Alert tone="warn" title="Setup incomplete" className="mb-6">
          {!wa?.integration || wa.status !== 'connected' ? (
            <>WhatsApp is not connected yet. <Link className="font-medium underline" to="/integrations">Connect WhatsApp</Link>. </>
          ) : null}
          {!providerOk && (
            <>The selected AI provider is not configured on the server. <Link className="font-medium underline" to="/ai">Check AI settings</Link>.</>
          )}
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Conversations" value={t.conversations} icon={MessageCircle} to="/inbox" delay={0} />
        <Stat label="Messages received" value={t.messages_received} icon={Inbox} delay={0.03} />
        <Stat label="AI replies sent" value={t.ai_replies_sent} icon={Send} tone="green" delay={0.06} />
        <Stat label="Awaiting approval" value={t.drafts_pending} icon={FileClock} tone="amber" to="/inbox?filter=drafts" delay={0.09} />
        <Stat label="Needs attention" value={t.needs_attention} icon={AlertCircle} tone="red" to="/inbox?filter=attention" delay={0.12} />
        <Stat label="Human takeovers" value={t.human_takeover} icon={UserRound} tone="violet" to="/inbox?filter=takeover" delay={0.15} />
        <Stat label="Human replies" value={t.human_replies} icon={MessageCircle} delay={0.18} />
        <Stat label="Failed sends" value={t.failed_messages} icon={AlertCircle} tone={t.failed_messages ? 'red' : 'stone'} delay={0.21} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Last 14 days" description="Inbound messages vs. AI replies (auto + approved)" />
          <div className="p-5"><DailyChart days={data.daily} /></div>
        </Card>
        <Card>
          <CardHeader title="Assistant status" />
          <div className="space-y-4 p-5 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-stone-500">Automation</span>
              <Badge color={!data.automation.enabled ? 'gray' : data.automation.mode === 'automatic' ? 'green' : 'amber'}>
                {data.automation.enabled ? MODE_LABEL[data.automation.mode] : 'Disabled'}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-stone-500">AI provider</span>
              <StatusDot ok={providerOk} label={PROVIDER_LABEL[data.provider.selected]} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-stone-500">Model</span>
              <code className="rounded bg-stone-100 px-1.5 py-0.5 text-xs">{data.provider.status?.model || '—'}</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-stone-500">Fallback</span>
              <span>{data.provider.fallback_enabled ? 'Enabled' : 'Off'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-stone-500">WhatsApp</span>
              <StatusDot ok={wa?.status === 'connected'} warn={wa?.status === 'pending'} label={wa?.integration?.display_phone_number || wa?.status?.replace('_', ' ') || '…'} />
            </div>
            <Link to="/ai" className="flex items-center gap-1 pt-1 text-sm font-medium text-brand-700 hover:underline">
              Change provider <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="AI usage (30 days)" icon={Bot} />
          <div className="divide-y divide-line">
            {data.ai_usage_30d.length === 0 && <p className="p-5 text-sm text-stone-500">No AI requests yet.</p>}
            {data.ai_usage_30d.map((u) => (
              <div key={u.source} className="flex items-center justify-between px-5 py-3 text-sm">
                <div>
                  <p className="font-medium">{PROVIDER_LABEL[u.source] || u.source}</p>
                  <p className="text-xs text-stone-500">{(u.input_tokens || 0) + (u.output_tokens || 0)} tokens</p>
                </div>
                <div className="text-right">
                  <p className="tabular-nums">{u.requests} requests</p>
                  {u.failures > 0 && <p className="text-xs text-red-600">{u.failures} failed</p>}
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
            <span className="flex items-center gap-2 text-stone-500"><Mic className="size-4" /> Voice notes</span>
            <span className="tabular-nums">
              {data.voice_usage_30d.total || 0} generated · {data.voice_usage_30d.characters || 0} chars
              {data.voice_usage_30d.failed ? <span className="text-red-600"> · {data.voice_usage_30d.failed} failed</span> : null}
            </span>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Recent activity" action={<Link to="/activity" className="text-sm font-medium text-brand-700 hover:underline">View all</Link>} />
          <ul className="divide-y divide-line">
            {(activity?.audit || []).slice(0, 8).map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
                <span className="truncate">
                  <span className={a.user.startsWith('system') ? 'font-medium text-brand-700' : 'font-medium'}>{a.user}</span>{' '}
                  <span className="text-stone-600">{a.action.replaceAll('.', ' · ').replaceAll('_', ' ')}</span>
                </span>
                <span className="shrink-0 text-xs text-stone-400">{timeAgo(a.created_at)}</span>
              </li>
            ))}
            {activity && activity.audit.length === 0 && <li className="px-5 py-6 text-sm text-stone-500">No activity yet.</li>}
          </ul>
        </Card>
      </div>
    </div>
  )
}
