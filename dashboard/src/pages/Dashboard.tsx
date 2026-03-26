import { useEffect, useState, useCallback, useRef } from "react"
import { Activity, DollarSign, TrendingUp, Zap, RefreshCw, AlertCircle } from "lucide-react"
import { StatusCard } from "@/components/StatusCard"
import { TradeTable } from "@/components/TradeTable"
import { PnLChart } from "@/components/PnLChart"
import { SentimentWidget } from "@/components/SentimentWidget"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { CandlestickChart } from "@/components/CandlestickChart"
import { EquityCurve } from "@/components/EquityCurve"
import { DrawdownChart } from "@/components/DrawdownChart"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiClient } from "@/api/client"
import { useWebSocket } from "@/hooks/useWebSocket"
import { useTimeframe } from "@/context/TimeframeContext"
import type { BotStatus, Position, Trade, PnLData, OHLCVCandle, EquityPoint } from "@/api/client"

const HTTP_POLL_FALLBACK_INTERVAL_MS = 30_000 // 30-second fallback HTTP polling when WebSocket unavailable
const WS_CHANNELS = ["positions", "trades", "status", "alerts"]
const DEFAULT_PAIR = 'BTC/USDT:USDT'

export function Dashboard() {
  const { timeframe } = useTimeframe()
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [trades, setTrades] = useState<Trade[]>([])
  const [tradesSource, setTradesSource] = useState<'exchange' | 'alerts' | undefined>(undefined)
  const [pnlData, setPnlData] = useState<PnLData[]>([])
  const [candles, setCandles] = useState<OHLCVCandle[]>([])
  const [equityCurve, setEquityCurve] = useState<EquityPoint[]>([])
  const [activeTab, setActiveTab] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  // Flash state: tracks which channel cards were recently updated via WebSocket
  const [flashedChannels, setFlashedChannels] = useState<Set<string>>(new Set())
  const flashTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const flashChannel = useCallback((channel: string) => {
    if (flashTimers.current[channel]) clearTimeout(flashTimers.current[channel])
    setFlashedChannels(prev => new Set([...prev, channel]))
    flashTimers.current[channel] = setTimeout(() => {
      setFlashedChannels(prev => {
        const next = new Set(prev)
        next.delete(channel)
        return next
      })
    }, 1200)
  }, [])

  // WebSocket connection — real-time streaming
  const { connectionState, data: wsData, lastUpdate, activeSubscriptions } = useWebSocket(WS_CHANNELS)
  const wsConnected = connectionState === 'connected'

  // Apply WebSocket data updates
  const prevWsData = useRef<Record<string, unknown>>({})
  useEffect(() => {
    if (wsData.positions !== prevWsData.current.positions && wsData.positions) {
      const payload = wsData.positions as { positions?: Position[] }
      if (payload.positions) {
        setPositions(payload.positions)
        flashChannel("positions")
        setLastRefresh(new Date())
      }
    }

    if (wsData.status !== prevWsData.current.status && wsData.status) {
      const payload = wsData.status as Partial<BotStatus>
      setStatus(prev => prev ? { ...prev, ...payload } : (payload as BotStatus))
      flashChannel("status")
      setLastRefresh(new Date())
    }

    prevWsData.current = wsData
  }, [wsData, flashChannel])

  // HTTP polling fallback — always runs for initial load; continues at 30s
  const fetchData = useCallback(async () => {
    try {
      const [statusData, positionsData, tradesData, pnlDataResult, ohlcvResult, equityResult] = await Promise.allSettled([
        apiClient.getBotStatus(),
        apiClient.getPositions(),
        apiClient.getTrades(50),
        apiClient.getPnLHistory('24h'),
        apiClient.getOHLCV(DEFAULT_PAIR, timeframe, 100),
        apiClient.getPerformanceReport('30d'),
      ])

      if (statusData.status === 'fulfilled') setStatus(statusData.value)
      // Only update positions from HTTP when WebSocket is not connected
      if (positionsData.status === 'fulfilled' && !wsConnected) {
        setPositions(positionsData.value)
      }
      if (tradesData.status === 'fulfilled') {
        const result = tradesData.value as Trade[] & { _source?: 'exchange' | 'alerts' }
        setTrades(result)
        if (result.length > 0 && result[0].source) {
          setTradesSource(result[0].source)
        }
      }
      if (pnlDataResult.status === 'fulfilled') setPnlData(pnlDataResult.value)
      if (ohlcvResult.status === 'fulfilled') setCandles(ohlcvResult.value.candles)
      if (equityResult.status === 'fulfilled') setEquityCurve(equityResult.value.equity_curve)

      setError(null)
      setLastRefresh(new Date())
    } catch (err) {
      setError('Failed to load dashboard data. Is the backend running?')
      console.error('Dashboard fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [wsConnected, timeframe])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, HTTP_POLL_FALLBACK_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchData])

  const totalPnL = positions.reduce((sum, p) => sum + p.pnl, 0)
  const totalPnLPercentage = positions.length > 0
    ? positions.reduce((sum, p) => sum + p.pnl_percentage, 0) / positions.length
    : 0

  const uptimeHours = status ? Math.floor(status.uptime / 3600) : 0

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground text-sm lg:text-base">
            Real-time overview of your trading bot performance
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <ConnectionStatus
            connectionState={connectionState}
            lastUpdate={lastUpdate}
            activeSubscriptions={activeSubscriptions}
          />
          <div className="flex items-center gap-1">
            <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
            {lastRefresh.toLocaleTimeString()}
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-500">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          title="Bot Status"
          value={status ? status.status.toUpperCase() : '—'}
          subtitle={status ? `Mode: ${status.mode}` : 'Loading…'}
          icon={Activity}
          flash={flashedChannels.has("status")}
        />
        <StatusCard
          title="Total P&L"
          value={`$${totalPnL.toFixed(2)}`}
          subtitle={`${totalPnLPercentage >= 0 ? '+' : ''}${totalPnLPercentage.toFixed(2)}%`}
          icon={DollarSign}
          flash={flashedChannels.has("positions")}
        />
        <StatusCard
          title="Open Positions"
          value={positions.length}
          subtitle={`${positions.filter(p => p.side === 'long').length} long, ${positions.filter(p => p.side === 'short').length} short`}
          icon={TrendingUp}
          flash={flashedChannels.has("positions")}
        />
        <StatusCard
          title="Uptime"
          value={`${uptimeHours}h`}
          subtitle={status ? `Last heartbeat: ${new Date(status.last_heartbeat).toLocaleTimeString()}` : 'Loading…'}
          icon={Zap}
        />
      </div>

      {status && !status.exchange_connected && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          No exchange connected. Add <code className="font-mono">EXCHANGE_API_KEY</code> and <code className="font-mono">EXCHANGE_API_SECRET</code> to your <code className="font-mono">.env</code> to see live positions.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Price Chart — {DEFAULT_PAIR}</CardTitle>
          <CardDescription>OHLCV candlestick with volume ({timeframe} timeframe)</CardDescription>
        </CardHeader>
        <CardContent>
          <CandlestickChart candles={candles} height={360} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Equity Curve</CardTitle>
            <CardDescription>Account equity over the last 30 days</CardDescription>
          </CardHeader>
          <CardContent>
            <EquityCurve data={equityCurve} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Drawdown</CardTitle>
            <CardDescription>Peak-to-trough drawdown over time</CardDescription>
          </CardHeader>
          <CardContent>
            <DrawdownChart data={equityCurve} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>P&L Chart</CardTitle>
          <CardDescription>24-hour profit and loss tracking</CardDescription>
        </CardHeader>
        <CardContent>
          <PnLChart data={pnlData} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {/* placeholder for additional chart or info */}
        </div>
        <SentimentWidget />
      </div>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview" active={activeTab === 'overview'}>
            Overview
          </TabsTrigger>
          <TabsTrigger value="positions" active={activeTab === 'positions'}>
            Positions
          </TabsTrigger>
          <TabsTrigger value="trades" active={activeTab === 'trades'}>
            Trade History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" active={activeTab === 'overview'}>
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Latest trades and positions</CardDescription>
            </CardHeader>
            <CardContent>
              <TradeTable trades={trades.slice(0, 5)} loading={loading} source={tradesSource} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="positions" active={activeTab === 'positions'}>
          <Card>
            <CardHeader>
              <CardTitle>Open Positions</CardTitle>
              <CardDescription>Current market positions from the exchange</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Side</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead>Entry Price</TableHead>
                    <TableHead>Current Price</TableHead>
                    <TableHead>P&L</TableHead>
                    <TableHead>Leverage</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground">
                        Loading positions…
                      </TableCell>
                    </TableRow>
                  ) : positions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground py-6">
                        No open positions — active exchange positions will appear here.
                      </TableCell>
                    </TableRow>
                  ) : (
                    positions.map((position, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-medium">{position.symbol}</TableCell>
                        <TableCell>
                          <Badge variant={position.side === 'long' ? 'success' : 'destructive'}>
                            {position.side.toUpperCase()}
                          </Badge>
                        </TableCell>
                        <TableCell>{position.size}</TableCell>
                        <TableCell>${position.entry_price.toFixed(2)}</TableCell>
                        <TableCell>${position.current_price.toFixed(2)}</TableCell>
                        <TableCell>
                          <span className={position.pnl >= 0 ? 'text-green-500' : 'text-red-500'}>
                            ${position.pnl.toFixed(2)} ({position.pnl_percentage >= 0 ? '+' : ''}{position.pnl_percentage.toFixed(2)}%)
                          </span>
                        </TableCell>
                        <TableCell>{position.leverage}x</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trades" active={activeTab === 'trades'}>
          <Card>
            <CardHeader>
              <CardTitle>Trade History</CardTitle>
              <CardDescription>All executed trades</CardDescription>
            </CardHeader>
            <CardContent>
              <TradeTable trades={trades} loading={loading} source={tradesSource} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
