import { useEffect, useState } from 'react'
import { api } from '../api'

function AmbientMeter({ tone, label, value, delay }) {
  return (
    <div className="ambient-row">
      <span className="ambient-label">{label}</span>
      <div className="ambient-track" aria-hidden="true">
        <span
          className={`ambient-fill ambient-${tone}`}
          style={{ animationDelay: `${delay}s`, width: `${value}%` }}
        />
      </div>
      <span className="ambient-value mono">{value.toFixed(0)}<span className="ambient-unit">%</span></span>
    </div>
  )
}

export default function Login({ onLogin }) {
  const [users, setUsers] = useState([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/auth/users')
      .then((d) => {
        setUsers(d.users)
        if (d.users.length) setUsername(d.users[0])
      })
      .catch(() => {})
  }, [])

  async function submit(e) {
    e.preventDefault()
    if (!username || !password) {
      setError('Enter both username and password.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const user = await api('/auth/login', { method: 'POST', body: { username, password } })
      onLogin(user)
    } catch (err) {
      setError(err.status === 401 ? 'Invalid username or password.' : err.detail)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-shell">
      {/* corner registration ticks frame the whole viewport */}
      <span className="viewport-tick vt-tl" aria-hidden="true" />
      <span className="viewport-tick vt-tr" aria-hidden="true" />
      <span className="viewport-tick vt-bl" aria-hidden="true" />
      <span className="viewport-tick vt-br" aria-hidden="true" />

      <div className="login-stage">
        <div className="login-led">
          <span className="login-led-dot" aria-hidden="true" />
          pironman 5 · online
        </div>

        <h1 className="login-brand">PI·NAS</h1>

        <p className="login-lead">
          Live telemetry, RAID &amp; Samba, a file explorer, an in-browser
          terminal, and case controls — behind one clean instrument-panel UI.
        </p>

        <div className="ambient-panel" aria-hidden="true">
          <div className="ambient-title mono">[ IDLE TELEMETRY ]</div>
          <AmbientMeter tone="ok" label="cpu"    value={12} delay={0} />
          <AmbientMeter tone="warn" label="memory" value={38} delay={0.7} />
          <AmbientMeter tone="ok" label="soc temp" value={44} delay={1.4} />
          <AmbientMeter tone="ok" label="disk"   value={62} delay={2.1} />
          <div className="ambient-footer mono">
            <span>bash · ready</span>
            <span className="dot-sep">·</span>
            <span>samba · standby</span>
            <span className="dot-sep">·</span>
            <span>tailscale · linked</span>
          </div>
        </div>
      </div>

      <form className="login-card" onSubmit={submit}>
        <span className="tick tick-tl" aria-hidden="true" />
        <span className="tick tick-tr" aria-hidden="true" />
        <span className="tick tick-bl" aria-hidden="true" />
        <span className="tick tick-br" aria-hidden="true" />

        <div className="login-eyebrow mono">[ AUTHENTICATION ]</div>
        <h2 className="login-title">Sign in</h2>
        <p className="login-sub">Use your Linux account credentials.</p>

        <label className="field">
          <span className="field-label">Username</span>
          {users.length ? (
            <select className="input" value={username} onChange={(e) => setUsername(e.target.value)}>
              {users.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          )}
        </label>

        <label className="field">
          <span className="field-label">Password</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>

        {error && <div className="form-error">{error}</div>}

        <button className="btn btn-primary btn-block login-submit" type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in →'}
        </button>

        <p className="login-hint mono">local network · not exposed to the internet</p>
      </form>
    </div>
  )
}
