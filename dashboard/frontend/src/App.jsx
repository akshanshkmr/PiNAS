import { useEffect, useState } from 'react'
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom'
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
  { id: 'system', label: 'System', path: '/system', component: SystemTab },
  { id: 'nas', label: 'Storage', path: '/storage', component: NasTab },
  { id: 'files', label: 'Files', path: '/files', component: FilesTab },
  { id: 'services', label: 'Services', path: '/services', component: ServicesTab },
  { id: 'terminal', label: 'Terminal', path: '/terminal', component: TerminalTab },
  { id: 'controls', label: 'Controls', path: '/controls', component: ControlsTab },
]

function TabIcon({ id }) {
  const p = {
    viewBox: '0 0 16 16',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  }
  switch (id) {
    case 'system': // activity / telemetry pulse
      return (
        <svg {...p}>
          <polyline points="1 9 4.5 9 6.5 3.5 9.5 12.5 11.5 8 15 8" />
        </svg>
      )
    case 'nas': // stacked disks
      return (
        <svg {...p}>
          <ellipse cx="8" cy="3.8" rx="5.2" ry="2" />
          <path d="M2.8 3.8v8.4c0 1.1 2.3 2 5.2 2s5.2-.9 5.2-2V3.8" />
          <path d="M2.8 8c0 1.1 2.3 2 5.2 2s5.2-.9 5.2-2" />
        </svg>
      )
    case 'files': // folder
      return (
        <svg {...p}>
          <path d="M1.8 4.3a1 1 0 0 1 1-1h3.1l1.4 1.5h6.4a1 1 0 0 1 1 1v6.4a1 1 0 0 1-1 1H2.8a1 1 0 0 1-1-1z" />
        </svg>
      )
    case 'services': // stacked servers with status LEDs
      return (
        <svg {...p}>
          <rect x="2" y="2.6" width="12" height="4.6" rx="1" />
          <rect x="2" y="8.8" width="12" height="4.6" rx="1" />
          <line x1="4.4" y1="4.9" x2="4.5" y2="4.9" />
          <line x1="4.4" y1="11.1" x2="4.5" y2="11.1" />
        </svg>
      )
    case 'terminal': // prompt
      return (
        <svg {...p}>
          <rect x="1.6" y="2.6" width="12.8" height="10.8" rx="1.6" />
          <polyline points="4.4 6.2 6.6 8 4.4 9.8" />
          <line x1="8" y1="10.2" x2="11.2" y2="10.2" />
        </svg>
      )
    case 'controls': // equalizer sliders
      return (
        <svg {...p}>
          <line x1="4" y1="2.5" x2="4" y2="13.5" />
          <line x1="8" y1="2.5" x2="8" y2="13.5" />
          <line x1="12" y1="2.5" x2="12" y2="13.5" />
          <circle cx="4" cy="5.4" r="1.7" fill="currentColor" stroke="none" />
          <circle cx="8" cy="9.8" r="1.7" fill="currentColor" stroke="none" />
          <circle cx="12" cy="6.6" r="1.7" fill="currentColor" stroke="none" />
        </svg>
      )
    default:
      return null
  }
}

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

function Sidebar({ user, online, onLogout }) {
  const firstName = titleCase((user.name || user.username).split(' ')[0])
  return (
    <aside className="chassis">
      <NavLink to="/system" className="chassis-brand">
        <span className={`power-led ${online ? 'is-on' : 'is-off'}`} aria-hidden="true" />
        <div>
          <div className="brand-name">PI·NAS</div>
          <div className="brand-sub mono">pironman 5</div>
        </div>
      </NavLink>

      <nav className="chassis-nav">
        {TABS.map((t) => (
          <NavLink
            key={t.id}
            to={t.path}
            className={({ isActive }) => `navitem ${isActive ? 'is-active' : ''}`}
          >
            <span className="navitem-glyph" aria-hidden="true">
              <TabIcon id={t.id} />
            </span>
            {t.label}
          </NavLink>
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

function Workspace({ user, stats, stale, onLogout }) {
  const loc = useLocation()
  const active = TABS.find((t) => t.path === loc.pathname) || TABS[0]
  return (
    <div className="app">
      <Sidebar user={user} online={!stale && !!stats} onLogout={onLogout} />
      <div className="workspace">
        <TelemetryRail stats={stats} stale={stale} />
        <main className="panel-area" key={loc.pathname}>
          <div className="area-head">
            <h1 className="area-title">{active.label}</h1>
            {stale && <span className="stale-flag mono">signal lost · retrying</span>}
          </div>
          <Routes>
            {TABS.map(({ id, path, component: C }) => (
              <Route key={id} path={path} element={<C stats={stats} />} />
            ))}
            <Route path="*" element={<Navigate to="/system" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(undefined) // undefined = checking, null = logged out
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
    const es = new EventSource('/api/system/stream', { withCredentials: true })
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
    return <div className="boot-screen mono">pi-nas :: establishing session…</div>
  }
  if (user === null) {
    return (
      <>
        <Login onLogin={setUser} />
        <ToastHost />
      </>
    )
  }

  return (
    <BrowserRouter>
      <Workspace user={user} stats={stats} stale={stale} onLogout={logout} />
      <ToastHost />
    </BrowserRouter>
  )
}
