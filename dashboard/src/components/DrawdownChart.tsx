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
import type { EquityPoint } from '@/api/client'

interface DrawdownChartProps {
  data: EquityPoint[]
  height?: number
}

export function DrawdownChart({ data, height = 160 }: DrawdownChartProps) {
  const chartData = useMemo(() => {
    let peak = -Infinity
    return (data ?? []).map(p => {
      if (p.equity > peak) peak = p.equity
      const dd = peak > 0 ? ((p.equity - peak) / peak) * 100 : 0
      return {
        time: new Date(p.ts).toLocaleDateString([], { month: 'short', day: 'numeric' }),
        drawdown: Math.min(0, dd),
      }
    })
  }, [data])

  if (!chartData.length) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-sm" style={{ height }}>
        No drawdown data available
      </div>
    )
  }

  const minDD = chartData.length > 0 ? Math.min(...chartData.map(d => d.drawdown)) : 0

  return (
    <ResponsiveContainer width="100%" height={height} minWidth={0} minHeight={0}>
      <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <defs>
          <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
        <XAxis dataKey="time" tick={{ fontSize: 10 }} tickLine={false} />
        <YAxis
          domain={[minDD * 1.1, 0]}
          tickFormatter={v => `${Number(v).toFixed(1)}%`}
          tick={{ fontSize: 10 }}
          width={56}
        />
        <ReferenceLine y={0} stroke="#6b7280" strokeWidth={1} />
        <Tooltip
          formatter={(v: number | undefined) => [`${Number(v ?? 0).toFixed(2)}%`, 'Drawdown']}
          labelStyle={{ fontSize: 11 }}
          contentStyle={{ fontSize: 11 }}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke="#ef4444"
          strokeWidth={2}
          fill="url(#ddGrad)"
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
