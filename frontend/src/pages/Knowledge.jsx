import { BookOpen, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Alert, Badge, Button, Card, EmptyState, Input, Loading, Modal, PageHeader, Select, Textarea, Toggle, cx, useToast } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { del, patch, post } from '../lib/api'
import { formatDateTime, useApi } from '../lib/hooks'

const EMPTY = { category: 'faq', title: '', content: '', keywords: '', active: true }

export default function Knowledge() {
  const { canManage } = useAuth()
  const toast = useToast()
  const { data: categories } = useApi('/knowledge-categories/')
  const { data, loading, error, reload } = useApi('/knowledge/')
  const [cat, setCat] = useState('all')
  const [q, setQ] = useState('')
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)

  const filtered = useMemo(
    () => (data || []).filter((e) => (cat === 'all' || e.category === cat) &&
      (!q || `${e.title} ${e.content} ${e.keywords}`.toLowerCase().includes(q.toLowerCase()))),
    [data, cat, q],
  )
  const counts = useMemo(() => (data || []).reduce((acc, e) => ({ ...acc, [e.category]: (acc[e.category] || 0) + 1 }), {}), [data])

  async function save() {
    setBusy(true)
    try {
      if (form.id) await patch(`/knowledge/${form.id}/`, form)
      else await post('/knowledge/', form)
      toast('Knowledge saved.')
      setForm(null)
      reload(true)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader title="Knowledge base" description="The only facts the assistant may state. If something isn't here, it asks a clarifying question or escalates to you instead of guessing."
        actions={<Button icon={Plus} onClick={() => setForm(EMPTY)} disabled={!canManage}>Add entry</Button>} />
      {error && <Alert tone="error">{error.message}</Alert>}
      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <Card className="h-fit p-2">
          <button onClick={() => setCat('all')} className={cx('flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm', cat === 'all' ? 'bg-stone-100 font-medium' : 'hover:bg-stone-50')}>
            All <span className="text-xs text-stone-400">{data?.length ?? 0}</span>
          </button>
          {categories?.map((c) => (
            <button key={c.value} onClick={() => setCat(c.value)} className={cx('flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm', cat === c.value ? 'bg-stone-100 font-medium' : 'hover:bg-stone-50')}>
              {c.label} <span className="text-xs text-stone-400">{counts[c.value] || 0}</span>
            </button>
          ))}
        </Card>
        <div className="space-y-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-stone-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search knowledge"
              className="h-10 w-full rounded-xl border border-line bg-white pl-9 pr-3 text-sm focus:border-brand-500 focus:outline-none" />
          </div>
          {loading && !data && <Loading />}
          {data && filtered.length === 0 && (
            <Card><EmptyState icon={BookOpen} title="No entries" description="Add your opening hours, prices, policies and FAQs." action={canManage && <Button size="sm" icon={Plus} onClick={() => setForm({ ...EMPTY, category: cat === 'all' ? 'faq' : cat })}>Add entry</Button>} /></Card>
          )}
          {filtered.map((e) => (
            <Card key={e.id} className={cx('group p-4', !e.active && 'opacity-60')}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge color={e.category === 'custom' ? 'violet' : 'green'}>{e.category_label}</Badge>
                    <h3 className="font-medium">{e.title}</h3>
                    {!e.active && <Badge>inactive</Badge>}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-stone-700">{e.content}</p>
                  {e.keywords && <p className="mt-2 text-xs text-stone-500">Keywords: {e.keywords}</p>}
                  <p className="mt-1 text-[11px] text-stone-400">Updated {formatDateTime(e.updated_at)} · ID {e.id}</p>
                </div>
                {canManage && (
                  <div className="flex shrink-0 gap-1 opacity-60 group-hover:opacity-100">
                    <button onClick={() => setForm(e)} className="rounded-md p-1.5 hover:bg-stone-100" aria-label="Edit"><Pencil className="size-4" /></button>
                    <button onClick={async () => { if (confirm(`Delete “${e.title}”?`)) { await del(`/knowledge/${e.id}/`); reload(true) } }} className="rounded-md p-1.5 text-red-600 hover:bg-red-50" aria-label="Delete"><Trash2 className="size-4" /></button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      </div>
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? 'Edit entry' : 'New knowledge entry'} wide
        footer={<><Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button><Button onClick={save} loading={busy} disabled={!form?.title?.trim() || !form?.content?.trim()}>Save</Button></>}>
        {form && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Select label="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} options={categories || []} />
              <Input label="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Opening hours" />
            </div>
            <Textarea label="Content" rows={6} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })}
              hint={form.category === 'custom' ? 'Custom instructions are added as owner instructions, not as facts.' : 'Be specific: exact prices, days, conditions.'} />
            <Input label="Keywords (optional)" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} hint="Words customers might use, to help retrieval." />
            <Toggle label="Active" checked={form.active} onChange={(v) => setForm({ ...form, active: v })} />
          </div>
        )}
      </Modal>
    </div>
  )
}
