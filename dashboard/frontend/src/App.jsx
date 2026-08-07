import { useEffect, useRef, useState } from 'react'
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom'
import { api, copyText } from './api'
import { toast } from './toast'
import { ToastHost } from './toast'
import { SegMeter, severity } from './components/ui'
import Login from './components/Login'
import SystemTab from './components/SystemTab'
import NasTab from './components/NasTab'
import FilesTab from './components/FilesTab'
import NetworkTab from './components/NetworkTab'
import ServicesTab from './components/ServicesTab'
import TerminalTab from './components/TerminalTab'
import ControlsTab from './components/ControlsTab'

const TABS = [
  { id: 'system',   label: 'System',   sub: 'live telemetry · every second',       path: '/system',   component: SystemTab },
  { id: 'nas',      label: 'Storage',  sub: 'raid · samba shares · smart health', path: '/storage',  component: NasTab },
  { id: 'files',    label: 'Explorer', sub: 'browse every attached drive',        path: '/files',    component: FilesTab },
  { id: 'network',  label: 'Network',  sub: 'lan · tailscale · funnel · vpn',     path: '/network',  component: NetworkTab },
  { id: 'services', label: 'Services', sub: 'systemd units',                      path: '/services', component: ServicesTab },
  { id: 'terminal', label: 'Terminal', sub: 'bash login shell',                   path: '/terminal', component: TerminalTab },
  { id: 'controls', label: 'Controls', sub: 'power · case · fans',                path: '/controls', component: ControlsTab },
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
    case 'network': // globe with latitude/longitude lines
      return (
        <svg {...p}>
          <circle cx="8" cy="8" r="6" />
          <ellipse cx="8" cy="8" rx="3" ry="6" />
          <line x1="2" y1="8" x2="14" y2="8" />
          <line x1="8" y1="2" x2="8" y2="14" />
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

function initials(displayName) {
  // "Akshansh" -> "AK", "Akshansh Kumar" -> "AK". Fall back to "?" so we never
  // render an empty circle even if the gecos field is oddly shaped.
  const parts = displayName.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function sessionRemaining(expiresAt) {
  if (!expiresAt) return null
  const secs = expiresAt - Math.floor(Date.now() / 1000)
  if (secs <= 0) return 'expired'
  const days = Math.floor(secs / 86400)
  if (days >= 1) return `${days}d left`
  const hours = Math.floor(secs / 3600)
  if (hours >= 1) return `${hours}h left`
  const mins = Math.max(1, Math.floor(secs / 60))
  return `${mins}m left`
}

function AccountPopup({ user, avatar, display, onClose, onLogout }) {
  const boxRef = useRef(null)
  const [version, setVersion] = useState(null)
  const [confirmRestart, setConfirmRestart] = useState(false)
  const [restarting, setRestarting] = useState(false)

  // click-outside + Escape close
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    const onDown = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) onClose()
    }
    window.addEventListener('keydown', onKey)
    // pointerdown fires before click, so we run before the trigger's own click.
    // Delay one tick so the click that opened us doesn't immediately close us.
    const id = setTimeout(() => document.addEventListener('pointerdown', onDown), 0)
    return () => {
      window.removeEventListener('keydown', onKey)
      clearTimeout(id)
      document.removeEventListener('pointerdown', onDown)
    }
  }, [onClose])

  useEffect(() => {
    api('/system/version').then(setVersion).catch(() => {})
  }, [])

  async function copyDashUrl() {
    if (await copyText(window.location.origin + '/')) {
      toast.ok('Dashboard URL copied.')
    } else {
      toast.err('Couldn’t copy — grab it from the address bar.')
    }
    onClose()
  }

  async function restart() {
    setRestarting(true)
    try {
      await api('/system/restart', { method: 'POST' })
      toast.ok('Dashboard restarting…')
      onClose()
    } catch (err) {
      toast.err(err.detail)
      setRestarting(false)
    }
  }

  return (
    <div className="account-popup" ref={boxRef} role="menu">
      <span className="tick tick-tl" aria-hidden="true" />
      <span className="tick tick-tr" aria-hidden="true" />
      <span className="tick tick-bl" aria-hidden="true" />
      <span className="tick tick-br" aria-hidden="true" />
      <div className="account-head">
        <span className="account-avatar-lg mono" aria-hidden="true">{avatar}</span>
        <div className="account-identity">
          <div className="account-name">{display}</div>
          <div className="account-handle mono">{user.username}</div>
        </div>
      </div>
      <div className="account-meta">
        {user.client_ip && (
          <div className="account-meta-row">
            <span className="account-meta-key">signed in from</span>
            <span className="account-meta-val mono">{user.client_ip}</span>
          </div>
        )}
        {user.session_expires_at && (
          <div className="account-meta-row">
            <span className="account-meta-key">session</span>
            <span className="account-meta-val mono">{sessionRemaining(user.session_expires_at)}</span>
          </div>
        )}
        {version && (
          <div className="account-meta-row">
            <span className="account-meta-key">version</span>
            <a
              className="account-meta-val mono account-meta-link"
              href={`${version.repo_url}/commit/${version.commit}`}
              target="_blank"
              rel="noopener"
              title={version.committed_at || ''}
            >
              {version.commit}
            </a>
          </div>
        )}
      </div>
      <div className="account-actions">
        <button className="account-action" onClick={copyDashUrl}>
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="5" y="5" width="8" height="8" rx="1" />
            <path d="M3 11V4a1 1 0 0 1 1-1h7" />
          </svg>
          Copy dashboard URL
        </button>
        <a
          className="account-action"
          href={version?.repo_url || 'https://github.com/akshanshkmr/PiNAS'}
          target="_blank"
          rel="noopener"
          onClick={onClose}
        >
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M6.5 12H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
            <path d="M9.5 4H11a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-1.5"/>
            <line x1="5.5" y1="8" x2="10.5" y2="8"/>
          </svg>
          View on GitHub
        </a>
        {confirmRestart ? (
          <div className="account-confirm">
            <span className="mono">Restart the dashboard?</span>
            <div className="account-confirm-btns">
              <button
                className="account-action account-signout"
                onClick={restart}
                disabled={restarting}
              >
                {restarting ? 'Restarting…' : 'Yes, restart'}
              </button>
              <button
                className="account-action"
                onClick={() => setConfirmRestart(false)}
                disabled={restarting}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button className="account-action" onClick={() => setConfirmRestart(true)}>
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M13.5 4.5v3h-3"/>
              <path d="M13 6.5A5.5 5.5 0 1 0 14 10.5"/>
            </svg>
            Restart dashboard
          </button>
        )}
        <button className="account-action account-signout" onClick={onLogout}>
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10 3H4a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h6" />
            <polyline points="9 5.5 12 8 9 10.5" />
            <line x1="12" y1="8" x2="6.5" y2="8" />
          </svg>
          Sign out
        </button>
      </div>
    </div>
  )
}

function Sidebar({ user, online, onLogout }) {
  const display = titleCase(user.name || user.username)
  const firstName = display.split(' ')[0]
  const avatar = initials(display)
  const [open, setOpen] = useState(false)
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
        <button
          className={`foot-user-btn ${open ? 'is-open' : ''}`}
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <span className="foot-avatar mono" aria-hidden="true">{avatar}</span>
          <span className="foot-user-lines">
            <span className="foot-greet">{greeting()},</span>
            <span className="foot-name">{firstName}</span>
          </span>
          <svg
            className="foot-user-chevron"
            viewBox="0 0 16 16"
            width="12"
            height="12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="4 6 8 10 12 6" />
          </svg>
        </button>
        {open && (
          <AccountPopup
            user={user}
            display={display}
            avatar={avatar}
            onClose={() => setOpen(false)}
            onLogout={() => { setOpen(false); onLogout() }}
          />
        )}
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
        cells.map((c) => {
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
        })
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
            <div className="area-head-titles">
              <h1 className="area-title">{active.label}</h1>
              {active.sub && <p className="area-sub mono">{active.sub}</p>}
            </div>
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
    return (
      <div className="boot-screen">
        <span className="viewport-tick vt-tl" aria-hidden="true" />
        <span className="viewport-tick vt-tr" aria-hidden="true" />
        <span className="viewport-tick vt-bl" aria-hidden="true" />
        <span className="viewport-tick vt-br" aria-hidden="true" />
        <div className="boot-stack">
          <div className="login-led">
            <span className="login-led-dot" aria-hidden="true" />
            pironman 5 · handshake
          </div>
          <div className="boot-brand">PI·NAS</div>
          <div className="boot-status mono">establishing session…</div>
        </div>
      </div>
    )
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
