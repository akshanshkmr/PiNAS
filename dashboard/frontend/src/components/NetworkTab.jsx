import { useEffect, useState } from 'react'
import { api, copyText } from '../api'
import { toast } from '../toast'
import { Badge, Btn, EmptyState, Panel, Toggle } from './ui'

/** Small local-network overview panel — LAN address, hostname, uptime.
 * Reads from the same telemetry stats we already stream to the rail. */
function LanPanel({ stats }) {
  if (!stats) {
    return (
      <Panel label="lan" meta="local network">
        <p className="field-hint">Reading network state…</p>
      </Panel>
    )
  }
  return (
    <Panel label="lan" meta="local network">
      <dl className="readout">
        <div>
          <dt>hostname</dt>
          <dd className="mono">{stats.hostname}</dd>
        </div>
        <div>
          <dt>local ip</dt>
          <dd className="mono">{stats.ip}</dd>
        </div>
        <div>
          <dt>packets tx / rx</dt>
          <dd className="mono">
            {(stats.net.packets_sent / 1000).toFixed(1)}K /{' '}
            {(stats.net.packets_recv / 1000).toFixed(1)}K
          </dd>
        </div>
      </dl>
    </Panel>
  )
}

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

  async function setExitNode(enabled) {
    setBusy(true)
    try {
      const res = await api('/services/tailscale/exit-node', { method: 'PUT', body: { enabled } })
      toast.ok(res.message)
      await load()
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  async function setFunnel(enabled) {
    setBusy(true)
    try {
      const res = await api('/services/tailscale/funnel', { method: 'PUT', body: { enabled } })
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
  const httpsUrl = ts.dns_name ? `https://${ts.dns_name}/` : null
  const smbHost = ts.dns_name || ts.ips[0]

  return (
    <Panel
      label="tailscale"
      meta="remote access"
      actions={
        <Badge tone={running ? 'ok' : ts.state === 'NeedsLogin' ? 'crit' : 'warn'}>
          {ts.state.toLowerCase()}
        </Badge>
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
        <div className="control-line">
          <span className="control-line-label">
            Exit node (VPN)
            <span className="sub">
              Route other tailnet devices' internet traffic through this Pi. Approve in the
              tailnet admin console after enabling.
            </span>
          </span>
          <Toggle
            label={ts.exit_node ? 'Advertising' : 'Off'}
            checked={!!ts.exit_node}
            disabled={busy}
            onChange={setExitNode}
          />
        </div>
      )}

      {running && (
        <div className="control-line">
          <span className="control-line-label">
            Public share links (Funnel)
            <span className="sub">
              Exposes only /s/* to the public internet so share links work off-tailnet. Admin
              UI stays tailnet-only.
            </span>
          </span>
          <Toggle
            label={ts.funnel?.enabled ? 'Enabled' : 'Off'}
            checked={!!ts.funnel?.enabled}
            disabled={busy}
            onChange={setFunnel}
          />
        </div>
      )}

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

export default function NetworkTab({ stats }) {
  return (
    <div className="stack">
      <LanPanel stats={stats} />
      <TailscalePanel />
    </div>
  )
}
