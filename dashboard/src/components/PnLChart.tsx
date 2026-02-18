import type { PnLData } from "@/api/client"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

interface PnLChartProps {
  data: PnLData[];
}

export function PnLChart({ data }: PnLChartProps) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#444" />
        <XAxis 
          dataKey="timestamp" 
          stroke="#888"
          tickFormatter={(value) => new Date(value).toLocaleTimeString()}
        />
        <YAxis stroke="#888" />
        <Tooltip 
          contentStyle={{ 
            backgroundColor: '#1a1a1a', 
            border: '1px solid #444',
            borderRadius: '8px'
          }}
          labelFormatter={(value) => new Date(value).toLocaleString()}
        />
        <Legend />
        <Line 
          type="monotone" 
          dataKey="realized_pnl" 
          stroke="#10b981" 
          name="Realized PnL"
          strokeWidth={2}
        />
        <Line 
          type="monotone" 
          dataKey="unrealized_pnl" 
          stroke="#3b82f6" 
          name="Unrealized PnL"
          strokeWidth={2}
        />
        <Line 
          type="monotone" 
          dataKey="total_pnl" 
          stroke="#8b5cf6" 
          name="Total PnL"
          strokeWidth={2}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
