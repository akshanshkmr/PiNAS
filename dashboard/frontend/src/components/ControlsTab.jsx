import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { toast } from '../toast'
import { Badge, Btn, Panel, ConfirmWord, Field, Toggle, severity } from './ui'

const FAN_MODES = ['Always On', 'Performance', 'Cool', 'Balanced', 'Quiet']
const RGB_STYLES = ['solid', 'breathing', 'flow', 'flow_reverse', 'rainbow', 'rainbow_reverse', 'hue_cycle']

/* ---------------- Cooling: both fans + live temperature ---------------- */

function CoolingCard({ stats, config, reload }) {
  const [cpuFan, setCpuFan] = useState(null)
  const [fanMode, setFanMode] = useState(config?.gpio_fan_mode ?? 0)
  const [cpuBusy, setCpuBusy] = useState(false)
  const [caseBusy, setCaseBusy] = useState(false)

  useEffect(() => {
    api('/controls/cpu-fan')
      .then((r) => setCpuFan(r.ok ? r.on : null))
      .catch(() => setCpuFan(null))
  }, [])

  useEffect(() => {
    if (config) setFanMode(config.gpio_fan_mode ?? 0)
  }, [config])

  async function toggleCpuFan(on) {
    setCpuBusy(true)
    const prev = cpuFan
    setCpuFan(on)
    try {
      await api('/controls/cpu-fan', { method: 'PUT', body: { on } })
      toast.ok(`CPU fan turned ${on ? 'on' : 'off'}`)
    } catch (err) {
      setCpuFan(prev)
      toast.err(err.detail)
    } finally {
      setCpuBusy(false)
    }
  }

  async function changeFanMode(mode) {
    setCaseBusy(true)
    const prev = fanMode
    setFanMode(mode)
    try {
      await api('/controls/pironman', { method: 'PUT', body: { gpio_fan_mode: mode } })
      toast.ok(`Case fan set to ${FAN_MODES[mode]}`)
      reload()
    } catch (err) {
      setFanMode(prev)
      toast.err(err.detail)
    } finally {
      setCaseBusy(false)
    }
  }

  const temp = stats?.cpu_temp
  const tempSev = temp != null ? severity(temp, 55, 75) : null

  return (
    <Panel
      label="cooling"
      meta="fans"
      actions={
        tempSev && (
          <Badge tone={tempSev.tone}>
            soc {temp.toFixed(1)}°C · {tempSev.label}
          </Badge>
        )
      }
    >
      <div className="control-line">
        <span className="control-line-label">
          CPU fan
          <span className="sub">Direct GPIO control — applies instantly</span>
        </span>
        {cpuFan == null ? (
          <span className="field-hint">unavailable</span>
        ) : (
          <Toggle
            label={cpuFan ? 'Running' : 'Off'}
            checked={cpuFan}
            disabled={cpuBusy}
            onChange={toggleCpuFan}
          />
        )}
      </div>

      <div className="control-line">
        <span className="control-line-label">
          Case fan
          <span className="sub">Pironman fan profile — applies on change</span>
        </span>
        <select
          className="input control-select"
          value={fanMode}
          disabled={caseBusy || !config}
          onChange={(e) => changeFanMode(Number(e.target.value))}
        >
          {FAN_MODES.map((m, i) => (
            <option key={m} value={i}>
              {m}
            </option>
          ))}
        </select>
      </div>
    </Panel>
  )
}

/* ---------------- Lighting & display: batched, dirty-aware ---------------- */

function formFromConfig(c) {
  return {
    rgb_enable: Boolean(c.rgb_enable ?? true),
    rgb_color: `#${String(c.rgb_color ?? 'ffffff').replace('#', '')}`,
    rgb_brightness: Number(c.rgb_brightness ?? 50),
    rgb_style: RGB_STYLES.includes(c.rgb_style) ? c.rgb_style : 'hue_cycle',
    rgb_speed: Number(c.rgb_speed ?? 50),
    oled_enable: Boolean(c.oled_enable ?? true),
    oled_rotation: Number(c.oled_rotation ?? 0),
    oled_disk: String(c.oled_disk ?? 'total'),
    oled_network_interface: String(c.oled_network_interface ?? 'all'),
    oled_sleep_timeout: Number(c.oled_sleep_timeout ?? 10),
  }
}

function AppearanceCard({ config, reload }) {
  const [form, setForm] = useState(null)
  const baseline = useRef(null)
  const [busy, setBusy] = useState(false)

  // Initialize once, so a case-fan change (which reloads config) can't discard
  // in-progress lighting edits. Our own applies update the baseline directly.
  useEffect(() => {
    if (config && baseline.current === null) {
      const f = formFromConfig(config)
      setForm(f)
      baseline.current = JSON.stringify(f)
    }
  }, [config])

  if (!form) {
    return (
      <Panel label="lighting & display" meta="pironman case">
        <p className="field-hint">Reading case configuration…</p>
      </Panel>
    )
  }

  const dirty = JSON.stringify(form) !== baseline.current
  const set = (patch) => setForm((cur) => ({ ...cur, ...patch }))

  async function apply() {
    setBusy(true)
    try {
      const res = await api('/controls/pironman', {
        method: 'PUT',
        body: { ...form, rgb_color: form.rgb_color.replace('#', '') },
      })
      toast.ok(res.message)
      baseline.current = JSON.stringify(form)
      reload()
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setForm(JSON.parse(baseline.current))
  }

  return (
    <Panel
      label="lighting & display"
      meta="pironman case"
      actions={
        <>
          {dirty && <span className="dirty-pill">unsaved</span>}
          {dirty && (
            <Btn variant="ghost" onClick={reset}>
              Discard
            </Btn>
          )}
          <Btn variant="primary" onClick={apply} busy={busy} disabled={!dirty}>
            Apply changes
          </Btn>
        </>
      }
    >
      <div className="grid grid-2">
        <div>
          <div className="field-label group-label">RGB lighting</div>
          <Toggle label="RGB enabled" checked={form.rgb_enable} onChange={(v) => set({ rgb_enable: v })} />
          <Field label="Color">
            <div className="swatch-row">
              <input
                type="color"
                className="swatch"
                value={form.rgb_color}
                onChange={(e) => set({ rgb_color: e.target.value })}
                disabled={!form.rgb_enable}
              />
              <span className="swatch-hex">{form.rgb_color.toUpperCase()}</span>
            </div>
          </Field>
          <Field label="Style">
            <select
              className="input"
              value={form.rgb_style}
              disabled={!form.rgb_enable}
              onChange={(e) => set({ rgb_style: e.target.value })}
            >
              {RGB_STYLES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </Field>
          <Field label={`Brightness · ${form.rgb_brightness}%`}>
            <input
              type="range"
              min="0"
              max="100"
              value={form.rgb_brightness}
              disabled={!form.rgb_enable}
              style={{ '--fill': `${form.rgb_brightness}%` }}
              onChange={(e) => set({ rgb_brightness: Number(e.target.value) })}
            />
          </Field>
          <Field label={`Animation speed · ${form.rgb_speed}%`}>
            <input
              type="range"
              min="0"
              max="100"
              value={form.rgb_speed}
              disabled={!form.rgb_enable}
              style={{ '--fill': `${form.rgb_speed}%` }}
              onChange={(e) => set({ rgb_speed: Number(e.target.value) })}
            />
          </Field>
        </div>

        <div>
          <div className="field-label group-label">OLED display</div>
          <Toggle label="OLED enabled" checked={form.oled_enable} onChange={(v) => set({ oled_enable: v })} />
          <Field label="Rotation">
            <select
              className="input"
              value={form.oled_rotation}
              disabled={!form.oled_enable}
              onChange={(e) => set({ oled_rotation: Number(e.target.value) })}
            >
              <option value={0}>0°</option>
              <option value={180}>180°</option>
            </select>
          </Field>
          <Field label="Disk shown" hint="total, or a device like nvme0n1">
            <input
              className="input mono"
              value={form.oled_disk}
              disabled={!form.oled_enable}
              onChange={(e) => set({ oled_disk: e.target.value })}
            />
          </Field>
          <Field label="Network interface" hint="all, eth0, wlan0…">
            <input
              className="input mono"
              value={form.oled_network_interface}
              disabled={!form.oled_enable}
              onChange={(e) => set({ oled_network_interface: e.target.value })}
            />
          </Field>
          <Field label="Sleep timeout (seconds)">
            <input
              type="number"
              min="0"
              className="input"
              value={form.oled_sleep_timeout}
              disabled={!form.oled_enable}
              onChange={(e) => set({ oled_sleep_timeout: Number(e.target.value) })}
            />
          </Field>
        </div>
      </div>
    </Panel>
  )
}

/* ---------------- Power ---------------- */

function PowerCard() {
  const [pending, setPending] = useState(null) // 'reboot' | 'shutdown' | null
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const word = pending === 'reboot' ? 'REBOOT' : 'SHUTDOWN'

  function choose(action) {
    setPending((cur) => (cur === action ? null : action))
    setConfirm('')
  }

  async function execute() {
    setBusy(true)
    try {
      const res = await api('/controls/power', { method: 'POST', body: { action: pending, confirm } })
      toast.ok(res.message)
      setPending(null)
      setConfirm('')
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel label="power" actions={<Badge tone="crit">danger zone</Badge>}>
      <p className="field-hint">Both actions disconnect every active session immediately.</p>
      <div className="btn-row">
        <Btn variant={pending === 'reboot' ? 'primary' : 'default'} onClick={() => choose('reboot')}>
          Reboot…
        </Btn>
        <Btn variant={pending === 'shutdown' ? 'primary' : 'default'} onClick={() => choose('shutdown')}>
          Shut down…
        </Btn>
      </div>
      {pending && (
        <div className="confirm-box confirm-danger">
          <p>
            {pending === 'reboot'
              ? 'The Pi restarts and should be back in about a minute.'
              : 'The Pi powers off. You will need physical access to turn it back on.'}
          </p>
          <div className="btn-row">
            <ConfirmWord word={word} value={confirm} onChange={setConfirm} />
            <Btn variant="danger" disabled={confirm.trim().toUpperCase() !== word} busy={busy} onClick={execute}>
              {pending === 'reboot' ? 'Reboot now' : 'Shut down now'}
            </Btn>
          </div>
        </div>
      )}
    </Panel>
  )
}

/* ---------------- Tab ---------------- */

export default function ControlsTab({ stats }) {
  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState('')

  async function loadConfig() {
    try {
      const res = await api('/controls/pironman')
      if (res.ok) {
        setConfig(res.config)
        setConfigError('')
      } else {
        setConfigError(res.error)
      }
    } catch (err) {
      setConfigError(err.detail)
    }
  }

  useEffect(() => {
    loadConfig()
  }, [])

  const pironmanAvailable = !configError

  return (
    <div className="stack">
      <div className="grid grid-2">
        <CoolingCard stats={stats} config={config} reload={loadConfig} />
        <PowerCard />
      </div>

      {pironmanAvailable ? (
        <AppearanceCard config={config} reload={loadConfig} />
      ) : (
        <Panel label="lighting & display" meta="pironman case">
          <div className="empty-state">Pironman tools aren’t available: {configError}</div>
        </Panel>
      )}
    </div>
  )
}
