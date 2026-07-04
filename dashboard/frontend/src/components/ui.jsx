/** Instrument-panel primitives: framed panels with registration ticks,
    segmented level meters, buttons, fields, typed-word confirmations. */

/** A framed panel. `label` renders as a bracketed instrument caption and the
    four corners get registration ticks — the schematic identity of the app. */
export function Panel({ label, meta, actions, children, className = '', tone = '' }) {
  return (
    <section className={`panel ${tone ? `panel-${tone}` : ''} ${className}`}>
      <span className="tick tick-tl" aria-hidden="true" />
      <span className="tick tick-tr" aria-hidden="true" />
      <span className="tick tick-bl" aria-hidden="true" />
      <span className="tick tick-br" aria-hidden="true" />
      {(label || actions || meta) && (
        <header className="panel-head">
          <div className="panel-head-l">
            {label && <span className="panel-label">[ {label} ]</span>}
            {meta && <span className="panel-meta">{meta}</span>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

// Card is an alias for Panel so existing tabs keep working with the new look.
export function Card({ eyebrow, title, actions, children, className = '' }) {
  const label = eyebrow || title
  const meta =
    eyebrow && title && eyebrow.toLowerCase() !== title.toLowerCase() ? title : undefined
  return (
    <Panel label={label} meta={meta} actions={actions} className={className}>
      {children}
    </Panel>
  )
}

export function Btn({ variant = 'default', busy = false, children, ...props }) {
  return (
    <button className={`btn btn-${variant}`} disabled={busy || props.disabled} {...props}>
      {busy ? <span className="spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  )
}

export function Badge({ tone = 'muted', children }) {
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-dot" aria-hidden="true" />
      {children}
    </span>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function Toggle({ label, checked, onChange, disabled }) {
  return (
    <label className={`toggle ${disabled ? 'is-disabled' : ''}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true" />
      <span>{label}</span>
    </label>
  )
}

/** Thin fill bar for inline use (table cells, disk usage). */
export function Bar({ percent, tone = 'accent' }) {
  return (
    <div className="bar">
      <div className={`bar-fill bar-${tone}`} style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
    </div>
  )
}

/** Segmented level meter — the signature readout. A row of cells lights up
    left-to-right proportional to the value, in the severity colour. */
export function SegMeter({ value, max = 100, tone = 'accent', segments = 28 }) {
  const lit = Math.round((Math.min(max, Math.max(0, value)) / max) * segments)
  return (
    <div className={`segmeter seg-${tone}`} role="meter" aria-valuenow={value} aria-valuemax={max}>
      {Array.from({ length: segments }, (_, i) => (
        <span key={i} className={`seg ${i < lit ? 'is-lit' : ''}`} />
      ))}
    </div>
  )
}

/** Typed-word confirmation for destructive actions. */
export function ConfirmWord({ word, value, onChange }) {
  return (
    <input
      className="input mono confirm-word"
      placeholder={`type ${word}`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoComplete="off"
      spellCheck="false"
    />
  )
}

export function severity(val, low, high) {
  if (val < low) return { tone: 'ok', label: 'nominal' }
  if (val < high) return { tone: 'warn', label: 'elevated' }
  return { tone: 'crit', label: 'critical' }
}

export function EmptyState({ children }) {
  return <div className="empty-state">{children}</div>
}
