import { useCallback, useEffect, useRef, useState } from 'react'
import { get } from './api'

/** Load JSON from the API. Optional polling interval (ms). */
export function useApi(path, { interval, enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(Boolean(path && enabled))
  const mounted = useRef(true)

  const load = useCallback(
    async (silent = false) => {
      if (!path || !enabled) return null
      if (!silent) setLoading(true)
      try {
        const result = await get(path)
        if (mounted.current) {
          setData(result)
          setError(null)
        }
        return result
      } catch (err) {
        if (mounted.current) setError(err)
        return null
      } finally {
        if (mounted.current) setLoading(false)
      }
    },
    [path, enabled],
  )

  useEffect(() => {
    mounted.current = true
    load()
    if (!interval) return () => (mounted.current = false)
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, interval)
    return () => {
      mounted.current = false
      clearInterval(id)
    }
  }, [load, interval])

  return { data, setData, error, loading, reload: load }
}

export function timeAgo(value) {
  if (!value) return ''
  const diff = (Date.now() - new Date(value).getTime()) / 1000
  if (diff < 45) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m`
  if (diff < 86400) return `${Math.round(diff / 3600)}h`
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)}d`
  return new Date(value).toLocaleDateString()
}

export function formatTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function formatDateTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export const PROVIDER_LABEL = { gemini: 'Google Gemini', deepseek: 'DeepSeek', groq: 'Groq' }
export const MODE_LABEL = { manual: 'Manual', approval: 'Approval', automatic: 'Automatic', off: 'Off' }
