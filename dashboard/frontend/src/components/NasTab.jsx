import { useEffect, useState } from 'react'
import { api, fmtBytes } from '../api'
import { toast } from '../toast'
import { Badge, Bar, Btn, Card, ConfirmWord, EmptyState, Field } from './ui'

const RAID_MIN_DISKS = { 0: 2, 1: 2, 5: 3, 10: 4 }
const RAID_HELP = {
  0: 'Striping. Full capacity, no redundancy — one failed disk loses everything.',
  1: 'Mirroring. Half capacity, survives a single disk failure.',
  5: 'Striping with parity. Survives one disk failure.',
  10: 'Mirrored stripes. Survives one disk failure per mirror.',
}

function diskStatus(d) {
  if (d.in_raid) return <Badge tone="accent">raid member</Badge>
  if (d.mountpoint) return <Badge tone="warn">mounted</Badge>
  return <Badge tone="ok">free</Badge>
}

function SmartCard() {
  const [drives, setDrives] = useState(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    setBusy(true)
    try {
      const res = await api('/nas/smart')
      setDrives(res.drives)
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  const days = (h) => (h != null ? `${Math.round(h / 24)} days` : '—')

  return (
    <Card
      eyebrow="drive health"
      title="smart"
      actions={
        <Btn onClick={load} busy={busy}>
          {drives ? 'Re-check' : 'Read SMART'}
        </Btn>
      }
    >
      {!drives && <p className="field-hint">Reads per-drive SMART health, temperature, and error counters via smartctl.</p>}
      {drives && drives.length === 0 && (
        <EmptyState>No SMART-capable drives found. The boot SD card doesn’t report SMART data.</EmptyState>
      )}
      {drives && drives.length > 0 && (
        <div className="smart-list">
          {drives.map((d) => (
            <div key={d.device} className={`smart-row ${d.health === 'failed' ? 'is-failed' : ''}`}>
              <div className="smart-head">
                <div>
                  <span className="mono smart-dev">{d.device}</span>
                  <span className="smart-model">{d.model || 'Unknown drive'}</span>
                </div>
                {!d.available ? (
                  <Badge tone="muted">no data</Badge>
                ) : (
                  <Badge tone={d.health === 'passed' ? 'ok' : d.health === 'failed' ? 'crit' : 'warn'}>
                    {d.health === 'passed' ? 'healthy' : d.health}
                  </Badge>
                )}
              </div>
              {d.available && (
                <>
                  <div className="smart-metrics">
                    <div className="smart-metric">
                      <span className="smart-metric-label">temp</span>
                      <span className="mono">{d.temperature != null ? `${d.temperature}°C` : '—'}</span>
                    </div>
                    <div className="smart-metric">
                      <span className="smart-metric-label">powered on</span>
                      <span className="mono">{days(d.power_on_hours)}</span>
                    </div>
                    {d.type === 'nvme' ? (
                      <>
                        <div className="smart-metric">
                          <span className="smart-metric-label">wear</span>
                          <span className="mono">{d.percentage_used != null ? `${d.percentage_used}%` : '—'}</span>
                        </div>
                        <div className="smart-metric">
                          <span className="smart-metric-label">media errors</span>
                          <span className="mono">{d.media_errors ?? '—'}</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="smart-metric">
                          <span className="smart-metric-label">reallocated</span>
                          <span className="mono">{d.reallocated ?? '—'}</span>
                        </div>
                        <div className="smart-metric">
                          <span className="smart-metric-label">pending</span>
                          <span className="mono">{d.pending ?? '—'}</span>
                        </div>
                      </>
                    )}
                  </div>
                  {d.warnings && d.warnings.length > 0 && (
                    <ul className="smart-warnings">
                      {d.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              {!d.available && <p className="field-hint">{d.error}</p>}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function ArrayCard({ arr, onAction, busyAction }) {
  const [confirmStop, setConfirmStop] = useState(null) // null | ''
  const [confirmRepair, setConfirmRepair] = useState(null)
  const [detail, setDetail] = useState(null)
  const degraded = arr.members.some((m) => m.faulty)

  async function showDetail() {
    if (detail) {
      setDetail(null)
      return
    }
    try {
      const d = await api(`/nas/raid/${arr.name}`)
      setDetail(d.detail)
    } catch (err) {
      toast.err(err.detail)
    }
  }

  return (
    <Card
      eyebrow={`raid ${arr.level.replace('raid', '')}`}
      title={arr.device}
      className="array-card"
      actions={
        <Badge tone={degraded ? 'crit' : arr.state === 'active' ? 'ok' : 'warn'}>
          {degraded ? 'degraded' : arr.state}
        </Badge>
      }
    >
      <div className="kv">
        <span>Capacity</span>
        <span className="mono">{fmtBytes(arr.size)}</span>
      </div>
      <div className="kv">
        <span>Mounted at</span>
        <span className="mono">{arr.mountpoint || 'not mounted'}</span>
      </div>
      <div className="kv">
        <span>Members</span>
        <span className="chip-row">
          {arr.members.map((m) => (
            <span key={m.device} className={`chip mono ${m.faulty ? 'chip-crit' : ''}`}>
              {m.device.replace('/dev/', '')}
              {m.faulty ? ' ✗' : ''}
            </span>
          ))}
        </span>
      </div>

      {arr.sync && (
        <div className="sync-progress">
          <div className="kv">
            <span>{arr.sync.action} in progress</span>
            <span className="mono">
              {arr.sync.percent.toFixed(1)}%{arr.sync.finish ? ` · ${arr.sync.finish} left` : ''}
            </span>
          </div>
          <Bar percent={arr.sync.percent} />
        </div>
      )}

      <div className="btn-row">
        {arr.mountpoint ? (
          <Btn onClick={() => onAction(`unmount-${arr.name}`, `/nas/raid/${arr.name}/unmount`)} busy={busyAction === `unmount-${arr.name}`}>
            Unmount
          </Btn>
        ) : (
          <Btn onClick={() => onAction(`mount-${arr.name}`, `/nas/raid/${arr.name}/mount`, {})} busy={busyAction === `mount-${arr.name}`}>
            Mount
          </Btn>
        )}
        <Btn
          onClick={() =>
            onAction(`check-${arr.name}`, `/nas/raid/${arr.name}/sync`, { action: 'check', confirm: 'CHECK' })
          }
          busy={busyAction === `check-${arr.name}`}
        >
          Check integrity
        </Btn>
        <Btn onClick={() => setConfirmRepair(confirmRepair === null ? '' : null)}>Repair…</Btn>
        <Btn variant="danger-ghost" onClick={() => setConfirmStop(confirmStop === null ? '' : null)}>
          Stop array…
        </Btn>
        <Btn variant="ghost" onClick={showDetail}>
          {detail ? 'Hide detail' : 'Detail'}
        </Btn>
      </div>

      {confirmRepair !== null && (
        <div className="confirm-box">
          <p>Repair resyncs data across members. The array stays usable but slower.</p>
          <div className="btn-row">
            <ConfirmWord word="REPAIR" value={confirmRepair} onChange={setConfirmRepair} />
            <Btn
              variant="primary"
              disabled={confirmRepair.trim().toUpperCase() !== 'REPAIR'}
              busy={busyAction === `repair-${arr.name}`}
              onClick={async () => {
                await onAction(`repair-${arr.name}`, `/nas/raid/${arr.name}/sync`, {
                  action: 'repair',
                  confirm: confirmRepair,
                })
                setConfirmRepair(null)
              }}
            >
              Start repair
            </Btn>
          </div>
        </div>
      )}

      {confirmStop !== null && (
        <div className="confirm-box confirm-danger">
          <p>Stopping unmounts and deactivates the array. Data stays on the disks; reassemble to bring it back.</p>
          <div className="btn-row">
            <ConfirmWord word="STOP" value={confirmStop} onChange={setConfirmStop} />
            <Btn
              variant="danger"
              disabled={confirmStop.trim().toUpperCase() !== 'STOP'}
              busy={busyAction === `stop-${arr.name}`}
              onClick={async () => {
                await onAction(`stop-${arr.name}`, `/nas/raid/${arr.name}/stop`, { confirm: confirmStop })
                setConfirmStop(null)
              }}
            >
              Stop array
            </Btn>
          </div>
        </div>
      )}

      {detail && <pre className="code-block">{detail}</pre>}
    </Card>
  )
}

function CreateArrayCard({ disks, onDone }) {
  const [selected, setSelected] = useState([])
  const [level, setLevel] = useState('1')
  const [mountpoint, setMountpoint] = useState('/mnt/nas')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  const eligible = disks.filter((d) => !d.in_raid && !d.mountpoint)
  const minDisks = RAID_MIN_DISKS[level]
  const ready = selected.length >= minDisks && confirm.trim().toUpperCase() === 'CREATE'

  function toggleDisk(device) {
    setSelected((cur) => (cur.includes(device) ? cur.filter((d) => d !== device) : [...cur, device]))
  }

  async function create() {
    setBusy(true)
    try {
      const res = await api('/nas/raid', {
        method: 'POST',
        body: { disks: selected, level, mountpoint, confirm },
      })
      toast.ok(res.message)
      setSelected([])
      setConfirm('')
      onDone()
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card eyebrow="provision" title="Create a new array">
      {eligible.length === 0 ? (
        <EmptyState>No free disks. Attach drives, or stop an existing array to reuse its members.</EmptyState>
      ) : (
        <>
          <div className="field-label">Select disks — everything on them will be erased</div>
          <div className="disk-picker">
            {eligible.map((d) => (
              <label key={d.device} className={`disk-option ${selected.includes(d.device) ? 'is-selected' : ''}`}>
                <input
                  type="checkbox"
                  checked={selected.includes(d.device)}
                  onChange={() => toggleDisk(d.device)}
                />
                <span className="mono">{d.device}</span>
                <span className="disk-meta">
                  {fmtBytes(d.size)} · {d.model}
                </span>
              </label>
            ))}
          </div>

          <div className="form-row">
            <Field label="RAID level" hint={RAID_HELP[level]}>
              <select className="input" value={level} onChange={(e) => setLevel(e.target.value)}>
                {Object.keys(RAID_MIN_DISKS).map((l) => (
                  <option key={l} value={l}>
                    RAID {l} (min {RAID_MIN_DISKS[l]} disks)
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Mount at" hint="Under /mnt, /srv or /media. Added to fstab automatically.">
              <input className="input mono" value={mountpoint} onChange={(e) => setMountpoint(e.target.value)} />
            </Field>
          </div>

          <div className="confirm-box confirm-danger">
            <p>
              This wipes {selected.length ? selected.join(', ') : 'the selected disks'} and builds a RAID {level}
              {' '}array formatted as ext4.
            </p>
            <div className="btn-row">
              <ConfirmWord word="CREATE" value={confirm} onChange={setConfirm} />
              <Btn variant="danger" disabled={!ready} busy={busy} onClick={create}>
                Wipe disks and create array
              </Btn>
            </div>
            {selected.length > 0 && selected.length < minDisks && (
              <div className="field-hint">RAID {level} needs at least {minDisks} disks — {selected.length} selected.</div>
            )}
          </div>
        </>
      )}
    </Card>
  )
}

function SambaCard({ samba, linuxUsers, onDone }) {
  const [shares, setShares] = useState(samba.shares)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [newUser, setNewUser] = useState(linuxUsers[0] || '')
  const [newPass, setNewPass] = useState('')
  const [userBusy, setUserBusy] = useState(false)

  useEffect(() => {
    if (!dirty) setShares(samba.shares)
  }, [samba.shares, dirty])

  function edit(i, patch) {
    setShares((cur) => cur.map((s, idx) => (idx === i ? { ...s, ...patch } : s)))
    setDirty(true)
  }

  function addRow() {
    setShares((cur) => [...cur, { name: '', path: '/mnt/nas', allow_guest: false, read_only: false }])
    setDirty(true)
  }

  function removeRow(i) {
    setShares((cur) => cur.filter((_, idx) => idx !== i))
    setDirty(true)
  }

  async function save() {
    setBusy(true)
    try {
      const res = await api('/nas/samba/shares', { method: 'PUT', body: { shares } })
      toast.ok(res.message)
      setDirty(false)
      onDone()
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  async function addUser() {
    setUserBusy(true)
    try {
      const res = await api('/nas/samba/users', { method: 'POST', body: { username: newUser, password: newPass } })
      toast.ok(res.message)
      setNewPass('')
      onDone()
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setUserBusy(false)
    }
  }

  async function disableUser(username) {
    try {
      const res = await api(`/nas/samba/users/${username}/disable`, { method: 'POST' })
      toast.ok(res.message)
      onDone()
    } catch (err) {
      toast.err(err.detail)
    }
  }

  return (
    <Card
      eyebrow="samba"
      title="Network shares"
      actions={
        <Badge tone={samba.service === 'active' ? 'ok' : 'crit'}>smbd {samba.service}</Badge>
      }
    >
      {shares.length === 0 ? (
        <EmptyState>No shares yet. Add one to expose a folder on the network.</EmptyState>
      ) : (
        <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Share name</th>
              <th>Path</th>
              <th>Guest</th>
              <th>Read-only</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {shares.map((s, i) => (
              <tr key={i}>
                <td>
                  <input className="input mono" value={s.name} onChange={(e) => edit(i, { name: e.target.value })} />
                </td>
                <td>
                  <input className="input mono" value={s.path} onChange={(e) => edit(i, { path: e.target.value })} />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={s.allow_guest}
                    onChange={(e) => edit(i, { allow_guest: e.target.checked })}
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={s.read_only}
                    onChange={(e) => edit(i, { read_only: e.target.checked })}
                  />
                </td>
                <td>
                  <Btn variant="ghost" onClick={() => removeRow(i)} aria-label={`Remove share ${s.name}`}>
                    ✕
                  </Btn>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      <div className="btn-row">
        <Btn onClick={addRow}>Add share</Btn>
        <Btn variant="primary" onClick={save} busy={busy} disabled={!dirty}>
          {dirty ? 'Save and restart Samba' : 'Saved'}
        </Btn>
      </div>

      <div className="divider" />

      <div className="field-label">Share users</div>
      <p className="field-hint">
        Samba keeps its own passwords. Enable a Linux user here with the password they will use from other devices.
      </p>
      {samba.users.length > 0 && (
        <div className="chip-row samba-users">
          {samba.users.map((u) => (
            <span key={u} className="chip mono">
              {u}
              <button className="chip-x" title={`Disable ${u}`} onClick={() => disableUser(u)}>
                ✕
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="form-row">
        <Field label="Linux user">
          <select className="input" value={newUser} onChange={(e) => setNewUser(e.target.value)}>
            {linuxUsers.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Share password">
          <input
            className="input"
            type="password"
            value={newPass}
            onChange={(e) => setNewPass(e.target.value)}
            autoComplete="new-password"
          />
        </Field>
        <Btn variant="primary" onClick={addUser} busy={userBusy} disabled={!newUser || !newPass}>
          Enable user
        </Btn>
      </div>
    </Card>
  )
}

export default function NasTab() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [linuxUsers, setLinuxUsers] = useState([])
  const [busyAction, setBusyAction] = useState('')

  async function load() {
    try {
      const [overview, users] = await Promise.all([api('/nas/overview'), api('/auth/users')])
      setData(overview)
      setLinuxUsers(users.users)
      setError('')
    } catch (err) {
      if (err.status !== 401) setError(err.detail)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // Poll while a sync/rebuild is running so progress stays live.
  useEffect(() => {
    if (!data || !data.arrays.some((a) => a.sync)) return
    const t = setTimeout(load, 5000)
    return () => clearTimeout(t)
  }, [data])

  async function runAction(id, path, body) {
    setBusyAction(id)
    try {
      const res = await api(path, { method: 'POST', body: body ?? undefined })
      toast.ok(res.message || 'Done.')
      await load()
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusyAction('')
    }
  }

  if (!data) {
    return <div className="tab-loading">{error || 'Reading NAS state…'}</div>
  }

  return (
    <div className="stack">
      <Card
        eyebrow="disks"
        title="Physical disks"
        actions={
          <div className="btn-row">
            <Btn onClick={() => runAction('assemble', '/nas/raid/assemble')} busy={busyAction === 'assemble'}>
              Scan &amp; assemble arrays
            </Btn>
            <Btn variant="ghost" onClick={load}>
              Refresh
            </Btn>
          </div>
        }
      >
        {data.disks.length === 0 ? (
          <EmptyState>No data disks attached. The boot SD card is not shown here.</EmptyState>
        ) : (
          <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Model</th>
                <th className="num">Size</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.disks.map((d) => (
                <tr key={d.device}>
                  <td className="mono">{d.device}</td>
                  <td>{d.model}</td>
                  <td className="mono num">{fmtBytes(d.size)}</td>
                  <td>{diskStatus(d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>

      {data.arrays.length === 0 ? (
        <Card eyebrow="raid" title="Arrays">
          <EmptyState>
            No active arrays. Create one below, or use “Scan &amp; assemble” if disks from an existing array are
            attached.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid grid-2">
          {data.arrays.map((arr) => (
            <ArrayCard key={arr.name} arr={arr} onAction={runAction} busyAction={busyAction} />
          ))}
        </div>
      )}

      <CreateArrayCard disks={data.disks} onDone={load} />

      <SmartCard />

      <SambaCard samba={data.samba} linuxUsers={linuxUsers} onDone={load} />
    </div>
  )
}
