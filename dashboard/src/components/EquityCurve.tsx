import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useMemo } from 'react'
import type { EquityPoint } from '@/api/client'

interface EquityCurveProps {
  data: EquityPoint[]
  height?: number
}

export function EquityCurve({ data, height = 220 }: EquityCurveProps) {
  const chartData = useMemo(() =>
    (data ?? []).map(p => ({
      time: new Date(p.ts).toLocaleDateString([], { month: 'short', day: 'numeric' }),
      equity: p.equity,
    })),
    [data]
  )

  if (!chartData.length) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-sm" style={{ height }}>
        No equity data available
      </div>
    )
  }

  const min = Math.min(...(data ?? []).map(p => p.equity)) * 0.995
  const max = Math.max(...(data ?? []).map(p => p.equity)) * 1.005

  return (
    <ResponsiveContainer width="100%" height={height} minWidth={0} minHeight={0}>
      <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
        <XAxis dataKey="time" tick={{ fontSize: 10 }} tickLine={false} />
        <YAxis
          domain={[min, max]}
          tickFormatter={v => `$${Number(v).toLocaleString()}`}
          tick={{ fontSize: 10 }}
          width={72}
        />
        <Tooltip
          formatter={(v: number | undefined) => [`$${(v ?? 0).toLocaleString()}`, 'Equity']}
          labelStyle={{ fontSize: 11 }}
          contentStyle={{ fontSize: 11 }}
        />
        <Area
          type="monotone"
          dataKey="equity"
          stroke="#6366f1"
          strokeWidth={2}
          fill="url(#equityGrad)"
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
