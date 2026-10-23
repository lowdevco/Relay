// Frontend tests. The backend API is MOCKED via a fake fetch.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../components/ui'
import { errorMessage } from '../lib/api'
import AISettings from '../pages/AISettings'

vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ canManage: true }) }))

const providers = [
  { provider: 'gemini', label: 'Google Gemini', configured: true, model: 'gemini-3.8-flash', missing: [] },
  { provider: 'deepseek', label: 'DeepSeek', configured: true, model: 'deepseek-flash', missing: [] },
  { provider: 'grok', label: 'xAI Grok', configured: true, model: 'grok-4.20-0309-non-reasoning', missing: [] },
  { provider: 'groq', label: 'Groq', configured: true, model: 'openai/gpt-oss-120b', missing: [] },
]
const settings = (provider) => ({
  provider, fallback_enabled: false, fallback_provider: '',
  temperature: 0.4, max_reply_chars: 700, history_messages: 12, providers,
  active: providers.find((p) => p.provider === provider), last_generation: null,
})

function mockFetch(handler) {
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const { status = 200, body } = handler(url, opts)
    return { ok: status < 400, status, text: async () => JSON.stringify(body) }
  })
}

describe('errorMessage', () => {
  it('flattens DRF errors', () => {
    expect(errorMessage({ detail: 'Nope' })).toBe('Nope')
    expect(errorMessage({ provider: ['DeepSeek is not configured.'] })).toBe('provider: DeepSeek is not configured.')
  })
})

describe('AI provider selector', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=test-csrf'
  })

  it('sends the chosen provider to the backend and shows the persisted result', async () => {
    let current = 'gemini'
    const puts = []
    mockFetch((url, opts) => {
      if (url === '/api/ai/settings/' && opts.method === 'PUT') {
        const body = JSON.parse(opts.body)
        puts.push({ body, csrf: opts.headers['X-CSRFToken'] })
        current = body.provider
      }
      return { body: settings(current) }
    })
    render(<MemoryRouter><ToastProvider><AISettings /></ToastProvider></MemoryRouter>)
    const deepseek = await screen.findByRole('radio', { name: 'DeepSeek' })
    expect(screen.getByRole('radio', { name: 'Google Gemini' })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(deepseek)
    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0]).toEqual({ body: { provider: 'deepseek' }, csrf: 'test-csrf' })
    await waitFor(() => expect(screen.getByRole('radio', { name: 'DeepSeek' })).toHaveAttribute('aria-checked', 'true'))
  })

  it('can select Groq (free plan)', async () => {
    let current = 'gemini'
    const puts = []
    mockFetch((url, opts) => {
      if (opts.method === 'PUT') {
        puts.push(JSON.parse(opts.body))
        current = puts.at(-1).provider
      }
      return { body: settings(current) }
    })
    render(<MemoryRouter><ToastProvider><AISettings /></ToastProvider></MemoryRouter>)
    expect(await screen.findByText('Free plan available')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'Groq' }))
    await waitFor(() => expect(puts).toEqual([{ provider: 'groq' }]))
  })

  it('can select xAI Grok', async () => {
    let current = 'gemini'
    const puts = []
    mockFetch((url, opts) => {
      if (opts.method === 'PUT') {
        puts.push(JSON.parse(opts.body))
        current = puts.at(-1).provider
      }
      return { body: settings(current) }
    })
    render(<MemoryRouter><ToastProvider><AISettings /></ToastProvider></MemoryRouter>)
    fireEvent.click(await screen.findByRole('radio', { name: 'xAI Grok' }))
    await waitFor(() => expect(puts).toEqual([{ provider: 'grok' }]))
    await waitFor(() => expect(screen.getByRole('radio', { name: 'xAI Grok' })).toHaveAttribute('aria-checked', 'true'))
  })

  it('shows the server error and keeps the previous provider when switching fails', async () => {
    mockFetch((url, opts) =>
      opts.method === 'PUT'
        ? { status: 400, body: { provider: ['DeepSeek is not configured on the server (missing: DEEPSEEK_API_KEY).'] } }
        : { body: settings('gemini') },
    )
    render(<MemoryRouter><ToastProvider><AISettings /></ToastProvider></MemoryRouter>)
    fireEvent.click(await screen.findByRole('radio', { name: 'DeepSeek' }))
    expect(await screen.findByText(/missing: DEEPSEEK_API_KEY/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Google Gemini' })).toHaveAttribute('aria-checked', 'true')
  })
})
