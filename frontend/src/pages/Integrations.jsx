import { Bot, CheckCircle2, Copy, ExternalLink, MessageCircle, Mic, Plug, RefreshCw, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, CardHeader, Input, Loading, PageHeader, StatusDot, useToast } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { post, put } from '../lib/api'
import { formatDateTime, useApi } from '../lib/hooks'

function Check({ ok, label, hint }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      {ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-600" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-stone-300" />}
      <span>
        {label}
        {hint && <span className="block text-xs text-stone-500">{hint}</span>}
      </span>
    </li>
  )
}

function EmbeddedSignup({ env, onDone }) {
  // Meta Embedded Signup: loads Meta's JS SDK, gets a short-lived code, and the backend exchanges it.
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  if (!env.embedded_signup_available) return null
  async function launch() {
    setBusy(true)
    try {
      await new Promise((resolve, reject) => {
        if (window.FB) return resolve()
        const s = document.createElement('script')
        s.src = 'https://connect.facebook.net/en_US/sdk.js'
        s.async = true
        s.onload = resolve
        s.onerror = () => reject(new Error('Could not load the Meta SDK.'))
        document.body.appendChild(s)
      })
      window.FB.init({ appId: env.meta_app_id, autoLogAppEvents: true, xfbml: false, version: env.graph_version })
      let session = {}
      const listener = (event) => {
        if (!String(event.origin).endsWith('facebook.com')) return
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'WA_EMBEDDED_SIGNUP' && data.event === 'FINISH') session = data.data
        } catch { /* ignore non-JSON messages */ }
      }
      window.addEventListener('message', listener)
      window.FB.login(async (response) => {
        window.removeEventListener('message', listener)
        const code = response?.authResponse?.code
        if (!code || !session.phone_number_id) {
          toast('Embedded signup was cancelled or incomplete.', 'error')
          setBusy(false)
          return
        }
        try {
          await post('/whatsapp/embedded-signup/', { code, phone_number_id: session.phone_number_id, waba_id: session.waba_id })
          toast('WhatsApp connected.')
          onDone()
        } catch (err) {
          toast(err.message, 'error')
        } finally {
          setBusy(false)
        }
      }, { config_id: env.embedded_signup_config_id, response_type: 'code', override_default_response_type: true, extras: { setup: {}, sessionInfoVersion: '3' } })
    } catch (err) {
      toast(err.message, 'error')
      setBusy(false)
    }
  }
  return <Button variant="brand" icon={Plug} loading={busy} onClick={launch}>Connect with Meta (Embedded Signup)</Button>
}

export default function Integrations() {
  const { canManage } = useAuth()
  const toast = useToast()
  const { data, loading, error, reload } = useApi('/integrations/', { interval: 15000 })
  const [pid, setPid] = useState('')
  const [waba, setWaba] = useState('')
  const [busy, setBusy] = useState(null)

  useEffect(() => {
    if (!data) return
    setPid((p) => p || data.whatsapp.integration?.phone_number_id || data.whatsapp.env.env_phone_number_id || '')
    setWaba((w) => w || data.whatsapp.integration?.business_account_id || data.whatsapp.env.env_business_account_id || '')
  }, [data])

  if (loading && !data) return <Loading />
  if (error) return <Alert tone="error">{error.message}</Alert>
  const wa = data.whatsapp
  const env = wa.env
  const integ = wa.integration

  async function saveWa() {
    setBusy('save')
    try {
      const r = await put('/whatsapp/', { phone_number_id: pid.trim(), business_account_id: waba.trim() })
      toast(r.status === 'connected' ? 'WhatsApp number verified with Meta.' : r.integration?.last_validation_error || 'Saved. Credentials not verified yet.', r.status === 'connected' ? 'success' : 'error')
      reload(true)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(null)
    }
  }
  async function validate() {
    setBusy('validate')
    try {
      const r = await post('/whatsapp/validate/')
      toast(r.ok ? 'Credentials valid.' : `Validation failed: ${r.error}`, r.ok ? 'success' : 'error')
      reload(true)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <PageHeader title="Integrations" description="Connection status for WhatsApp, AI providers and ElevenLabs. Credentials live in backend/.env and are never shown here." />

      <Card className="mb-4">
        <CardHeader title="WhatsApp Business Platform (Cloud API)" icon={MessageCircle}
          action={<StatusDot ok={wa.status === 'connected'} warn={wa.status === 'pending' || wa.status === 'error'} label={<span className="capitalize">{wa.status.replace('_', ' ')}</span>} />} />
        <div className="grid gap-6 p-5 lg:grid-cols-2">
          <div className="space-y-4">
            {integ && (
              <dl className="grid grid-cols-2 gap-3 rounded-xl bg-stone-50 p-4 text-sm">
                <div><dt className="text-xs text-stone-500">Phone number</dt><dd className="font-medium">{integ.display_phone_number || '—'}</dd></div>
                <div><dt className="text-xs text-stone-500">Verified name</dt><dd className="font-medium">{integ.verified_name || '—'}</dd></div>
                <div><dt className="text-xs text-stone-500">Phone number ID</dt><dd className="font-mono text-xs">{integ.phone_number_id}</dd></div>
                <div><dt className="text-xs text-stone-500">Business account ID</dt><dd className="font-mono text-xs">{integ.business_account_id || '—'}</dd></div>
                <div><dt className="text-xs text-stone-500">Quality rating</dt><dd>{integ.quality_rating || '—'}</dd></div>
                <div><dt className="text-xs text-stone-500">Token source</dt><dd>{integ.token_source === 'env' ? '.env (server)' : integ.token_source === 'embedded_signup' ? 'Embedded Signup' : 'none'}</dd></div>
                <div><dt className="text-xs text-stone-500">Last validated</dt><dd>{formatDateTime(integ.last_validated_at)}</dd></div>
                <div><dt className="text-xs text-stone-500">Last webhook</dt><dd>{formatDateTime(integ.last_webhook_at)}</dd></div>
                <div className="col-span-2"><dt className="text-xs text-stone-500">Last message event</dt><dd>{formatDateTime(integ.last_message_event_at)}</dd></div>
              </dl>
            )}
            {integ?.last_validation_error && <Alert tone="error" title="Credential check failed">{integ.last_validation_error}</Alert>}
            <div className="grid gap-3 sm:grid-cols-2">
              <Input label="Phone number ID" value={pid} onChange={(e) => setPid(e.target.value.replace(/\D/g, ''))} hint="From Meta App → WhatsApp → API Setup" disabled={!canManage} />
              <Input label="WhatsApp Business Account ID" value={waba} onChange={(e) => setWaba(e.target.value.replace(/\D/g, ''))} disabled={!canManage} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={saveWa} loading={busy === 'save'} disabled={!canManage || pid.length < 5}>Save & verify</Button>
              <Button variant="secondary" icon={RefreshCw} onClick={validate} loading={busy === 'validate'} disabled={!canManage || !integ}>Re-check credentials</Button>
              <EmbeddedSignup env={env} onDone={() => reload(true)} />
            </div>
          </div>
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-sm font-medium">Server configuration</p>
              <ul className="space-y-2">
                <Check ok={env.access_token_configured || integ?.token_source === 'embedded_signup'} label="Access token" hint="WHATSAPP_ACCESS_TOKEN (system user token) or Embedded Signup" />
                <Check ok={env.verify_token_configured} label="Webhook verify token" hint="WHATSAPP_VERIFY_TOKEN" />
                <Check ok={env.app_secret_configured} label="App secret (signature verification)" hint="META_APP_SECRET — required to accept webhooks" />
                <Check ok={!!integ?.last_webhook_at} label="Webhook received" hint={integ?.last_webhook_at ? formatDateTime(integ.last_webhook_at) : 'No webhook received yet'} />
              </ul>
              {env.unsigned_webhooks_allowed && <Alert tone="warn" className="mt-3">Development mode: unsigned webhooks are accepted because META_APP_SECRET is empty. Never use this outside local development.</Alert>}
            </div>
            <div className="rounded-xl border border-line p-4 text-sm">
              <p className="font-medium">Meta-side setup</p>
              <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-stone-600">
                <li>Create a Meta app with the WhatsApp product and add a phone number.</li>
                <li>Expose this backend publicly (e.g. a tunnel) and set the callback URL:
                  <span className="mt-1 flex items-center gap-1">
                    <code className="rounded bg-stone-100 px-1.5 py-0.5 text-xs">{env.webhook_url}</code>
                    <button onClick={() => { navigator.clipboard.writeText(env.webhook_url); toast('Copied.') }} className="rounded p-1 hover:bg-stone-100" aria-label="Copy"><Copy className="size-3.5" /></button>
                  </span>
                </li>
                <li>Use the value of WHATSAPP_VERIFY_TOKEN as the verify token, then subscribe to the <b>messages</b> field.</li>
                <li>Put the app secret, a system-user access token and the phone number ID in <code>backend/.env</code>.</li>
              </ol>
              <a href="https://developers.facebook.com/docs/whatsapp/cloud-api/get-started" target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
                Cloud API docs <ExternalLink className="size-3.5" />
              </a>
            </div>
            {wa.recent_errors.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium">Recent errors</p>
                <ul className="space-y-1.5">
                  {wa.recent_errors.map((e, i) => (
                    <li key={i} className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800">
                      <span className="font-mono">{e.error_code}</span> · {e.message} <span className="text-red-600/60">· {formatDateTime(e.created_at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.providers.map((p) => (
          <Card key={p.provider}>
            <CardHeader title={p.label} icon={Bot} action={<Badge color={p.configured ? 'green' : 'red'}>{p.configured ? 'Configured' : 'Missing'}</Badge>} />
            <div className="space-y-1 p-5 text-sm">
              <p className="flex justify-between"><span className="text-stone-500">Model</span><code className="text-xs">{p.model || '—'}</code></p>
              {!p.configured && <p className="text-xs text-red-600">Set {p.missing.join(', ')} in backend/.env</p>}
            </div>
          </Card>
        ))}
        <Card>
          <CardHeader title="ElevenLabs" icon={Mic} action={<Badge color={data.elevenlabs.configured ? 'green' : 'gray'}>{data.elevenlabs.configured ? 'Configured' : 'Optional · not set'}</Badge>} />
          <div className="space-y-1 p-5 text-sm">
            <p className="flex justify-between"><span className="text-stone-500">Model</span><code className="text-xs">{data.elevenlabs.model}</code></p>
            <p className="flex justify-between"><span className="text-stone-500">Format</span><code className="text-xs">{data.elevenlabs.output_format}</code></p>
          </div>
        </Card>
      </div>
    </div>
  )
}
