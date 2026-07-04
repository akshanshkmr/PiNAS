import { useEffect, useState } from 'react'
import { api, copyText } from '../api'
import { toast } from '../toast'
import { Badge, Btn, EmptyState, Panel, Toggle } from './ui'

/* -------------------- Tailscale -------------------- */

function CopyRow({ label, value, hint }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    if (await copyText(value)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } else {
      toast.err('Couldn’t copy — select the text and copy manually.')
    }
  }
  return (
    <div className="copy-row">
      <div className="copy-main">
        <span className="copy-label">{label}</span>
        <code className="copy-value">{value}</code>
        {hint && <span className="field-hint">{hint}</span>}
      </div>
      <Btn variant="ghost" onClick={copy}>
        {copied ? 'Copied' : 'Copy'}
      </Btn>
    </div>
  )
}

function TailscalePanel() {
  const [ts, setTs] = useState(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      setTs(await api('/services/tailscale'))
    } catch (err) {
      toast.err(err.detail)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function setConnection(connect) {
    setBusy(true)
    try {
      const res = await api('/services/tailscale/connection', { method: 'PUT', body: { connect } })
      toast.ok(res.message)
      await load()
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  if (!ts) {
    return (
      <Panel label="tailscale" meta="remote access">
        <p className="field-hint">Reading tailnet status…</p>
      </Panel>
    )
  }
  if (!ts.available) {
    return (
      <Panel label="tailscale" meta="remote access">
        <EmptyState>Tailscale isn’t available: {ts.error}</EmptyState>
      </Panel>
    )
  }

  const running = ts.state === 'Running'
  // Trailing slash matters: it hits the dashboard directly instead of an Apache
  // redirect, which would otherwise downgrade the tailnet URL to http.
  const httpsUrl = ts.dns_name ? `https://${ts.dns_name}/status/` : null
  const smbHost = ts.dns_name || ts.ips[0]

  return (
    <Panel
      label="tailscale"
      meta="remote access"
      actions={
        <Badge tone={running ? 'ok' : ts.state === 'NeedsLogin' ? 'crit' : 'warn'}>{ts.state.toLowerCase()}</Badge>
      }
    >
      <div className="control-line">
        <span className="control-line-label">
          Tailnet connection
          <span className="sub">
            {ts.hostname} · {ts.ips[0] || 'no address'}
          </span>
        </span>
        {ts.state === 'NeedsLogin' ? (
          <span className="field-hint">Run `sudo tailscale up` on the Pi to log in.</span>
        ) : (
          <Toggle
            label={running ? 'Connected' : 'Disconnected'}
            checked={running}
            disabled={busy}
            onChange={setConnection}
          />
        )}
      </div>

      {running && (
        <div className="access-block">
          <div className="field-label group-label">Reach this server from anywhere on your tailnet</div>
          {httpsUrl && ts.serving && (
            <CopyRow label="Dashboard (HTTPS)" value={httpsUrl} hint="Tailscale serves this over TLS — no port forwarding, no HTTP." />
          )}
          {httpsUrl && !ts.serving && (
            <p className="field-hint">
              Run <code>sudo tailscale serve --bg http://localhost:80</code> on the Pi to expose the dashboard over HTTPS.
            </p>
          )}
          {smbHost && (
            <CopyRow
              label="NAS shares (SMB)"
              value={`smb://${smbHost}/`}
              hint="Open in Finder (⌘K) or Windows Explorer. Append the share name, e.g. smb://…/nas"
            />
          )}
        </div>
      )}

      <div className="field-label group-label">Devices on this tailnet</div>
      {ts.peers.length === 0 ? (
        <EmptyState>No other devices connected.</EmptyState>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>device</th>
                <th>os</th>
                <th>address</th>
                <th>status</th>
              </tr>
            </thead>
            <tbody>
              {ts.peers.map((p) => (
                <tr key={p.ip || p.name}>
                  <td className="mono">{p.hostname || p.name}</td>
                  <td className="tone-muted">{p.os}</td>
                  <td className="mono tone-muted">{p.ip}</td>
                  <td>
                    <Badge tone={p.online ? 'ok' : 'muted'}>{p.online ? 'online' : 'offline'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

/* -------------------- systemd units -------------------- */

function UnitRow({ unit, onAction, busyAction }) {
  const [confirmStop, setConfirmStop] = useState(false)
  const [logs, setLogs] = useState(null)
  const [logsBusy, setLogsBusy] = useState(false)

  const active = unit.active === 'active'
  const isSelf = unit.unit === 'dashboard'

  async function toggleLogs() {
    if (logs !== null) {
      setLogs(null)
      return
    }
    setLogsBusy(true)
    try {
      const res = await api(`/services/units/${unit.unit}/logs?lines=200`)
      setLogs(res.logs)
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setLogsBusy(false)
    }
  }

  return (
    <div className="unit-row">
      <div className="unit-main">
        <div className="unit-id">
          <Badge tone={active ? 'ok' : unit.active === 'failed' ? 'crit' : 'muted'}>{unit.sub || unit.active}</Badge>
          <div>
            <div className="unit-name mono">{unit.unit}</div>
            <div className="unit-desc">{unit.description}</div>
          </div>
        </div>
        <div className="unit-actions">
          <Btn
            onClick={() => onAction(unit.unit, active ? 'restart' : 'start')}
            busy={busyAction === `${unit.unit}-restart` || busyAction === `${unit.unit}-start`}
          >
            {active ? 'Restart' : 'Start'}
          </Btn>
          {active &&
            (confirmStop ? (
              <Btn variant="danger" busy={busyAction === `${unit.unit}-stop`} onClick={() => onAction(unit.unit, 'stop')}>
                {isSelf ? 'Stop the dashboard?' : 'Confirm stop'}
              </Btn>
            ) : (
              <Btn variant="danger-ghost" onClick={() => setConfirmStop(true)}>
                Stop
              </Btn>
            ))}
          {confirmStop && (
            <Btn variant="ghost" onClick={() => setConfirmStop(false)}>
              Cancel
            </Btn>
          )}
          <Btn variant="ghost" onClick={toggleLogs} busy={logsBusy}>
            {logs !== null ? 'Hide logs' : 'Logs'}
          </Btn>
        </div>
      </div>
      {logs !== null && <pre className="code-block unit-logs">{logs}</pre>}
    </div>
  )
}

function UnitsPanel() {
  const [units, setUnits] = useState(null)
  const [busyAction, setBusyAction] = useState('')

  async function load() {
    try {
      const res = await api('/services')
      setUnits(res.units)
    } catch (err) {
      toast.err(err.detail)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function runAction(unit, action) {
    setBusyAction(`${unit}-${action}`)
    try {
      const res = await api(`/services/units/${unit}/${action}`, { method: 'POST' })
      toast.ok(res.message)
      // Give systemd a moment to settle before re-reading state.
      setTimeout(load, 800)
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusyAction('')
    }
  }

  return (
    <Panel
      label="services"
      meta="systemd"
      actions={
        <Btn variant="ghost" onClick={load}>
          Refresh
        </Btn>
      }
    >
      {!units ? (
        <p className="field-hint">Reading unit status…</p>
      ) : (
        <div className="unit-list">
          {units.map((u) => (
            <UnitRow key={u.unit} unit={u} onAction={runAction} busyAction={busyAction} />
          ))}
        </div>
      )}
    </Panel>
  )
}

export default function ServicesTab() {
  return (
    <div className="stack">
      <TailscalePanel />
      <UnitsPanel />
    </div>
  )
}
