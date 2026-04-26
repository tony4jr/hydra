/**
 * Inline SVG sparkline — 24-point trend visualization.
 *
 * Usage:
 *   <Sparkline data={[1,2,5,3,8,...]} width={120} height={28} />
 */
interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
  fillOpacity?: number
}

export function Sparkline({
  data,
  width = 120,
  height = 28,
  color,
  fillOpacity = 0.12,
}: SparklineProps) {
  if (!data || data.length === 0) {
    return <svg width={width} height={height} />
  }
  const max = Math.max(...data, 1)
  const min = 0
  const stepX = width / Math.max(data.length - 1, 1)

  const points = data.map((v, i) => {
    const x = i * stepX
    const y = height - ((v - min) / Math.max(max - min, 1)) * (height - 2) - 1
    return [x, y] as const
  })

  const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const last = points[points.length - 1]
  const area = `${path} L${(last ? last[0] : width).toFixed(1)},${height} L0,${height} Z`

  const stroke = color || 'currentColor'

  return (
    <svg width={width} height={height} className='hydra-spark' aria-hidden>
      <path d={area} fill={stroke} fillOpacity={fillOpacity} stroke='none' />
      <path d={path} fill='none' stroke={stroke} strokeWidth='1.5' strokeLinecap='round' strokeLinejoin='round' />
      {/* last point dot */}
      {last && (
        <circle cx={last[0]} cy={last[1]} r='2.2' fill={stroke} />
      )}
    </svg>
  )
}
