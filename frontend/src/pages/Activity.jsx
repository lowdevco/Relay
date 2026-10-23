import { Activity as ActivityIcon } from 'lucide-react'
import { useState } from 'react'
import { Alert, Badge, Card, EmptyState, Loading, PageHeader, Segmented } from '../components/ui'
import { PROVIDER_LABEL, formatDateTime, useApi } from '../lib/hooks'

const KIND_COLOR = { ai_request: 'blue', ai_fallback: 'amber', voice_generation: 'violet', whatsapp_send: 'green', error: 'red' }

export default function Activity() {
  const [tab, setTab] = useState('audit')
  const { data, loading, error } = useApi('/activity/', { interval: 10000 })
  if (loading && !data) return <Loading />
  if (error) return <Alert tone="error">{error.message}</Alert>
  return (
    <div>
      <PageHeader title="Activity log" description="Who did what: team actions, automatic AI actions, provider usage and errors." />
      <Segmented className="mb-4" value={tab} onChange={setTab} options={[{ value: 'audit', label: 'Actions' }, { value: 'events', label: 'Usage & errors' }]} />
      <Card>
        {tab === 'audit' ? (
          data.audit.length === 0 ? <EmptyState icon={ActivityIcon} title="No actions yet" /> : (
            <ul className="divide-y divide-line">
              {data.audit.map((a) => (
                <li key={a.id} className="flex flex-col gap-1 px-5 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <Badge color={a.user.startsWith('system') ? 'green' : 'gray'}>{a.user}</Badge>{' '}
                    <span className="font-medium">{a.action}</span>
                    {a.target_type && <span className="text-stone-500"> · {a.target_type} #{a.target_id}</span>}
                    {Object.keys(a.details || {}).length > 0 && <p className="mt-1 font-mono text-[11px] text-stone-500">{JSON.stringify(a.details)}</p>}
                  </div>
                  <span className="shrink-0 text-xs text-stone-400">{formatDateTime(a.created_at)}</span>
                </li>
              ))}
            </ul>
          )
        ) : data.events.length === 0 ? <EmptyState icon={ActivityIcon} title="No usage yet" /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-xs uppercase tracking-wide text-stone-500">
                <tr><th className="px-5 py-2.5">Event</th><th className="px-3">Source</th><th className="px-3">Detail</th><th className="px-3">Latency</th><th className="px-5 text-right">When</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.events.map((e) => (
                  <tr key={e.id} className={e.success ? '' : 'bg-red-50/40'}>
                    <td className="px-5 py-2.5"><Badge color={e.success ? KIND_COLOR[e.kind] || 'gray' : 'red'}>{e.kind.replace('_', ' ')}</Badge></td>
                    <td className="px-3">{PROVIDER_LABEL[e.source] || e.source} {e.operation && <span className="text-stone-400">· {e.operation}</span>}</td>
                    <td className="max-w-md px-3 text-xs text-stone-600">
                      {e.model && <code className="mr-2">{e.model}</code>}
                      {e.input_tokens + e.output_tokens > 0 && <span className="mr-2">{e.input_tokens}+{e.output_tokens} tok</span>}
                      {e.characters > 0 && <span className="mr-2">{e.characters} chars</span>}
                      {e.error_code && <span className="font-mono text-red-700">{e.error_code} </span>}
                      {e.message}
                    </td>
                    <td className="px-3 text-xs tabular-nums text-stone-500">{e.latency_ms ? `${e.latency_ms} ms` : ''}</td>
                    <td className="whitespace-nowrap px-5 text-right text-xs text-stone-400">{formatDateTime(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
