import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { useMemo } from 'react'
import type { SentimentHistoryPoint } from '@/api/client'

interface SentimentHistoryChartProps {
  data: SentimentHistoryPoint[]
  height?: number
}

export function SentimentHistoryChart({ data = [], height = 200 }: SentimentHistoryChartProps) {
  const chartData = useMemo(() =>
    (data ?? []).map(p => ({
      time: new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      score: p.score,
    })),
    [data]
  )

  if (!chartData.length) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-sm" style={{ height }}>
        No sentiment history available
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height} minWidth={0} minHeight={0}>
      <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <defs>
          <linearGradient id="sentPos" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="sentNeg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
        <XAxis dataKey="time" tick={{ fontSize: 10 }} tickLine={false} />
        <YAxis
          domain={[-1, 1]}
          tickFormatter={v => `${Number(v).toFixed(1)}`}
          tick={{ fontSize: 10 }}
          width={40}
        />
        <ReferenceLine y={0} stroke="#6b7280" strokeWidth={1} />
        <Tooltip
          formatter={(v: number | undefined) => [(v ?? 0).toFixed(3), 'Sentiment Score']}
          labelStyle={{ fontSize: 11 }}
          contentStyle={{ fontSize: 11 }}
        />
        <Area
          type="monotone"
          dataKey="score"
          stroke="#6366f1"
          strokeWidth={2}
          fill="url(#sentPos)"
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
