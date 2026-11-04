export interface Segment {
  label: string
  value: number
  className: string
}

export function SegmentedBar({ segments, label }: { segments: Segment[]; label: string }) {
  const total = segments.reduce((sum, item) => sum + item.value, 0)
  return (
    <div>
      <div
        role="img"
        aria-label={`${label}: ${segments.map((item) => `${item.value} ${item.label}`).join(', ')}`}
        className="flex h-2 overflow-hidden rounded bg-well"
      >
        {total > 0 &&
          segments
            .filter((item) => item.value > 0)
            .map((item) => (
              <div key={item.label} className={item.className} style={{ width: `${(item.value / total) * 100}%` }} />
            ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-2">
        {segments.map((item) => (
          <li key={item.label} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-sm ${item.className}`} aria-hidden="true" />
            {item.label} <span className="tabular-nums text-fg">{item.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Points are values between 0 and 1, oldest first. */
export function Sparkline({ points, label }: { points: number[]; label: string }) {
  const width = 180
  const height = 44
  if (points.length === 0) return <p className="text-sm text-fg-3">No runs yet.</p>
  const step = points.length > 1 ? width / (points.length - 1) : 0
  const coords = points.map((value, index) => ({
    x: points.length > 1 ? index * step : width / 2,
    y: height - 4 - value * (height - 8),
  }))
  const path = coords.map((c, index) => `${index === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ')
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${width} ${height}`} className="h-11 w-full max-w-[220px]">
      <line x1="0" x2={width} y1={height - 4} y2={height - 4} className="stroke-line" strokeWidth="1" />
      {points.length > 1 && <path d={path} fill="none" className="stroke-accent" strokeWidth="1.75" />}
      {coords.map((c, index) => (
        <circle key={index} cx={c.x} cy={c.y} r="3" className="fill-accent" />
      ))}
    </svg>
  )
}
