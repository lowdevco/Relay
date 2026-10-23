import { motion } from 'framer-motion'
import { Clock, Hand, PenLine, Save, ShieldAlert, ShieldCheck, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Alert, Button, Card, CardHeader, Input, Loading, Modal, PageHeader, Segmented, Toggle, cx, useToast } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { put } from '../lib/api'
import { useApi } from '../lib/hooks'

const MODES = [
  { value: 'manual', icon: PenLine, title: 'Manual', text: 'AI analyzes messages and prepares suggestions. Nothing is ever sent automatically.' },
  { value: 'approval', icon: ShieldCheck, title: 'Approval required', text: 'AI drafts every reply. You approve, edit, reject or regenerate before it is sent.' },
  { value: 'automatic', icon: Zap, title: 'Automatic', text: 'Eligible replies are sent after validation, quality checks and your rules. Anything risky is queued.' },
]
const DAYS = [['mon', 'Mon'], ['tue', 'Tue'], ['wed', 'Wed'], ['thu', 'Thu'], ['fri', 'Fri'], ['sat', 'Sat'], ['sun', 'Sun']]

function ListEditor({ label, hint, value, onChange }) {
  const [draft, setDraft] = useState('')
  return (
    <div>
      <p className="text-sm font-medium text-ink-800">{label}</p>
      {hint && <p className="mb-2 text-xs text-stone-500">{hint}</p>}
      <div className="flex flex-wrap gap-1.5">
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-full bg-stone-100 py-0.5 pl-2.5 pr-1 text-xs">
            {v}
            <button onClick={() => onChange(value.filter((x) => x !== v))} className="rounded-full px-1 text-stone-400 hover:bg-stone-200 hover:text-ink-900" aria-label={`Remove ${v}`}>×</button>
          </span>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); const t = draft.trim(); if (t && !value.includes(t)) onChange([...value, t]); setDraft('') }}>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Add…" className="h-6 w-28 rounded-full border border-dashed border-stone-300 px-2.5 text-xs focus:border-brand-500 focus:outline-none" />
        </form>
      </div>
    </div>
  )
}

export default function Automation() {
  const { canManage } = useAuth()
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/automation/')
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [confirmAuto, setConfirmAuto] = useState(false)
  useEffect(() => { if (data) setForm(data) }, [data])
  if (loading && !form) return <Loading />
  if (error) return <Alert tone="error">{error.message}</Alert>
  if (!form) return null
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }))
  const dirty = JSON.stringify(form) !== JSON.stringify(data)

  async function save(extra = {}) {
    setSaving(true)
    try {
      const { updated_at, ...body } = form
      await put('/automation/', { ...body, ...extra })
      toast('Automation settings saved.')
      reload(true)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  function trySave() {
    if (form.mode === 'automatic' && data.mode !== 'automatic') setConfirmAuto(true)
    else save()
  }

  const hours = form.operating_hours || {}
  return (
    <div>
      <PageHeader title="Automation" description="Decide how much the assistant does on its own. These rules are enforced on the server for every message."
        actions={<Button icon={Save} onClick={trySave} loading={saving} disabled={!dirty || !canManage}>{dirty ? 'Save changes' : 'Saved'}</Button>} />

      <Card className="mb-4">
        <CardHeader title="Automation mode" action={<Toggle label="Automation enabled" checked={form.automation_enabled} onChange={set('automation_enabled')} disabled={!canManage} />} />
        <div className={cx('grid gap-3 p-5 md:grid-cols-3', !form.automation_enabled && 'pointer-events-none opacity-50')}>
          {MODES.map((m) => {
            const active = form.mode === m.value
            return (
              <motion.button key={m.value} whileTap={{ scale: 0.99 }} onClick={() => canManage && set('mode')(m.value)} aria-pressed={active}
                className={cx('rounded-xl2 border p-4 text-left transition-all', active ? 'border-brand-500 bg-brand-50/40 shadow-[0_0_0_4px_rgba(16,185,129,0.12)]' : 'border-line hover:border-stone-300')}>
                <div className={cx('mb-3 inline-flex rounded-lg p-2', active ? 'bg-brand-600 text-white' : 'bg-stone-100 text-stone-600')}><m.icon className="size-4" /></div>
                <p className="font-display font-semibold">{m.title}</p>
                <p className="mt-1 text-sm text-stone-500">{m.text}</p>
              </motion.button>
            )
          })}
        </div>
        <p className="border-t border-line px-5 py-3 text-xs text-stone-500">
          <Hand className="mr-1 inline size-3.5" />You can override the mode, pause, or take over any single conversation from the inbox.
        </p>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Safety thresholds" icon={ShieldAlert} />
          <div className="space-y-5 p-5">
            <div>
              <div className="mb-1 flex justify-between text-sm"><span className="font-medium">Minimum confidence for auto-send</span><b className="tabular-nums">{Math.round(form.confidence_threshold * 100)}%</b></div>
              <input type="range" min="0.5" max="1" step="0.05" value={form.confidence_threshold} onChange={(e) => set('confidence_threshold')(Number(e.target.value))} className="w-full accent-brand-600" />
              <p className="text-xs text-stone-500">Model confidence is an uncalibrated estimate, so it is combined with the rules below.</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="Max auto-replies per chat per hour" type="number" min="1" max="100" value={form.max_auto_replies_per_hour} onChange={(e) => set('max_auto_replies_per_hour')(Number(e.target.value))} />
              <Input label="Flag after N consecutive AI failures" type="number" min="1" max="10" value={form.max_consecutive_failures} onChange={(e) => set('max_consecutive_failures')(Number(e.target.value))} />
            </div>
            <ListEditor label="Topics that always need approval" hint="If the customer's message contains any of these, the reply is queued for you." value={form.review_topics} onChange={set('review_topics')} />
            <ListEditor label="Escalate when the customer says" hint="Marks the chat as needing attention and never auto-replies." value={form.escalation_keywords} onChange={set('escalation_keywords')} />
            <ListEditor label="Intents allowed for auto-send (optional)" hint="Leave empty to allow any intent not blocked by other rules. e.g. availability_question, opening_hours" value={form.allowed_auto_intents} onChange={set('allowed_auto_intents')} />
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Operating hours" icon={Clock} description="Outside these hours automatic replies are queued for approval." />
            <div className="space-y-3 p-5">
              <Toggle label="Only auto-send during operating hours" checked={form.operating_hours_enabled} onChange={set('operating_hours_enabled')} />
              <div className={cx('space-y-2', !form.operating_hours_enabled && 'opacity-50')}>
                {DAYS.map(([d, label]) => {
                  const range = hours[d]?.[0]
                  return (
                    <div key={d} className="flex items-center gap-3 text-sm">
                      <label className="flex w-20 items-center gap-2">
                        <input type="checkbox" className="accent-brand-600" checked={!!range} disabled={!form.operating_hours_enabled}
                          onChange={(e) => set('operating_hours')({ ...hours, [d]: e.target.checked ? [['09:00', '18:00']] : [] })} />
                        {label}
                      </label>
                      {range ? (
                        <>
                          <input type="time" value={range[0]} disabled={!form.operating_hours_enabled} className="h-8 rounded-md border border-line px-2"
                            onChange={(e) => set('operating_hours')({ ...hours, [d]: [[e.target.value, range[1]]] })} />
                          <span className="text-stone-400">–</span>
                          <input type="time" value={range[1]} disabled={!form.operating_hours_enabled} className="h-8 rounded-md border border-line px-2"
                            onChange={(e) => set('operating_hours')({ ...hours, [d]: [[range[0], e.target.value]] })} />
                        </>
                      ) : <span className="text-stone-400">Closed</span>}
                    </div>
                  )
                })}
              </div>
            </div>
          </Card>
          <Card>
            <CardHeader title="Reply format" />
            <div className="space-y-4 p-5">
              <div>
                <p className="mb-2 text-sm font-medium">Default reply format</p>
                <Segmented value={form.default_reply_format} onChange={set('default_reply_format')} options={[{ value: 'text', label: 'Text' }, { value: 'voice', label: 'Voice note' }]} />
                <p className="mt-2 text-xs text-stone-500">Voice falls back to text when voice notes are not configured.</p>
              </div>
              <Toggle label="Voice notes always need approval" checked={form.voice_requires_approval} onChange={set('voice_requires_approval')} />
            </div>
          </Card>
        </div>
      </div>

      <Modal open={confirmAuto} onClose={() => setConfirmAuto(false)} title="Enable automatic replies?"
        footer={<><Button variant="secondary" onClick={() => setConfirmAuto(false)}>Cancel</Button><Button variant="brand" icon={Zap} onClick={() => { setConfirmAuto(false); save({ confirm_automatic: true }) }}>Yes, enable automatic mode</Button></>}>
        <p className="text-sm text-stone-600">The assistant will send replies to customers without you reviewing them first. It only sends when:</p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-stone-600">
          <li>the reply passed schema validation and a second quality check,</li>
          <li>confidence is above {Math.round(form.confidence_threshold * 100)}% and no numbers are unverified,</li>
          <li>no review topic, escalation, commitment or sensitive intent was detected,</li>
          <li>nobody on your team has taken over the conversation.</li>
        </ul>
      </Modal>
    </div>
  )
}
