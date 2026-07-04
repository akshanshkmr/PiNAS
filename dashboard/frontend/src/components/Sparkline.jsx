/** Minimal SVG area sparkline; no chart library needed for 120 points. */
export default function Sparkline({ data, min = 0, max = 100, tone = 'accent' }) {
  const W = 200
  const H = 44
  if (!data || data.length < 2) {
    return <svg className="sparkline" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true" />
  }
  const span = max - min || 1
  const step = W / (data.length - 1)
  const y = (v) => H - 2 - ((Math.min(max, Math.max(min, v)) - min) / span) * (H - 6)
  const pts = data.map((v, i) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`)
  const line = `M${pts.join(' L')}`
  const area = `${line} L${W},${H} L0,${H} Z`
  return (
    <svg className={`sparkline spark-${tone}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      <path className="spark-area" d={area} />
      <path className="spark-line" d={line} />
    </svg>
  )
}
