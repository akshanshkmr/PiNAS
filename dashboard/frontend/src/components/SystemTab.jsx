import { fmtBytes, fmtCount } from '../api'
import Sparkline from './Sparkline'
import { Badge, Bar, Panel, severity } from './ui'

function TrendPanel({ label, value, unit, history, low, high, max = 100 }) {
  const sev = severity(value, low, high)
  const delta = history.length >= 2 ? history[history.length - 1] - history[history.length - 2] : 0
  return (
    <Panel label={label} className="trend-panel" tone={sev.tone}>
      <div className="trend-row">
        <div className={`trend-value mono tone-${sev.tone}`}>
          {value.toFixed(1)}
          <span className="trend-unit">{unit}</span>
        </div>
        <div className="trend-side">
          <span className={`trend-delta ${delta > 0 ? 'is-up' : delta < 0 ? 'is-down' : ''}`}>
            {delta === 0 ? '±0.0' : `${delta > 0 ? '▲' : '▼'} ${Math.abs(delta).toFixed(1)}`}
          </span>
          <span className="trend-window mono">5 min</span>
        </div>
      </div>
      <Sparkline data={history} max={max} tone={sev.tone} />
    </Panel>
  )
}

export default function SystemTab({ stats }) {
  if (!stats) {
    return <div className="tab-loading mono">reading system metrics…</div>
  }

  const disk = severity(stats.disk.percent, 70, 90)

  return (
    <div className="stack">
      <div className="grid grid-3">
        <TrendPanel label="cpu load · 5m" value={stats.cpu} unit="%" history={stats.history.cpu} low={30} high={80} />
        <TrendPanel label="memory · 5m" value={stats.ram} unit="%" history={stats.history.ram} low={30} high={80} />
        <TrendPanel
          label="soc temp · 5m"
          value={stats.cpu_temp}
          unit="°C"
          history={stats.history.temp}
          low={55}
          high={75}
          max={90}
        />
      </div>

      <div className="grid grid-3">
        <Panel label="network" meta="interface">
          <dl className="readout">
            <div>
              <dt>local ip</dt>
              <dd className="mono">{stats.ip}</dd>
            </div>
            <div>
              <dt>hostname</dt>
              <dd className="mono">{stats.hostname}</dd>
            </div>
            <div>
              <dt>board temp</dt>
              <dd className="mono">{stats.adc_temp.toFixed(1)} °C</dd>
            </div>
          </dl>
        </Panel>

        <Panel label="net · tx" meta="transmitted">
          <div className="stat-hero mono">{fmtCount(stats.net.packets_sent)}</div>
          <div className="stat-hero-sub">packets · {fmtBytes(stats.net.bytes_sent)} total</div>
        </Panel>

        <Panel label="net · rx" meta="received">
          <div className="stat-hero mono">{fmtCount(stats.net.packets_recv)}</div>
          <div className="stat-hero-sub">packets · {fmtBytes(stats.net.bytes_recv)} total</div>
        </Panel>
      </div>

      <div className="grid grid-2">
        <Panel label="uptime" meta="since last boot">
          <div className="stat-hero stat-hero-lg">{stats.uptime}</div>
          <div className="stat-hero-sub">memory in use · {fmtBytes(stats.memory.used)} of {fmtBytes(stats.memory.total)}</div>
        </Panel>

        <Panel label="root filesystem" actions={<Badge tone={disk.tone}>{disk.label}</Badge>}>
          <div className="disk-line">
            <span className="mono">{fmtBytes(stats.disk.used)} / {fmtBytes(stats.disk.total)}</span>
            <span className="mono tone-muted">{stats.disk.percent.toFixed(1)}%</span>
          </div>
          <Bar percent={stats.disk.percent} tone={disk.tone} />
          <div className="stat-hero-sub">{fmtBytes(stats.disk.free)} free</div>
        </Panel>
      </div>

      <Panel label="processes" meta="top by cpu">
        <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>process</th>
              <th className="num">pid</th>
              <th className="wide">cpu</th>
              <th className="wide">memory</th>
            </tr>
          </thead>
          <tbody>
            {stats.processes.map((p) => (
              <tr key={p.pid}>
                <td className="mono">{p.name}</td>
                <td className="mono num tone-muted">{p.pid}</td>
                <td>
                  <div className="cell-bar">
                    <Bar percent={p.cpu} />
                    <span className="mono">{p.cpu.toFixed(1)}%</span>
                  </div>
                </td>
                <td>
                  <div className="cell-bar">
                    <Bar percent={p.ram} tone="violet" />
                    <span className="mono">{p.ram.toFixed(1)}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </Panel>
    </div>
  )
}
