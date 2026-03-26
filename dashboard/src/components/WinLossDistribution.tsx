import { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { MLPrediction } from '@/api/client'

interface WinLossDistributionProps {
  predictions: MLPrediction[]
  height?: number
}

export function WinLossDistribution({ predictions, height = 220 }: WinLossDistributionProps) {
  const chartData = useMemo(() => {
    const buckets: Record<string, { wins: number; losses: number }> = {}
    const bucketEdges = [0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.01]

    for (let i = 0; i < bucketEdges.length - 1; i++) {
      const label = `${Math.round(bucketEdges[i] * 100)}–${Math.round(bucketEdges[i + 1] * 100)}%`
      buckets[label] = { wins: 0, losses: 0 }
    }

    predictions.forEach(p => {
      if (p.actual_outcome === 'pending') return
      const c = p.confidence
      for (let i = 0; i < bucketEdges.length - 1; i++) {
        if (c >= bucketEdges[i] && c < bucketEdges[i + 1]) {
          const label = `${Math.round(bucketEdges[i] * 100)}–${Math.round(bucketEdges[i + 1] * 100)}%`
          if (p.actual_outcome === 'win') buckets[label].wins++
          else buckets[label].losses++
          break
        }
      }
    })

    return Object.entries(buckets)
      .map(([label, counts]) => ({ label, ...counts }))
      .filter(d => d.wins + d.losses > 0)
  }, [predictions])

  if (!chartData.length) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-sm" style={{ height }}>
        No prediction outcomes to display
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} width={32} />
        <Tooltip contentStyle={{ fontSize: 11 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="wins" name="Wins" stackId="a" fill="#22c55e" isAnimationActive={false}>
          {chartData.map((_, i) => <Cell key={i} fill="#22c55e" />)}
        </Bar>
        <Bar dataKey="losses" name="Losses" stackId="a" fill="#ef4444" isAnimationActive={false}>
          {chartData.map((_, i) => <Cell key={i} fill="#ef4444" />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
