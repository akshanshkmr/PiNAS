import { useEffect, useState } from 'react'
import { api } from '../api'

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
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <span className="tick tick-tl" aria-hidden="true" />
        <span className="tick tick-tr" aria-hidden="true" />
        <span className="tick tick-bl" aria-hidden="true" />
        <span className="tick tick-br" aria-hidden="true" />
        <div className="login-led">pironman 5 · online</div>
        <h1 className="login-title">PI·NAS</h1>
        <p className="login-sub">Sign in with your Linux account.</p>

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

        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
