import { useMemo } from 'react'
import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { OHLCVCandle } from '@/api/client'

interface CandlestickChartProps {
  candles: OHLCVCandle[]
  height?: number
}

interface CandleBar {
  time: string
  open: number
  close: number
  high: number
  low: number
  volume: number
  bodyLow: number
  bodyHigh: number
  isBullish: boolean
}

function CandleShape(props: {
  x?: number
  y?: number
  width?: number
  height?: number
  fill?: string
  payload?: CandleBar
}) {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props
  if (!payload) return null

  const { open, close, high, low, isBullish } = payload
  const color = isBullish ? '#22c55e' : '#ef4444'

  // The bar represents the body (open-close). We need to draw the wick separately.
  const chartHeight = y + height // bottom of the bar area
  const chartTop = y // top of the bar area

  // We need the price-to-pixel conversion — approximate from the bar bounds
  const bodyH = Math.abs(height)
  if (bodyH === 0) return null

  const bodyRange = Math.abs(close - open)
  if (bodyRange === 0) return null

  const pricePerPixel = bodyRange / bodyH

  // Wick positions relative to the bar
  const wickTopOffset = (Math.max(open, close) - high) / pricePerPixel
  const wickBottomOffset = (low - Math.min(open, close)) / pricePerPixel

  const cx = x + width / 2
  const wickX = cx

  return (
    <g>
      {/* Upper wick */}
      <line
        x1={wickX}
        y1={chartTop + wickTopOffset}
        x2={wickX}
        y2={chartTop}
        stroke={color}
        strokeWidth={1}
      />
      {/* Candle body */}
      <rect
        x={x + 1}
        y={chartTop}
        width={Math.max(1, width - 2)}
        height={Math.max(1, bodyH)}
        fill={color}
        stroke={color}
        strokeWidth={0.5}
      />
      {/* Lower wick */}
      <line
        x1={wickX}
        y1={chartHeight}
        x2={wickX}
        y2={chartHeight + wickBottomOffset}
        stroke={color}
        strokeWidth={1}
      />
    </g>
  )
}

export function CandlestickChart({ candles, height = 300 }: CandlestickChartProps) {
  const data = useMemo<CandleBar[]>(() => {
    return candles.map(c => ({
      time: new Date(c.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      open: c.open,
      close: c.close,
      high: c.high,
      low: c.low,
      volume: c.volume,
      bodyLow: Math.min(c.open, c.close),
      bodyHigh: Math.max(c.open, c.close),
      isBullish: c.close >= c.open,
    }))
  }, [candles])

  if (!data.length) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-sm" style={{ height }}>
        No candle data available
      </div>
    )
  }

  // Compute display range for every Nth candle to avoid label clutter
  const step = Math.max(1, Math.floor(data.length / 8))
  const ticks = data.filter((_, i) => i % step === 0).map(d => d.time)

  const priceMin = Math.min(...candles.map(c => c.low)) * 0.999
  const priceMax = Math.max(...candles.map(c => c.high)) * 1.001

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="70%">
        <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
          <XAxis
            dataKey="time"
            ticks={ticks}
            tick={{ fontSize: 10 }}
            tickLine={false}
          />
          <YAxis
            domain={[priceMin, priceMax]}
            tickFormatter={v => `$${Number(v).toLocaleString()}`}
            tick={{ fontSize: 10 }}
            width={70}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.[0]) return null
              const d = payload[0].payload as CandleBar
              return (
                <div className="rounded border bg-background/95 p-2 text-xs shadow">
                  <p className="font-semibold mb-1">{d.time}</p>
                  <p>O: <span className="font-mono">${d.open.toLocaleString()}</span></p>
                  <p>H: <span className="font-mono">${d.high.toLocaleString()}</span></p>
                  <p>L: <span className="font-mono">${d.low.toLocaleString()}</span></p>
                  <p>C: <span className="font-mono">${d.close.toLocaleString()}</span></p>
                  <p>V: <span className="font-mono">{d.volume.toLocaleString()}</span></p>
                </div>
              )
            }}
          />
          <Bar dataKey="bodyHigh" shape={<CandleShape />} isAnimationActive={false}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.isBullish ? '#22c55e' : '#ef4444'} />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
      {/* Volume bars */}
      <ResponsiveContainer width="100%" height="30%">
        <ComposedChart data={data} margin={{ top: 0, right: 8, bottom: 4, left: 8 }}>
          <XAxis dataKey="time" hide />
          <YAxis tick={{ fontSize: 9 }} width={70} tickFormatter={v => String(Math.round(Number(v)))} />
          <Bar dataKey="volume" isAnimationActive={false}>
            {data.map((entry, index) => (
              <Cell key={`vol-${index}`} fill={entry.isBullish ? '#22c55e80' : '#ef444480'} />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
