import { useMemo } from 'react'
import type { CorrelationResponse } from '@/api/client'

interface CorrelationHeatmapProps {
  data: CorrelationResponse
}

function heatColor(value: number): string {
  // -1 → blue, 0 → white/gray, 1 → red
  if (value >= 0) {
    const intensity = Math.round(value * 180)
    return `rgb(${180 + intensity}, ${80 - Math.round(intensity * 0.3)}, ${80 - Math.round(intensity * 0.3)})`
  } else {
    const intensity = Math.round(-value * 180)
    return `rgb(${80 - Math.round(intensity * 0.3)}, ${80 - Math.round(intensity * 0.3)}, ${180 + intensity})`
  }
}

function shortPair(pair: string): string {
  return pair.split('/')[0] ?? pair
}

export function CorrelationHeatmap({ data }: CorrelationHeatmapProps) {
  const { pairs, matrix } = data

  const cells = useMemo(() => {
    return pairs.flatMap(row =>
      pairs.map(col => ({
        row,
        col,
        value: matrix[row]?.[col] ?? 0,
      }))
    )
  }, [pairs, matrix])

  if (!pairs.length) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-sm py-8">
        No correlation data available
      </div>
    )
  }

  const n = pairs.length
  const cellSize = Math.min(80, Math.floor(320 / n))

  return (
    <div className="overflow-auto">
      <table className="border-separate border-spacing-0.5 mx-auto">
        <thead>
          <tr>
            <th className="w-12" />
            {pairs.map(p => (
              <th
                key={p}
                className="text-xs text-muted-foreground font-medium pb-1 text-center"
                style={{ width: cellSize, minWidth: cellSize }}
              >
                {shortPair(p)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pairs.map(row => (
            <tr key={row}>
              <td className="text-xs text-muted-foreground font-medium pr-1 text-right whitespace-nowrap">
                {shortPair(row)}
              </td>
              {pairs.map(col => {
                const entry = cells.find(c => c.row === row && c.col === col)
                const val = entry?.value ?? 0
                return (
                  <td
                    key={col}
                    title={`${shortPair(row)} / ${shortPair(col)}: ${val.toFixed(3)}`}
                    className="rounded text-center text-xs font-mono font-semibold"
                    style={{
                      width: cellSize,
                      height: cellSize,
                      backgroundColor: heatColor(val),
                      color: Math.abs(val) > 0.5 ? '#fff' : '#111',
                    }}
                  >
                    {val.toFixed(2)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
