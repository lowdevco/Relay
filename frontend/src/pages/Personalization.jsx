import { AnimatePresence, motion } from 'framer-motion'
import { MessageSquareQuote, Pencil, Plus, Save, Sparkles, Trash2, Wand2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Input, Loading, Modal, PageHeader, Scale, Segmented, Select, Textarea, Toggle, useToast } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { del, patch, post, put } from '../lib/api'
import { PROVIDER_LABEL, useApi } from '../lib/hooks'

const TEXT_FIELDS = [
  ['greetings', 'Greetings', 'e.g. "Hey!", "Hi there 👋"'],
  ['closings', 'Preferred closing phrases', 'e.g. "Talk soon!", "Cheers"'],
  ['vocabulary', 'Vocabulary to use', 'Words and phrases that sound like you'],
  ['phrases_to_avoid', 'Phrases to avoid', 'e.g. "Dear valued customer", "As an AI"'],
  ['regional_expressions', 'Regional expressions', 'Local slang or idioms that are OK to use'],
  ['code_switching', 'Code-switching', 'e.g. "Mix English and Hindi if the customer does"'],
  ['situation_guidelines', 'Situation-specific guidelines', 'e.g. "When someone is upset, apologize first and keep it short."'],
]

function ExampleModal({ example, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(example || { customer_message: '', preferred_reply: '', situation: '', language: '', authorized: true, active: true })
  const [busy, setBusy] = useState(false)
  useEffect(() => setForm(example || { customer_message: '', preferred_reply: '', situation: '', language: '', authorized: true, active: true }), [example])
  async function save() {
    setBusy(true)
    try {
      if (form.id) await patch(`/examples/${form.id}/`, form)
      else await post('/examples/', form)
      toast('Example saved.')
      onSaved()
      onClose()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={example !== undefined} onClose={onClose} title={form.id ? 'Edit example' : 'New style example'} wide
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy} disabled={!form.customer_message.trim() || !form.preferred_reply.trim()}>Save example</Button></>}>
      <div className="space-y-4">
        <Textarea label="Customer message" rows={2} value={form.customer_message} onChange={(e) => setForm({ ...form, customer_message: e.target.value })} placeholder="Hi, do you have any slots available tomorrow?" />
        <Textarea label="Your preferred reply" rows={3} value={form.preferred_reply} onChange={(e) => setForm({ ...form, preferred_reply: e.target.value })} placeholder="Hey! Yes, we have a couple of slots available tomorrow. What time works best for you?" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Situation (optional)" value={form.situation} onChange={(e) => setForm({ ...form, situation: e.target.value })} placeholder="booking, complaint, pricing…" />
          <Input label="Language (optional)" value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })} placeholder="en" />
        </div>
        <Toggle label="I'm authorized to use this content" description="Only use your own replies or content you have rights to." checked={form.authorized} onChange={(v) => setForm({ ...form, authorized: v })} />
        <Toggle label="Active" checked={form.active} onChange={(v) => setForm({ ...form, active: v })} />
        <p className="text-xs text-stone-500">Examples steer tone and structure only. Facts inside them (prices, availability) are not treated as current business information. The model is not fine-tuned. The most relevant 2–3 examples are added to each prompt.</p>
      </div>
    </Modal>
  )
}

function StyleProfileEditor({ profile, onChange }) {
  const p = profile || {}
  const list = (key) => (p[key] || []).join(', ')
  const setList = (key) => (e) => onChange({ ...p, [key]: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Input label="Typical greetings" value={list('typical_greetings')} onChange={setList('typical_greetings')} />
      <Input label="Common vocabulary" value={list('common_vocabulary')} onChange={setList('common_vocabulary')} />
      <Input label="Follow-up patterns" value={list('follow_up_patterns')} onChange={setList('follow_up_patterns')} />
      <Input label="Languages" value={list('languages')} onChange={setList('languages')} />
      <Input label="Average reply length (words)" type="number" value={p.average_reply_words ?? ''} onChange={(e) => onChange({ ...p, average_reply_words: Number(e.target.value) })} />
      <Select label="Emoji frequency" value={p.emoji_frequency || 'rare'} onChange={(e) => onChange({ ...p, emoji_frequency: e.target.value })}
        options={['none', 'rare', 'moderate', 'frequent'].map((v) => ({ value: v, label: v }))} />
      <div className="sm:col-span-2"><Textarea label="Notes" rows={2} value={p.notes || ''} onChange={(e) => onChange({ ...p, notes: e.target.value })} /></div>
    </div>
  )
}

function Preview({ persona }) {
  const [message, setMessage] = useState('Hi, do you have any slots available tomorrow?')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function run() {
    setBusy(true)
    setError('')
    try {
      const { id, workspace, version, updated_at, ...overrides } = persona
      setResult(await post('/persona/preview/', { customer_message: message, persona: overrides }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="lg:sticky lg:top-6">
      <CardHeader title="Preview" icon={MessageSquareQuote} description="Uses your unsaved settings, knowledge base and examples. Nothing is sent." />
      <div className="space-y-3 p-5">
        <Textarea label="Customer says" rows={2} value={message} onChange={(e) => setMessage(e.target.value)} />
        <Button icon={Wand2} onClick={run} loading={busy} disabled={!message.trim()} className="w-full">Generate preview</Button>
        {error && <Alert tone="error">{error}</Alert>}
        <AnimatePresence mode="wait">
          {result && (
            <motion.div key={result.reply.reply_text} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="chat-wallpaper space-y-2 rounded-xl p-3">
              <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-white px-3 py-2 text-sm shadow-sm">{message}</div>
              <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-role-ai px-3 py-2 text-sm shadow-sm">
                <p className="mb-1 text-[11px] font-medium text-brand-700">Preview · {PROVIDER_LABEL[result.provider]}{result.fallback_used ? ' (fallback)' : ''}</p>
                <p className="whitespace-pre-wrap">{result.reply.reply_text}</p>
              </div>
              <div className="flex flex-wrap gap-1 pt-1">
                <Badge color="blue">{result.reply.intent.replaceAll('_', ' ')}</Badge>
                <Badge color={result.reply.confidence >= 0.75 ? 'green' : 'amber'}>conf. {Math.round(result.reply.confidence * 100)}%</Badge>
                <Badge>{result.reply.suggested_action}</Badge>
                {result.reply.needs_human_review && <Badge color="amber">needs review</Badge>}
                <Badge>{result.knowledge_ids.length} knowledge · {result.example_ids.length} examples</Badge>
              </div>
              {result.reply.rationale && <p className="text-[11px] text-stone-500">Why: {result.reply.rationale}</p>}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Card>
  )
}

export default function Personalization() {
  const { canManage } = useAuth()
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/persona/')
  const { data: examples, reload: reloadExamples } = useApi('/examples/')
  const [persona, setPersona] = useState(null)
  const [saving, setSaving] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [editing, setEditing] = useState(undefined)
  const [tab, setTab] = useState('persona')

  useEffect(() => { if (data) setPersona(data) }, [data])
  if (loading && !persona) return <Loading />
  if (error) return <Alert tone="error">{error.message}</Alert>
  if (!persona) return null
  const set = (k) => (v) => setPersona((p) => ({ ...p, [k]: v?.target ? v.target.value : v }))
  const dirty = JSON.stringify(persona) !== JSON.stringify(data)

  async function save() {
    setSaving(true)
    try {
      const { version, updated_at, ...body } = persona
      await put('/persona/', body)
      toast('Persona saved. New replies will use it.')
      reload(true)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function analyze() {
    setAnalyzing(true)
    try {
      const r = await post('/persona/style-profile/')
      setPersona((p) => ({ ...p, style_profile: r.style_profile }))
      toast(`Style profile generated from ${r.examples_used} examples with ${PROVIDER_LABEL[r.provider]}. Review it, then save.`)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div>
      <PageHeader title="Personalization" description="Teach the assistant to sound like your business. Replies follow your style but never claim you personally wrote them."
        actions={<Button icon={Save} onClick={save} loading={saving} disabled={!dirty || !canManage}>{dirty ? 'Save changes' : 'Saved'}</Button>} />
      <Segmented className="mb-4" value={tab} onChange={setTab} options={[{ value: 'persona', label: 'Persona' }, { value: 'examples', label: `Style examples (${examples?.length ?? 0})` }, { value: 'profile', label: 'Style profile' }]} />

      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          {tab === 'persona' && (
            <>
              <Card>
                <CardHeader title="Identity" />
                <div className="grid gap-4 p-5 sm:grid-cols-2">
                  <Input label="Business name" value={persona.business_name} onChange={set('business_name')} />
                  <Input label="Assistant role" value={persona.assistant_role} onChange={set('assistant_role')} hint="e.g. booking assistant for a hair salon" />
                  <Input label="Preferred language" value={persona.preferred_language} onChange={set('preferred_language')} hint='"match customer", "en", "es"…' />
                  <Select label="Sentence length" value={persona.sentence_length} onChange={set('sentence_length')}
                    options={[{ value: 'short', label: 'Short' }, { value: 'medium', label: 'Medium' }, { value: 'long', label: 'Long' }]} />
                </div>
              </Card>
              <Card>
                <CardHeader title="Tone" />
                <div className="grid gap-6 p-5 sm:grid-cols-3">
                  <Scale label="Formality" value={persona.formality} onChange={set('formality')} left="casual" right="formal" />
                  <Scale label="Friendliness" value={persona.friendliness} onChange={set('friendliness')} left="neutral" right="warm" />
                  <Scale label="Conciseness" value={persona.conciseness} onChange={set('conciseness')} left="detailed" right="brief" />
                </div>
                <div className="border-t border-line p-5">
                  <p className="mb-2 text-sm font-medium text-ink-800">Emoji usage</p>
                  <Segmented value={persona.emoji_usage} onChange={set('emoji_usage')} options={['none', 'rare', 'moderate', 'frequent'].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }))} />
                </div>
              </Card>
              <Card>
                <CardHeader title="Wording" />
                <div className="grid gap-4 p-5 sm:grid-cols-2">
                  {TEXT_FIELDS.map(([k, label, ph]) => (
                    <Textarea key={k} label={label} rows={2} value={persona[k]} onChange={set(k)} placeholder={ph} />
                  ))}
                  <div className="sm:col-span-2">
                    <Textarea label="Custom persona instructions" rows={4} value={persona.custom_persona} onChange={set('custom_persona')}
                      placeholder="Anything else about how you talk to customers." />
                  </div>
                </div>
              </Card>
            </>
          )}

          {tab === 'examples' && (
            <Card>
              <CardHeader title="Style examples" description="Customer messages with your ideal replies. Only relevant examples are added to each prompt."
                action={<Button size="sm" icon={Plus} onClick={() => setEditing(null)} disabled={!canManage}>Add example</Button>} />
              {examples?.length === 0 && <EmptyState icon={MessageSquareQuote} title="No examples yet" description="Add 3–10 real replies you're happy with." />}
              <ul className="divide-y divide-line">
                {examples?.map((ex) => (
                  <li key={ex.id} className="group p-4">
                    <div className="flex items-start gap-3">
                      <div className="min-w-0 flex-1 space-y-2">
                        <p className="max-w-[90%] rounded-2xl rounded-bl-md bg-stone-100 px-3 py-1.5 text-sm">{ex.customer_message}</p>
                        <p className="ml-auto max-w-[90%] rounded-2xl rounded-br-md bg-role-ai px-3 py-1.5 text-sm">{ex.preferred_reply}</p>
                        <div className="flex gap-1">
                          {ex.situation && <Badge color="blue">{ex.situation}</Badge>}
                          {!ex.active && <Badge>inactive</Badge>}
                          {!ex.authorized && <Badge color="red">not authorized · unused</Badge>}
                        </div>
                      </div>
                      {canManage && (
                        <div className="flex gap-1 opacity-60 group-hover:opacity-100">
                          <button className="rounded-md p-1.5 hover:bg-stone-100" onClick={() => setEditing(ex)} aria-label="Edit"><Pencil className="size-4" /></button>
                          <button className="rounded-md p-1.5 text-red-600 hover:bg-red-50" aria-label="Delete" onClick={async () => {
                            if (!confirm('Delete this example?')) return
                            await del(`/examples/${ex.id}/`)
                            reloadExamples(true)
                          }}><Trash2 className="size-4" /></button>
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {tab === 'profile' && (
            <Card>
              <CardHeader title="Style profile" icon={Sparkles} description="A summary of your writing style. Generate it from your examples, then correct it."
                action={<Button size="sm" variant="secondary" icon={Wand2} onClick={analyze} loading={analyzing} disabled={!canManage}>Analyze examples</Button>} />
              <div className="p-5">
                {Object.keys(persona.style_profile || {}).length === 0 && !analyzing && (
                  <Alert tone="info" className="mb-4">No style profile yet. Add at least 2 examples and click “Analyze examples”, or fill it in yourself.</Alert>
                )}
                <StyleProfileEditor profile={persona.style_profile} onChange={set('style_profile')} />
              </div>
            </Card>
          )}
        </div>
        <Preview persona={persona} />
      </div>
      <ExampleModal example={editing} onClose={() => setEditing(undefined)} onSaved={() => reloadExamples(true)} />
    </div>
  )
}
