import { useEffect, useState } from 'react'
import { api } from '../api'
import { toast } from '../toast'
import { Badge, Btn, Panel } from './ui'

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
      // give systemd a moment to settle before re-reading state
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
      <UnitsPanel />
    </div>
  )
}
