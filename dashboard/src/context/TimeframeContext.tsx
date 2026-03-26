import { createContext, useContext, useState } from 'react'

export const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d'] as const
export type Timeframe = typeof TIMEFRAMES[number]

interface TimeframeContextValue {
  timeframe: Timeframe
  setTimeframe: (tf: Timeframe) => void
}

const TimeframeContext = createContext<TimeframeContextValue>({
  timeframe: '5m',
  setTimeframe: () => undefined,
})

export function TimeframeProvider({ children }: { children: React.ReactNode }) {
  const [timeframe, setTimeframe] = useState<Timeframe>('5m')
  return (
    <TimeframeContext.Provider value={{ timeframe, setTimeframe }}>
      {children}
    </TimeframeContext.Provider>
  )
}

export function useTimeframe() {
  return useContext(TimeframeContext)
}
