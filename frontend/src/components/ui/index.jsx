import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useId, useState } from 'react'

export function cx(...parts) {
  return parts.filter(Boolean).join(' ')
}

/* ---------- Buttons ---------- */
const BTN = {
  primary: 'bg-ink-900 text-white hover:bg-ink-800 shadow-sm',
  brand: 'bg-brand-600 text-white hover:bg-brand-700 shadow-sm',
  secondary: 'bg-white text-ink-900 border border-line hover:bg-stone-50 shadow-sm',
  ghost: 'text-ink-700 hover:bg-ink-900/5',
  danger: 'bg-white text-red-700 border border-red-200 hover:bg-red-50',
}
const SIZE = { sm: 'h-8 px-3 text-xs gap-1.5', md: 'h-9 px-3.5 text-sm gap-2', lg: 'h-11 px-5 text-sm gap-2' }

export function Button({ variant = 'primary', size = 'md', loading, icon: Icon, className, children, disabled, ...props }) {
  return (
    <button
      className={cx(
        'inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        BTN[variant],
        SIZE[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : Icon ? <Icon className="size-4" /> : null}
      {children}
    </button>
  )
}

/* ---------- Layout primitives ---------- */
export function Card({ className, children, ...props }) {
  return (
    <div className={cx('rounded-xl2 border border-line bg-white shadow-card', className)} {...props}>
      {children}
    </div>
  )
}

export function CardHeader({ title, description, action, icon: Icon }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div className="flex items-start gap-3">
        {Icon && (
          <div className="mt-0.5 rounded-lg bg-brand-50 p-2 text-brand-700">
            <Icon className="size-4" />
          </div>
        )}
        <div>
          <h3 className="font-display text-[15px] font-semibold text-ink-900">{title}</h3>
          {description && <p className="mt-0.5 text-sm text-stone-500">{description}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function PageHeader({ title, description, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-stone-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

/* ---------- Status ---------- */
const BADGE = {
  gray: 'bg-stone-100 text-stone-700 ring-stone-200',
  green: 'bg-brand-50 text-brand-700 ring-brand-200',
  amber: 'bg-amber-50 text-amber-800 ring-amber-200',
  red: 'bg-red-50 text-red-700 ring-red-200',
  blue: 'bg-sky-50 text-sky-700 ring-sky-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  dark: 'bg-ink-900 text-white ring-ink-900',
}

export function Badge({ color = 'gray', className, children, icon: Icon }) {
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset', BADGE[color], className)}>
      {Icon && <Icon className="size-3" />}
      {children}
    </span>
  )
}

export function StatusDot({ ok, warn, label }) {
  const color = ok ? 'bg-brand-500' : warn ? 'bg-amber-400' : 'bg-stone-300'
  return (
    <span className="inline-flex items-center gap-2 text-sm">
      <span className="relative flex size-2.5">
        {ok && <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-400 opacity-40" />}
        <span className={cx('relative inline-flex size-2.5 rounded-full', color)} />
      </span>
      {label}
    </span>
  )
}

export function Spinner({ className }) {
  return <Loader2 className={cx('size-5 animate-spin text-stone-400', className)} />
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-stone-500">
      <Spinner /> {label}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {Icon && (
        <div className="mb-3 rounded-2xl bg-stone-100 p-3 text-stone-500">
          <Icon className="size-6" />
        </div>
      )}
      <p className="font-medium text-ink-900">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-stone-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

const ALERT = {
  info: ['bg-sky-50 border-sky-200 text-sky-900', Info],
  warn: ['bg-amber-50 border-amber-200 text-amber-900', AlertTriangle],
  error: ['bg-red-50 border-red-200 text-red-900', XCircle],
  success: ['bg-brand-50 border-brand-200 text-brand-800', CheckCircle2],
}

export function Alert({ tone = 'info', title, children, className }) {
  const [cls, Icon] = ALERT[tone]
  return (
    <div className={cx('flex gap-3 rounded-xl border px-4 py-3 text-sm', cls, className)} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cx(title && 'mt-0.5', 'opacity-90')}>{children}</div>}
      </div>
    </div>
  )
}

/* ---------- Form controls ---------- */
const FIELD = 'w-full rounded-lg border border-line bg-white px-3 text-sm text-ink-900 placeholder:text-stone-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:bg-stone-50'

export function Field({ label, hint, error, children, htmlFor }) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={htmlFor} className="block text-sm font-medium text-ink-800">
          {label}
        </label>
      )}
      {children}
      {error ? <p className="text-xs text-red-600">{error}</p> : hint ? <p className="text-xs text-stone-500">{hint}</p> : null}
    </div>
  )
}

export function Input({ label, hint, error, className, id, ...props }) {
  const auto = useId()
  const fid = id || auto
  return (
    <Field label={label} hint={hint} error={error} htmlFor={fid}>
      <input id={fid} className={cx(FIELD, 'h-9', className)} {...props} />
    </Field>
  )
}

export function Textarea({ label, hint, error, className, id, rows = 3, ...props }) {
  const auto = useId()
  const fid = id || auto
  return (
    <Field label={label} hint={hint} error={error} htmlFor={fid}>
      <textarea id={fid} rows={rows} className={cx(FIELD, 'py-2 leading-relaxed', className)} {...props} />
    </Field>
  )
}

export function Select({ label, hint, options, className, id, ...props }) {
  const auto = useId()
  const fid = id || auto
  return (
    <Field label={label} hint={hint} htmlFor={fid}>
      <select id={fid} className={cx(FIELD, 'h-9 pr-8', className)} {...props}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  )
}

export function Toggle({ checked, onChange, label, description, disabled }) {
  const id = useId()
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <label htmlFor={id} className="text-sm font-medium text-ink-800">
          {label}
        </label>
        {description && <p className="mt-0.5 text-xs text-stone-500">{description}</p>}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50',
          checked ? 'bg-brand-600' : 'bg-stone-300',
        )}
      >
        <motion.span layout transition={{ type: 'spring', stiffness: 500, damping: 32 }}
          className={cx('inline-block size-5 rounded-full bg-white shadow', checked ? 'ml-[22px]' : 'ml-0.5')} />
      </button>
    </div>
  )
}

export function Scale({ label, value, onChange, min = 1, max = 5, left, right }) {
  const id = useId()
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-sm font-medium text-ink-800">{label}</label>
        <span className="rounded-md bg-stone-100 px-1.5 text-xs font-semibold tabular-nums text-ink-800">{value}</span>
      </div>
      <input id={id} type="range" min={min} max={max} step={1} value={value}
        onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-brand-600" />
      {(left || right) && (
        <div className="flex justify-between text-[11px] text-stone-400"><span>{left}</span><span>{right}</span></div>
      )}
    </div>
  )
}

export function Segmented({ value, onChange, options, className }) {
  return (
    <div className={cx('inline-flex rounded-lg bg-stone-100 p-0.5', className)} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            'relative rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
            value === o.value ? 'text-ink-900' : 'text-stone-500 hover:text-ink-800',
          )}
        >
          {value === o.value && (
            <motion.span layoutId={`seg-${options.map((x) => x.value).join('')}`} className="absolute inset-0 rounded-md bg-white shadow-sm"
              transition={{ type: 'spring', stiffness: 500, damping: 35 }} />
          )}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  )
}

/* ---------- Modal ---------- */
export function Modal({ open, onClose, title, children, footer, wide }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-ink-950/40 backdrop-blur-[2px]" onClick={onClose} />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 400, damping: 34 }}
            className={cx('relative max-h-[90vh] w-full overflow-auto rounded-t-2xl bg-white shadow-pop sm:rounded-2xl', wide ? 'sm:max-w-2xl' : 'sm:max-w-lg')}
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <h3 className="font-display font-semibold">{title}</h3>
              <button onClick={onClose} className="rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-ink-800" aria-label="Close">
                <X className="size-4" />
              </button>
            </div>
            <div className="px-5 py-4">{children}</div>
            {footer && <div className="flex justify-end gap-2 border-t border-line bg-stone-50/60 px-5 py-3">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/* ---------- Toasts ---------- */
const ToastContext = createContext(() => {})

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const push = useCallback((message, tone = 'success') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, message, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'error' ? 7000 : 3500)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(92vw,380px)] flex-col gap-2">
        <AnimatePresence>
          {toasts.map((t) => {
            const [cls, Icon] = ALERT[t.tone] || ALERT.info
            return (
              <motion.div key={t.id} layout initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 40 }}
                className={cx('pointer-events-auto flex items-start gap-2 rounded-xl border px-4 py-3 text-sm shadow-pop', cls)}>
                <Icon className="mt-0.5 size-4 shrink-0" />
                <span>{t.message}</span>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
