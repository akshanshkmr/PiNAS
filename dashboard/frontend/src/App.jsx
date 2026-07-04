import { useEffect, useState } from 'react'
import { api } from './api'
import { ToastHost } from './toast'
import { SegMeter, severity } from './components/ui'
import Login from './components/Login'
import SystemTab from './components/SystemTab'
import NasTab from './components/NasTab'
import FilesTab from './components/FilesTab'
import ServicesTab from './components/ServicesTab'
import TerminalTab from './components/TerminalTab'
import ControlsTab from './components/ControlsTab'

const TABS = [
  { id: 'system', label: 'System', glyph: '▚', component: SystemTab },
  { id: 'nas', label: 'Storage', glyph: '▛', component: NasTab },
  { id: 'files', label: 'Files', glyph: '▤', component: FilesTab },
  { id: 'services', label: 'Services', glyph: '◉', component: ServicesTab },
  { id: 'terminal', label: 'Terminal', glyph: '▮', component: TerminalTab },
  { id: 'controls', label: 'Controls', glyph: '◈', component: ControlsTab },
]

function greeting() {
  const h = new Date().getHours()
  if (h < 5) return 'Up late'
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  if (h < 21) return 'Good evening'
  return 'Good night'
}

function titleCase(s) {
  return s.replace(/\b\w/g, (c) => c.toUpperCase())
}

function Sidebar({ user, tab, setTab, online, onLogout }) {
  const firstName = titleCase((user.name || user.username).split(' ')[0])
  return (
    <aside className="chassis">
      <div className="chassis-brand">
        <span className={`power-led ${online ? 'is-on' : 'is-off'}`} aria-hidden="true" />
        <div>
          <div className="brand-name">PI·ADMIN</div>
          <div className="brand-sub mono">pironman 5</div>
        </div>
      </div>

      <nav className="chassis-nav" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`navitem ${tab === t.id ? 'is-active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className="navitem-glyph" aria-hidden="true">
              {t.glyph}
            </span>
            {t.label}
          </button>
        ))}
      </nav>

      <div className="chassis-foot">
        <div className="foot-user">
          <span className="foot-greet">{greeting()},</span>
          <span className="foot-name">{firstName}</span>
        </div>
        <button className="btn btn-ghost btn-block" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </aside>
  )
}

/** Always-on vitals across the top of the main area — the signature readout. */
function TelemetryRail({ stats, stale }) {
  const cells = stats
    ? [
        { key: 'cpu', label: 'cpu load', value: stats.cpu, unit: '%', max: 100, low: 30, high: 80 },
        { key: 'ram', label: 'memory', value: stats.ram, unit: '%', max: 100, low: 30, high: 80 },
        { key: 'temp', label: 'soc temp', value: stats.cpu_temp, unit: '°', max: 90, low: 55, high: 75 },
        { key: 'disk', label: 'disk', value: stats.disk.percent, unit: '%', max: 100, low: 70, high: 90 },
      ]
    : []

  return (
    <div className={`rail ${stale ? 'is-stale' : ''}`}>
      {stats ? (
        <>
          {cells.map((c) => {
            const sev = severity(c.value, c.low, c.high)
            return (
              <div className="rail-cell" key={c.key}>
                <div className="rail-top">
                  <span className="rail-label">{c.label}</span>
                  <span className={`rail-value mono tone-${sev.tone}`}>
                    {c.value.toFixed(1)}
                    <span className="rail-unit">{c.unit}</span>
                  </span>
                </div>
                <SegMeter value={c.value} max={c.max} tone={sev.tone} />
              </div>
            )
          })}
          <div className="rail-cell rail-host">
            <div className="rail-top">
              <span className="rail-label">host</span>
              <span className="rail-value-sm mono">{stats.hostname}</span>
            </div>
            <div className="rail-hostline mono">
              <span>{stats.ip}</span>
              <span className="dot-sep">·</span>
              <span>up {stats.uptime}</span>
            </div>
          </div>
        </>
      ) : (
        <div className="rail-boot mono">reading telemetry…</div>
      )}
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(undefined) // undefined = checking, null = logged out
  const [tab, setTab] = useState('system')
  const [stats, setStats] = useState(null)
  const [stale, setStale] = useState(false)

  useEffect(() => {
    api('/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
  }, [])

  useEffect(() => {
    const expire = () => setUser(null)
    window.addEventListener('auth-expired', expire)
    return () => window.removeEventListener('auth-expired', expire)
  }, [])

  // Live telemetry over Server-Sent Events, shared by the rail + System tab.
  // EventSource reconnects on its own after a drop; we only surface the state.
  useEffect(() => {
    if (!user) return
    const es = new EventSource('/status/api/system/stream', { withCredentials: true })
    es.onmessage = (e) => {
      try {
        setStats(JSON.parse(e.data))
        setStale(false)
      } catch {
        /* ignore malformed frame */
      }
    }
    es.onerror = () => {
      setStale(true)
      // A dropped stream can mean the session expired; probe to route to login.
      api('/auth/me').catch(() => {})
    }
    return () => es.close()
  }, [user])

  async function logout() {
    try {
      await api('/auth/logout', { method: 'POST' })
    } finally {
      setStats(null)
      setUser(null)
    }
  }

  if (user === undefined) {
    return <div className="boot-screen mono">pi-admin :: establishing session…</div>
  }
  if (user === null) {
    return (
      <>
        <Login onLogin={setUser} />
        <ToastHost />
      </>
    )
  }

  const Active = TABS.find((t) => t.id === tab).component
  const activeLabel = TABS.find((t) => t.id === tab).label

  return (
    <div className="app">
      <Sidebar user={user} tab={tab} setTab={setTab} online={!stale && !!stats} onLogout={logout} />
      <div className="workspace">
        <TelemetryRail stats={stats} stale={stale} />
        <main className="panel-area" key={tab}>
          <div className="area-head">
            <h1 className="area-title">{activeLabel}</h1>
            {stale && <span className="stale-flag mono">signal lost · retrying</span>}
          </div>
          <Active stats={stats} />
        </main>
      </div>
      <ToastHost />
    </div>
  )
}
