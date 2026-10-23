
## Quick start (local)

Requirements: Python 3.12+ (tested on 3.15), Node 20+ (tested on 24).

```bash
# Backend
cd backend
python -m venv env
.venv/Scripts/activate          # Windows (Git Bash: source .venv/Scripts/activate)
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
cp .env.example .env            # then edit .env (see below). DJANGO_SECRET_KEY is required.
python manage.py migrate
python manage.py seed_demo      # optional: demo workspace, login demo / demo-pass-2026
python manage.py runserver 8000
```

```bash
# Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

Open http://localhost:5173 and sign in (or create a workspace).

### Background jobs

Slow work (AI calls, media download, voice generation) runs outside the webhook request.

| `JOBS_MODE` | Behaviour |
|---|---|
| `thread` (default) | Runs each job in a background thread right after the request. Good for local development. |
| `worker` | Only enqueues jobs. Run `python manage.py run_jobs` in another terminal. Survives restarts and retries with backoff. |
| `sync` | Runs inline (used by tests). |

---

## Configuration (`backend/.env`)

Every setting is read with `decouple.config()` in `backend/config/settings.py`. `backend/.env` is git-ignored;
`backend/.env.example` holds placeholders only.

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | **Required.** Startup fails clearly if missing. |
| `DEBUG`, `ALLOWED_HOSTS`, `TIME_ZONE` | Standard Django settings |
| `DATABASE_ENGINE` | `sqlite` (default) or `mysql` (`MYSQL_*` vars; `pip install mysqlclient`) |
| `AI_PROVIDER` | `gemini`, `deepseek`, `groq` or `grok`: the default for **new** workspaces. Validated at startup. |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_THINKING_LEVEL` | Default model `gemini-3.5-flash-lite` with `minimal` thinking (about 1 s per reply in live tests, Oct 2026). `gemini-3.8-flash` returned 503 "high demand" / 504 timeouts at the time. |
| `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL` | Default `deepseek-flash` at `https://api.deepseek.com` (checked against api-docs.deepseek.com) |
| `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL`, `GROQ_REASONING_EFFORT` | **Groq (GroqCloud), free plan available.** Default `openai/gpt-oss-120b` at `https://api.groq.com/openai/v1`, reasoning effort `low` (reasoning hidden, never stored). |
| `GROK_API_KEY` (or `XAI_API_KEY`), `GROK_MODEL`, `GROK_BASE_URL` | xAI Grok via the official API. Default `grok-4.20-0309-non-reasoning` (cheapest tier, $1.25 / $2.50 per 1M tokens, checked against docs.x.ai, Oct 2026) at `https://api.x.ai/v1`. **Paid per token; xAI has no free API tier.** |
| `AI_REQUEST_TIMEOUT`, `AI_MAX_RETRIES` | Timeout in seconds (default 60); bounded retries for invalid output or transient errors (503/429 retried after a short backoff or the server's `retry-after`, up to 20 s) |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_DEFAULT_MODEL`, `ELEVENLABS_OUTPUT_FORMAT` | Optional voice notes. Default `eleven_multilingual_v2`, `opus_48000_64` (Ogg/Opus) |
| `WHATSAPP_ACCESS_TOKEN` | System-user token for the Cloud API |
| `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID` | Pre-fill for the Integrations page |
| `WHATSAPP_VERIFY_TOKEN` | Your chosen webhook verify token |
| `META_APP_SECRET` | Used to verify `X-Hub-Signature-256` on webhooks. Webhooks are rejected without it. |
| `META_APP_ID`, `META_EMBEDDED_SIGNUP_CONFIG_ID` | Optional: enables the Embedded Signup button |
| `WHATSAPP_GRAPH_VERSION` | Default `v26.0` |
| `WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS` | DEV ONLY: accept unsigned webhooks when `META_APP_SECRET` is empty. Refused unless `DEBUG=True`. |

Keys are never returned by the API, never sent to the frontend and redacted from logs.

### AI provider selection

- **AI provider** page: pick Google Gemini, DeepSeek, Groq or xAI Grok. The choice is stored per workspace (`AISettings.provider`),
  validated server-side (the provider must be configured), optionally connection-tested before saving, and
  used for every subsequent AI operation (reply, classify, summarize, evaluate, style profile).
- Provider-specific code lives in `backend/apps/ai/providers/{gemini,deepseek,groq,grok}.py` behind a shared interface (`base.py`); DeepSeek, Groq and Grok share the
  OpenAI-compatible adapter in `openai_compat.py`.
- **No silent switching.** Automatic fallback is a separate opt-in toggle, off by default. When used, it is logged
  (`ai_fallback` usage event + warning log) and shown on the message and draft.
  You choose the fallback provider explicitly (any configured provider other than the selected one).

### Using Groq (free)

Groq is an AI inference company (GroqCloud), not to be confused with xAI's Grok. Its official API has a **free plan**:
no card is needed, but requests are rate limited per model (about 30 requests/min, 1,000 requests/day, 8,000 tokens/min
and 200,000 tokens/day for `openai/gpt-oss-120b`, Oct 2026; see https://console.groq.com/settings/limits).

1. Sign in at https://console.groq.com and create an API key under **API Keys**.
2. Set `GROQ_API_KEY` in `backend/.env`, then restart the backend.
3. Select **Groq** on the AI provider page and click **Test connection**.

Each WhatsApp reply uses roughly 1.5-2K tokens (reply + quality check in automatic mode), so the free plan handles
about 4-5 replies per minute and a few hundred per day. When a limit is hit, short waits are retried automatically;
longer ones (for example the daily cap) fail fast, and the message is queued for your review. Nothing is sent
unchecked. Enable **Automatic fallback** to Gemini if you expect bursts above the free limits.

### Using Grok (xAI)

xAI does **not** offer a free Grok API; every request is billed to your xAI account. "Free Grok" tools found online
work by scraping grok.com or reusing logged-in browser sessions, which breaks xAI's terms and gets accounts blocked,
so this project does not support them.

1. Create an API key at https://console.x.ai and add billing credits.
2. Set `GROK_API_KEY` in `backend/.env` (optionally change `GROK_MODEL`), then restart the backend.
3. Select **xAI Grok** on the AI provider page. Use **Test connection** to confirm the key works.

To keep costs low: the default non-reasoning model is in xAI's cheapest tier; lower **Max reply chars** and
**History messages** on the AI provider page to shrink each request. To route Grok through OpenRouter instead, set
`GROK_BASE_URL=https://openrouter.ai/api/v1`, `GROK_MODEL=x-ai/grok-4.3` and `GROK_API_KEY=<your OpenRouter key>`.

---

## Connecting WhatsApp (Meta-side steps)

1. Create a Meta app with the **WhatsApp** product and add or verify a business phone number.
2. Create a **system user** access token with `whatsapp_business_messaging` and `whatsapp_business_management`
   permissions. Put it in `WHATSAPP_ACCESS_TOKEN`.
3. Copy the app secret into `META_APP_SECRET` and choose a `WHATSAPP_VERIFY_TOKEN`.
4. Expose the local backend over HTTPS (for example `cloudflared tunnel --url http://localhost:8000` or `ngrok http 8000`)
   and set `BACKEND_PUBLIC_URL` plus `ALLOWED_HOSTS` accordingly.
5. In the Meta app, go to **WhatsApp → Configuration → Webhook**: callback URL `https://<public-host>/api/webhooks/whatsapp/`,
   verify token = `WHATSAPP_VERIFY_TOKEN`. Subscribe to the **messages** field.
6. Restart the backend. On **Integrations**, enter the phone number ID and click **Save & verify**. The backend
   calls the Graph API to validate the credentials.
7. Optional: Embedded Signup. Set `META_APP_ID`, `META_APP_SECRET` and `META_EMBEDDED_SIGNUP_CONFIG_ID` (from Facebook Login for
   Business). The browser receives only a short-lived code; the backend exchanges it and stores the token server-side.

WhatsApp rules enforced by the backend: free-form replies only inside the 24-hour customer-service window
(otherwise only approved templates can be sent from the inbox), idempotent sends, and delivery or read status tracking.

### Developing without Meta credentials

With `DEBUG=True` the inbox shows a **Simulate message** button (development tool). It injects a webhook-shaped
event through the real ingestion and AI pipeline. It is clearly labelled, does not touch the webhook health
indicators, and outgoing replies still use the real Cloud API, so they fail visibly when credentials are missing.

---

## How a message is processed

1. `POST /api/webhooks/whatsapp/` verifies the HMAC signature, deduplicates by body hash, stores the contact,
   conversation and message (unique per `wamid`), and acknowledges immediately.
2. A background job (`automation.process_inbound`, deduplicated per message) runs the pipeline in `apps/automation/pipeline.py`:
   - effective mode = workspace mode + per-chat override, paused or human-takeover state (enforced server-side)
   - context: recent history, running summary, customer notes, keyword-retrieved knowledge, 2–3 relevant authorized examples
   - versioned prompt (`apps/ai/prompts.py`); untrusted text is wrapped in `<untrusted_*>` tags and neutralised
   - structured JSON output validated (`apps/ai/schema.py`), with one bounded retry
   - deterministic rules (`apps/automation/rules.py`): confidence threshold, numbers not found in the knowledge base,
     commitment phrases, sensitive intents, review topics, escalation keywords, instruction-leak detection,
     24h window, operating hours, rate limit, stale messages
   - automatic mode adds a second AI quality check (`evaluate_reply`) before sending
   - a send is atomically "claimed" against the conversation's `state_version`, so a human takeover or reply always wins
3. Result: auto-sent (`ai_auto`), queued draft (`pending`), manual suggestion (`suggestion`), or escalation (`needs_attention`).
4. Delivery status webhooks update messages; failures are flagged in the inbox.

No chain-of-thought is requested or stored; only the structured output and a one-line rationale.

---

## Tests

```bash
cd backend && .venv/Scripts/python manage.py test tests     # 100 tests
cd frontend && npm test && npm run build
```

All external APIs (Gemini, DeepSeek, Groq, Grok, WhatsApp Graph API, ElevenLabs) are **mocked** in the test suites. Passing tests
show that the application logic, request formatting and safety rules are correct. They do **not** prove that live credentials work.

---

## Implementation checklist

- [x] Django + DRF backend, python-decouple settings, `.env.example`, `.env` git-ignored
- [x] SQLite locally, MySQL supported through config
- [x] Session auth + CSRF, workspaces, memberships (owner/admin/agent), per-workspace isolation
- [x] WhatsApp webhook: verification challenge, HMAC signature check, idempotent ingestion, statuses, media download
- [x] Outgoing text, template, and audio/voice messages via Cloud API; 24h window; error mapping; retry; duplicate-send prevention
- [x] Shared provider interface; Gemini (google-genai SDK), DeepSeek, Groq and xAI Grok (REST) adapters; selector persisted per workspace
- [x] Opt-in fallback (off by default) with logging; connection tests; usage and generation records
- [x] Knowledge base CRUD + keyword retrieval; persona; few-shot examples; style-profile generation; live preview
- [x] Structured output validation; factual, commitment and injection guardrails; escalation
- [x] Manual / approval / automatic modes; per-chat overrides; pause; takeover/resume; concurrency guard
- [x] ElevenLabs: voice list, consent gate for cloned voices, Ogg/Opus detection, upload + voice-note send, text fallback
- [x] Dashboard, inbox, AI provider, personalization, knowledge, automation, voice, integrations, activity pages
- [x] Backend tests (88) + frontend tests; Django check; production build
- [ ] **Live verification with real DeepSeek / Groq / Grok / Meta / ElevenLabs credentials (Gemini verified live).** Blocked: no credentials available in this environment.
- [ ] Inbound voice-message transcription (currently flagged for human review)
- [ ] Encryption at rest for Embedded Signup tokens (currently stored server-side in plaintext in the database)
