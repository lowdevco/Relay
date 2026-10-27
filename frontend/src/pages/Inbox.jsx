import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  Check,
  CheckCheck,
  CheckCircle2,
  Clock,
  FlaskConical,
  Hand,
  Mic,
  MessageSquareDashed,
  PanelRight,
  Pencil,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  ThumbsDown,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Alert, Badge, Button, EmptyState, Input, Loading, Modal, Segmented, Select, Spinner, Textarea, Toggle, cx, useToast } from '../components/ui'
import { patch, post } from '../lib/api'
import { MODE_LABEL, PROVIDER_LABEL, formatDateTime, formatTime, timeAgo, useApi } from '../lib/hooks'

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'attention', label: 'Attention' },
  { value: 'drafts', label: 'Drafts' },
  { value: 'unread', label: 'Unread' },
  { value: 'takeover', label: 'Takeover' },
  { value: 'resolved', label: 'Resolved' },
]

const REASON_LABEL = {
  model_requested_review: 'AI asked for review',
  low_confidence: 'Low confidence',
  unverified_figures: 'Numbers not in knowledge base',
  possible_commitment: 'Possible commitment',
  possible_instruction_leak: 'Suspicious content',
  sensitive_intent: 'Sensitive topic',
  escalated: 'Escalated',
  window_closed: '24h window closed',
  outside_operating_hours: 'Outside operating hours',
  auto_reply_rate_limit: 'Auto-reply limit reached',
  stale_message: 'Old message',
  voice_requires_approval: 'Voice needs approval',
  evaluation_failed: 'Failed quality check',
  evaluation_unavailable: 'Quality check unavailable',
  state_changed: 'Human acted meanwhile',
  newer_customer_message: 'Newer message arrived',
  send_failed: 'Send failed',
  regenerated_by_user: 'Regenerated',
  invalid_knowledge_reference: 'Invalid knowledge reference',
  intent_not_allowed_for_auto: 'Intent not allowed for auto',
}

function reasonLabel(r) {
  if (r.startsWith('review_topic:')) return `Topic: ${r.split(':')[1]}`
  if (r.startsWith('reason_')) return r.slice(7).replaceAll('_', ' ')
  if (r.startsWith('action_')) return `Action: ${r.slice(7)}`
  return REASON_LABEL[r] || r.replaceAll('_', ' ')
}

/* ------------------------------------------------------------------ */
function ConversationList({ activeId, filter, setFilter }) {
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setQ(search), 300)
    return () => clearTimeout(t)
  }, [search])
  const params = new URLSearchParams()
  if (filter !== 'all') params.set('filter', filter)
  if (q) params.set('search', q)
  const { data, loading } = useApi(`/conversations/?${params}`, { interval: 5000 })
  const navigate = useNavigate()

  return (
    <div className="flex h-full flex-col border-r border-line bg-white">
      <div className="space-y-3 border-b border-line p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-stone-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, number or message"
            className="h-9 w-full rounded-lg border border-line bg-stone-50 pl-9 pr-3 text-sm focus:border-brand-500 focus:bg-white focus:outline-none" />
        </div>
        <div className="scroll-thin -mx-1 flex gap-1 overflow-x-auto px-1">
          {FILTERS.map((f) => (
            <button key={f.value} onClick={() => setFilter(f.value)}
              className={cx('shrink-0 rounded-full px-2.5 py-1 text-xs font-medium transition-colors',
                filter === f.value ? 'bg-ink-900 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200')}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto">
        {loading && !data && <Loading />}
        {data?.length === 0 && (
          <EmptyState icon={MessageSquareDashed} title="No conversations" description={filter === 'all' && !q ? 'Messages sent to your WhatsApp number will appear here.' : 'Nothing matches this filter.'} />
        )}
        {data?.map((c) => (
          <button key={c.id} onClick={() => navigate(`/inbox/${c.id}${filter !== 'all' ? `?filter=${filter}` : ''}`)}
            className={cx('flex w-full gap-3 border-b border-line/70 px-3 py-3 text-left transition-colors',
              String(c.id) === String(activeId) ? 'bg-brand-50/70' : 'hover:bg-stone-50')}>
            <div className="relative grid size-10 shrink-0 place-items-center rounded-full bg-gradient-to-br from-stone-200 to-stone-300 font-semibold text-stone-700">
              {c.contact.name.replace('+', '')[0]?.toUpperCase()}
              {c.human_takeover && <span className="absolute -bottom-0.5 -right-0.5 grid size-4 place-items-center rounded-full bg-violet-600 ring-2 ring-white"><Hand className="size-2.5 text-white" /></span>}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <p className={cx('truncate text-sm', c.unread_count ? 'font-semibold' : 'font-medium')}>{c.contact.name}</p>
                <span className={cx('shrink-0 text-[11px]', c.unread_count ? 'font-semibold text-brand-700' : 'text-stone-400')}>{timeAgo(c.last_message_at)}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2">
                <p className="flex-1 truncate text-xs text-stone-500">{c.last_message_preview || '—'}</p>
                {c.unread_count > 0 && <span className="rounded-full bg-brand-600 px-1.5 text-[10px] font-semibold text-white">{c.unread_count}</span>}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {c.needs_attention && <Badge color="red" icon={AlertTriangle}>Attention</Badge>}
                {c.pending_drafts > 0 && <Badge color="amber">Draft</Badge>}
                {c.automation_paused && <Badge>Paused</Badge>}
                {c.automation_override !== 'inherit' && <Badge color="blue">{MODE_LABEL[c.automation_override]}</Badge>}
                {c.status === 'resolved' && <Badge color="green">Resolved</Badge>}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
function SenderLabel({ m }) {
  if (m.direction === 'in') return null
  const prov = m.provider ? `${PROVIDER_LABEL[m.provider.provider] || m.provider.provider}${m.provider.fallback_used ? ' (fallback)' : ''}` : ''
  const map = {
    ai_auto: { icon: Bot, text: `AI · sent automatically${prov ? ` · ${prov}` : ''}`, cls: 'text-brand-700' },
    ai_approved: { icon: CheckCircle2, text: `AI draft · approved by ${m.created_by_name || 'team'}${prov ? ` · ${prov}` : ''}`, cls: 'text-violet-700' },
    human: { icon: UserRound, text: m.created_by_name || 'Team', cls: 'text-sky-700' },
    system: { icon: Sparkles, text: 'System', cls: 'text-stone-500' },
  }
  const s = map[m.sender_type] || map.system
  return (
    <p className={cx('mb-1 flex items-center gap-1 text-[11px] font-medium', s.cls)}>
      <s.icon className="size-3" /> {s.text}
    </p>
  )
}

function StatusIcon({ status }) {
  if (status === 'read' || status === 'played') return <CheckCheck className="size-3.5 text-sky-500" />
  if (status === 'delivered') return <CheckCheck className="size-3.5 text-stone-400" />
  if (status === 'sent') return <Check className="size-3.5 text-stone-400" />
  if (status === 'failed') return <AlertTriangle className="size-3.5 text-red-500" />
  return <Clock className="size-3 text-stone-400" />
}

function AudioPlayer({ url, mime }) {
  const [src, setSrc] = useState(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    let revoke
    fetch(url, { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => {
        revoke = URL.createObjectURL(b)
        setSrc(revoke)
      })
      .catch(() => setErr(true))
    return () => revoke && URL.revokeObjectURL(revoke)
  }, [url])
  if (err) return <p className="text-xs text-red-600">Audio unavailable</p>
  if (!src) return <Spinner className="size-4" />
  return <audio controls src={src} className="h-9 w-60 max-w-full" type={mime} />
}

function MessageBubble({ m, onRetry }) {
  const inbound = m.direction === 'in'
  const bg = inbound ? 'bg-role-customer' : m.sender_type === 'human' ? 'bg-role-human' : m.sender_type === 'ai_approved' ? 'bg-role-approved' : 'bg-role-ai'
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className={cx('flex', inbound ? 'justify-start' : 'justify-end')}>
      <div className={cx('max-w-[85%] rounded-2xl px-3.5 py-2 shadow-sm sm:max-w-[70%]', bg, inbound ? 'rounded-bl-md' : 'rounded-br-md')}>
        <SenderLabel m={m} />
        {m.message_type === 'audio' && (
          <div className="mb-1 flex items-center gap-2">
            <Mic className="size-4 text-stone-500" />
            {m.media_url ? <AudioPlayer url={m.media_url} mime={m.media_mime} /> : <span className="text-xs text-stone-500">{m.media_status === 'pending' ? 'Downloading voice message…' : 'Voice message'}</span>}
          </div>
        )}
        {m.message_type === 'image' && m.media_url && <p className="text-xs text-stone-500">[image] <a className="underline" href={m.media_url} target="_blank" rel="noreferrer">open</a></p>}
        {m.text && <p className={cx('whitespace-pre-wrap break-words text-sm leading-relaxed', m.message_type === 'audio' && 'text-xs italic text-stone-600')}>{m.message_type === 'audio' && !inbound ? `Transcript: ${m.text}` : m.text}</p>}
        <div className="mt-1 flex items-center justify-end gap-1 text-[10px] text-stone-500">
          {formatTime(m.created_at)}
          {!inbound && <StatusIcon status={m.status} />}
        </div>
        {m.status === 'failed' && (
          <div className="mt-1.5 rounded-lg bg-red-50 px-2 py-1.5 text-xs text-red-700">
            <p>Not delivered: {m.error_message || 'unknown error'} {m.error_code && <span className="opacity-60">({m.error_code})</span>}</p>
            {m.message_type === 'text' && (
              <button onClick={() => onRetry(m)} className="mt-1 inline-flex items-center gap-1 font-medium underline"><RotateCcw className="size-3" /> Retry</button>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}

/* ------------------------------------------------------------------ */
function DraftPanel({ draft, conversation, onDone }) {
  const toast = useToast()
  const [text, setText] = useState(draft.text)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(null)
  const [format, setFormat] = useState(draft.reply_format || 'text')
  useEffect(() => {
    setText(draft.text)
    setEditing(false)
    setFormat(draft.reply_format || 'text')
  }, [draft.id, draft.text, draft.reply_format])

  async function act(kind) {
    setBusy(kind)
    try {
      if (kind === 'approve') await post(`/drafts/${draft.id}/approve/`, { text, reply_format: format })
      if (kind === 'reject') await post(`/drafts/${draft.id}/reject/`)
      if (kind === 'regen') await post(`/conversations/${conversation.id}/regenerate/`, { reply_format: format })
      toast(kind === 'approve' ? 'Reply sent.' : kind === 'reject' ? 'Draft rejected.' : 'New draft generated.')
      onDone()
    } catch (err) {
      toast(err.message, 'error')
      onDone()
    } finally {
      setBusy(null)
    }
  }

  const suggestion = draft.status === 'suggestion'
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}
      className="mx-3 mb-2 rounded-2xl border-2 border-dashed border-amber-300 bg-role-draft p-3 shadow-sm sm:mx-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1 text-xs font-semibold text-amber-900">
          <Sparkles className="size-3.5" /> {suggestion ? 'AI suggestion (manual mode)' : 'AI draft awaiting approval'}
        </span>
        {draft.provider && <Badge color="gray">{PROVIDER_LABEL[draft.provider.provider]}{draft.provider.fallback_used ? ' · fallback' : ''}</Badge>}
        {draft.confidence != null && <Badge color={draft.confidence >= 0.75 ? 'green' : 'amber'}>conf. {Math.round(draft.confidence * 100)}%</Badge>}
        {draft.intent && <Badge color="blue">{draft.intent.replaceAll('_', ' ')}</Badge>}
        {(draft.review_reasons || []).map((r) => <Badge key={r} color="amber">{reasonLabel(r)}</Badge>)}
      </div>
      {draft.error_message && <p className="mb-2 rounded-lg bg-red-50 px-2 py-1 text-xs text-red-700">Last attempt failed: {draft.error_message}</p>}
      {editing ? (
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} autoFocus
          className="w-full rounded-lg border border-amber-300 bg-white p-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300" />
      ) : (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-900">{text}</p>
      )}
      {draft.rationale && <p className="mt-1.5 text-[11px] text-amber-900/70">Why: {draft.rationale}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="brand" icon={Send} loading={busy === 'approve'} disabled={!!busy || !text.trim()} onClick={() => act('approve')}>
          {editing && text !== draft.text ? 'Send edited' : 'Approve & send'}
        </Button>
        <Button size="sm" variant="secondary" icon={editing ? Check : Pencil} onClick={() => setEditing((v) => !v)} disabled={!!busy}>{editing ? 'Done' : 'Edit'}</Button>
        <Button size="sm" variant="secondary" icon={RefreshCw} loading={busy === 'regen'} disabled={!!busy} onClick={() => act('regen')}>Regenerate</Button>
        <Button size="sm" variant="ghost" icon={ThumbsDown} loading={busy === 'reject'} disabled={!!busy} onClick={() => act('reject')}>Reject</Button>
        <div className="ml-auto">
          <Segmented value={format} onChange={setFormat} options={[{ value: 'text', label: 'Text' }, { value: 'voice', label: 'Voice' }]} />
        </div>
      </div>
    </motion.div>
  )
}

function TemplateForm({ conversation, onSent }) {
  const toast = useToast()
  const [name, setName] = useState('hello_world')
  const [lang, setLang] = useState('en_US')
  const [busy, setBusy] = useState(false)
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={async (e) => {
      e.preventDefault()
      setBusy(true)
      try {
        await post(`/conversations/${conversation.id}/send-template/`, { name, language: lang })
        toast('Template sent.')
        onSent()
      } catch (err) {
        toast(err.message, 'error')
      } finally {
        setBusy(false)
      }
    }}>
      <div className="w-44"><Input label="Approved template name" value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div className="w-24"><Input label="Language" value={lang} onChange={(e) => setLang(e.target.value)} /></div>
      <Button type="submit" variant="secondary" size="md" loading={busy}>Send template</Button>
    </form>
  )
}

function Composer({ conversation, onSent }) {
  const toast = useToast()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  async function send(e) {
    e?.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    try {
      await post(`/conversations/${conversation.id}/messages/`, { text })
      setText('')
      onSent()
    } catch (err) {
      toast(err.message, 'error')
      onSent()
    } finally {
      setBusy(false)
    }
  }
  if (!conversation.within_service_window) {
    return (
      <div className="border-t border-line bg-white p-3 sm:p-4">
        <Alert tone="warn" title="24-hour customer service window closed" className="mb-3">
          WhatsApp only allows approved template messages until the customer writes again.
        </Alert>
        <TemplateForm conversation={conversation} onSent={onSent} />
      </div>
    )
  }
  return (
    <form onSubmit={send} className="flex items-end gap-2 border-t border-line bg-white p-3 sm:p-4">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} placeholder="Type a reply as yourself…"
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) send(e) }}
        className="max-h-40 min-h-10 flex-1 resize-none rounded-xl border border-line bg-stone-50 px-3 py-2.5 text-sm focus:border-brand-500 focus:bg-white focus:outline-none" />
      <Button type="submit" variant="brand" icon={Send} loading={busy} disabled={!text.trim()} className="h-10" aria-label="Send">Send</Button>
    </form>
  )
}

/* ------------------------------------------------------------------ */
function DetailsPanel({ conversation, onChange }) {
  const toast = useToast()
  const [contact, setContact] = useState(conversation.contact)
  const { data: gens } = useApi(`/ai/generations/?conversation=${conversation.id}`, { interval: 8000 })
  useEffect(() => setContact(conversation.contact), [conversation.contact])
  async function update(body) {
    try {
      await patch(`/conversations/${conversation.id}/`, body)
      onChange()
    } catch (err) {
      toast(err.message, 'error')
    }
  }
  return (
    <div className="scroll-thin h-full space-y-5 overflow-y-auto border-l border-line bg-white p-4">
      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Customer</h4>
        <div className="space-y-3">
          <Input label="Display name" value={contact.display_name} placeholder={contact.profile_name} onChange={(e) => setContact({ ...contact, display_name: e.target.value })} />
          <p className="text-xs text-stone-500">WhatsApp: +{contact.wa_id}{contact.profile_name && ` · profile “${contact.profile_name}”`}</p>
          <Textarea label="Notes the assistant may use" rows={3} value={contact.notes} hint="Only store what you're allowed to retain." onChange={(e) => setContact({ ...contact, notes: e.target.value })} />
          <Button size="sm" variant="secondary" onClick={async () => {
            try {
              await patch(`/conversations/${conversation.id}/contact/`, { display_name: contact.display_name, notes: contact.notes })
              toast('Contact saved.')
              onChange()
            } catch (err) { toast(err.message, 'error') }
          }}>Save contact</Button>
        </div>
      </section>
      <section className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-stone-500">Automation for this chat</h4>
        <Select label="Mode" value={conversation.automation_override} onChange={(e) => update({ automation_override: e.target.value })}
          options={[{ value: 'inherit', label: 'Use workspace setting' }, { value: 'off', label: 'Off' }, { value: 'manual', label: 'Manual (drafts only)' },
            { value: 'approval', label: 'Approval required' }, { value: 'automatic', label: 'Automatic' }]} />
        <Select label="Reply format" value={conversation.reply_format} onChange={(e) => update({ reply_format: e.target.value })}
          options={[{ value: 'inherit', label: 'Use workspace setting' }, { value: 'text', label: 'Text' }, { value: 'voice', label: 'Voice note' }]} />
        <Toggle label="Pause automation" checked={conversation.automation_paused} onChange={(v) => update({ automation_paused: v })} description="AI stops drafting and sending until resumed." />
        <p className="text-xs text-stone-500">Effective mode right now: <b>{MODE_LABEL[conversation.effective_mode]}</b></p>
      </section>
      {conversation.summary && (
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">Conversation summary</h4>
          <p className="text-sm text-stone-700">{conversation.summary}</p>
        </section>
      )}
      <section>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">AI activity</h4>
        <ul className="space-y-2">
          {(gens || []).slice(0, 12).map((g) => (
            <li key={g.id} className="rounded-lg border border-line p-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium capitalize">{g.operation}</span>
                <Badge color={g.status === 'success' ? 'green' : 'red'}>{g.status.replace('_', ' ')}</Badge>
              </div>
              <p className="mt-1 text-stone-500">{PROVIDER_LABEL[g.provider]} · {g.model}{g.fallback_used ? ' · fallback' : ''} · {g.latency_ms} ms</p>
              {g.error_message && <p className="mt-1 text-red-600">{g.error_message}</p>}
              <p className="mt-0.5 text-stone-400">{formatDateTime(g.created_at)}</p>
            </li>
          ))}
          {gens?.length === 0 && <li className="text-xs text-stone-500">No AI activity yet.</li>}
        </ul>
      </section>
    </div>
  )
}

/* ------------------------------------------------------------------ */
function Thread({ id, onBack }) {
  const toast = useToast()
  const { data: conv, reload: reloadConv, error } = useApi(`/conversations/${id}/`, { interval: 5000 })
  const { data: messages, reload: reloadMsgs } = useApi(`/conversations/${id}/messages/`, { interval: 4000 })
  const { data: drafts, reload: reloadDrafts } = useApi(`/conversations/${id}/drafts/`, { interval: 4000 })
  const [showDetails, setShowDetails] = useState(false)
  const [busy, setBusy] = useState(null)
  const bottom = useRef(null)
  const lastCount = useRef(0)

  useEffect(() => {
    post(`/conversations/${id}/read/`).catch(() => {})
  }, [id, messages?.length])

  useEffect(() => {
    if (messages && messages.length !== lastCount.current) {
      bottom.current?.scrollIntoView({ behavior: lastCount.current ? 'smooth' : 'auto' })
      lastCount.current = messages.length
    }
  }, [messages])

  const refreshAll = () => Promise.all([reloadConv(true), reloadMsgs(true), reloadDrafts(true)])
  const draft = useMemo(() => drafts?.find((d) => ['pending', 'suggestion', 'failed'].includes(d.status)), [drafts])

  async function action(kind) {
    setBusy(kind)
    try {
      await post(`/conversations/${id}/${kind}/`)
      toast({ takeover: 'You have taken over. AI is paused for this chat.', resume: 'AI assistance resumed.', resolve: 'Marked resolved.', reopen: 'Reopened.' }[kind])
      await refreshAll()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(null)
    }
  }

  if (error) return <div className="p-6"><Alert tone="error">{error.message}</Alert></div>
  if (!conv) return <Loading />

  return (
    <div className="flex h-full min-w-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-white px-3 py-2.5 sm:px-4">
          <button onClick={onBack} className="rounded-md p-1 hover:bg-stone-100 md:hidden" aria-label="Back"><ArrowLeft className="size-5" /></button>
          <div className="grid size-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-stone-200 to-stone-300 font-semibold text-stone-700">
            {conv.contact.name.replace('+', '')[0]?.toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{conv.contact.name}</p>
            <p className="flex items-center gap-2 text-xs text-stone-500">
              +{conv.contact.wa_id}
              <span className="hidden sm:inline">·</span>
              <span className="hidden sm:inline">AI: <b className="font-medium text-ink-800">{MODE_LABEL[conv.effective_mode]}</b></span>
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            {conv.human_takeover ? (
              <Button size="sm" variant="brand" icon={Play} loading={busy === 'resume'} onClick={() => action('resume')}>Resume AI</Button>
            ) : (
              <Button size="sm" variant="primary" icon={Hand} loading={busy === 'takeover'} onClick={() => action('takeover')}>Take over</Button>
            )}
            {conv.status === 'open' ? (
              <Button size="sm" variant="secondary" icon={CheckCircle2} loading={busy === 'resolve'} onClick={() => action('resolve')} className="hidden sm:inline-flex">Resolve</Button>
            ) : (
              <Button size="sm" variant="secondary" icon={RotateCcw} loading={busy === 'reopen'} onClick={() => action('reopen')} className="hidden sm:inline-flex">Reopen</Button>
            )}
            <button onClick={() => setShowDetails((v) => !v)} className={cx('rounded-lg p-2 hover:bg-stone-100', showDetails && 'bg-stone-100')} aria-label="Toggle details">
              <PanelRight className="size-4" />
            </button>
          </div>
        </header>

        {conv.human_takeover && (
          <div className="flex items-center gap-2 border-b border-violet-200 bg-violet-50 px-4 py-2 text-xs text-violet-800">
            <Hand className="size-3.5" /> {conv.takeover_by_name || 'A team member'} is handling this chat. The AI will not draft or send replies until you resume it.
          </div>
        )}
        {conv.needs_attention && (
          <div className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-800">
            <AlertTriangle className="size-3.5 shrink-0" />
            <span className="flex-1">{conv.attention_reason || 'This conversation needs attention.'}</span>
            <button onClick={async () => { await patch(`/conversations/${id}/`, { needs_attention: false }); reloadConv(true) }} className="rounded p-0.5 hover:bg-red-100" aria-label="Dismiss"><X className="size-3.5" /></button>
          </div>
        )}

        <div className="chat-wallpaper scroll-thin flex-1 space-y-2 overflow-y-auto px-3 py-4 sm:px-6">
          {!messages && <Loading />}
          {messages?.map((m) => (
            <MessageBubble key={m.id} m={m} onRetry={async (msg) => {
              try { await post(`/messages/${msg.id}/retry/`); toast('Message resent.') } catch (err) { toast(err.message, 'error') }
              reloadMsgs(true)
            }} />
          ))}
          <div ref={bottom} />
        </div>

        <AnimatePresence>{draft && !conv.human_takeover && <DraftPanel key={draft.id} draft={draft} conversation={conv} onDone={refreshAll} />}</AnimatePresence>
        {!draft && !conv.human_takeover && conv.effective_mode !== 'off' && messages?.some((m) => m.direction === 'in') && (
          <div className="mx-3 mb-2 flex justify-end sm:mx-4">
            <Button size="sm" variant="ghost" icon={Sparkles} loading={busy === 'regen'} onClick={async () => {
              setBusy('regen')
              try { await post(`/conversations/${id}/regenerate/`, {}); await reloadDrafts(true) } catch (err) { toast(err.message, 'error') }
              setBusy(null)
            }}>Draft a reply with AI</Button>
          </div>
        )}
        <Composer conversation={conv} onSent={refreshAll} />
      </div>
      <AnimatePresence>
        {showDetails && (
          <motion.div initial={{ width: 0, opacity: 0 }} animate={{ width: 320, opacity: 1 }} exit={{ width: 0, opacity: 0 }} className="hidden shrink-0 overflow-hidden lg:block">
            <div className="h-full w-80"><DetailsPanel conversation={conv} onChange={refreshAll} /></div>
          </motion.div>
        )}
      </AnimatePresence>
      {showDetails && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink-950/40" onClick={() => setShowDetails(false)} />
          <div className="absolute inset-y-0 right-0 w-[min(90vw,340px)]"><DetailsPanel conversation={conv} onChange={refreshAll} /></div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
function SimulateModal({ open, onClose }) {
  const toast = useToast()
  const [form, setForm] = useState({ kind: 'customer', name: 'Test Customer', wa_id: '15550001111', text: 'Hi, do you have any slots available tomorrow?' })
  const [busy, setBusy] = useState(false)
  return (
    <Modal open={open} onClose={onClose} title="Simulate an inbound message"
      footer={<>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button loading={busy} onClick={async () => {
          setBusy(true)
          try {
            await post('/dev/simulate-inbound/', form)
            toast(form.kind === 'owner_echo' ? 'Owner reply simulated. The AI is paused for this chat.' : 'Simulated message injected. The AI pipeline is running.')
            onClose()
          } catch (err) { toast(err.message, 'error') } finally { setBusy(false) }
        }}>Inject message</Button>
      </>}>
      <Alert tone="warn" className="mb-4" title="Development tool">
        This creates a webhook-shaped event locally. It does not come from WhatsApp. Replies are still sent through the real Cloud API and will fail visibly if credentials are missing or the number is not a real recipient.
      </Alert>
      <Segmented className="mb-4" value={form.kind} onChange={(kind) => setForm({ ...form, kind })}
        options={[{ value: 'customer', label: 'Customer message' }, { value: 'owner_echo', label: 'Owner reply from phone' }]} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Customer name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input label="WhatsApp number (digits)" value={form.wa_id} onChange={(e) => setForm({ ...form, wa_id: e.target.value.replace(/\D/g, '') })} />
        <div className="sm:col-span-2"><Textarea label="Message" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} /></div>
      </div>
    </Modal>
  )
}

export default function Inbox() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const filter = params.get('filter') || 'all'
  const navigate = useNavigate()
  const { data: integrations } = useApi('/integrations/')
  const [simOpen, setSimOpen] = useState(false)
  const debug = integrations?.whatsapp?.env?.debug

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line bg-white px-4 py-3">
        <div>
          <h1 className="font-display text-lg font-semibold">Inbox</h1>
          <p className="hidden text-xs text-stone-500 sm:block">
            <span className="mr-3 inline-flex items-center gap-1"><span className="size-2 rounded-full bg-role-ai ring-1 ring-brand-300" /> AI auto</span>
            <span className="mr-3 inline-flex items-center gap-1"><span className="size-2 rounded-full bg-role-approved ring-1 ring-violet-300" /> AI approved</span>
            <span className="mr-3 inline-flex items-center gap-1"><span className="size-2 rounded-full bg-role-human ring-1 ring-sky-300" /> Team</span>
            <span className="inline-flex items-center gap-1"><span className="size-2 rounded-full bg-role-draft ring-1 ring-amber-300" /> Draft</span>
          </p>
        </div>
        {debug && <Button size="sm" variant="secondary" icon={FlaskConical} onClick={() => setSimOpen(true)}>Simulate message</Button>}
      </div>
      <div className="flex min-h-0 flex-1">
        <div className={cx('w-full shrink-0 md:w-80', id && 'hidden md:block')}>
          <ConversationList activeId={id} filter={filter} setFilter={(f) => setParams(f === 'all' ? {} : { filter: f })} />
        </div>
        <div className={cx('min-w-0 flex-1', !id && 'hidden md:block')}>
          {id ? (
            <Thread key={id} id={id} onBack={() => navigate(`/inbox${filter !== 'all' ? `?filter=${filter}` : ''}`)} />
          ) : (
            <div className="chat-wallpaper flex h-full items-center justify-center">
              <EmptyState icon={MessageSquareDashed} title="Select a conversation" description="Pick a chat to read messages, review AI drafts or reply yourself." />
            </div>
          )}
        </div>
      </div>
      <SimulateModal open={simOpen} onClose={() => setSimOpen(false)} />
    </div>
  )
}
