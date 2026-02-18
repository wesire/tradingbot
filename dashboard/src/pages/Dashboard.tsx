import { useEffect, useState } from "react"
import { Activity, DollarSign, TrendingUp, Zap } from "lucide-react"
import { StatusCard } from "@/components/StatusCard"
import { TradeTable } from "@/components/TradeTable"
import { PnLChart } from "@/components/PnLChart"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { BotStatus, Position, Trade, WebhookEvent, PnLData } from "@/api/client"

// Mock data for demo
const mockStatus: BotStatus = {
  status: 'running',
  mode: 'dry-run',
  uptime: 86400,
  last_heartbeat: new Date().toISOString(),
}

const mockPositions: Position[] = [
  {
    symbol: 'BTC/USDT',
    side: 'long',
    size: 0.5,
    entry_price: 45000,
    current_price: 46200,
    pnl: 600,
    pnl_percentage: 2.67,
    leverage: 3,
  },
  {
    symbol: 'ETH/USDT',
    side: 'short',
    size: 5,
    entry_price: 2500,
    current_price: 2450,
    pnl: 250,
    pnl_percentage: 2.0,
    leverage: 2,
  },
]

const mockTrades: Trade[] = [
  {
    id: '1',
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    symbol: 'BTC/USDT',
    side: 'buy',
    size: 0.5,
    price: 45000,
    status: 'open',
  },
  {
    id: '2',
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    symbol: 'ETH/USDT',
    side: 'sell',
    size: 5,
    price: 2500,
    status: 'open',
  },
  {
    id: '3',
    timestamp: new Date(Date.now() - 10800000).toISOString(),
    symbol: 'SOL/USDT',
    side: 'buy',
    size: 20,
    price: 100,
    pnl: -50,
    status: 'closed',
  },
]

const mockWebhookEvents: WebhookEvent[] = [
  {
    id: '1',
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    action: 'buy',
    symbol: 'BTC/USDT',
    details: { leverage: 3, stop_loss: 44000 },
    processed: true,
  },
  {
    id: '2',
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    action: 'sell',
    symbol: 'ETH/USDT',
    details: { leverage: 2, take_profit: 2400 },
    processed: true,
  },
]

const mockPnLData: PnLData[] = Array.from({ length: 24 }, (_, i) => ({
  timestamp: new Date(Date.now() - (23 - i) * 3600000).toISOString(),
  realized_pnl: Math.random() * 200 - 50,
  unrealized_pnl: Math.random() * 300 - 100,
  total_pnl: Math.random() * 400 - 100,
}))

export function Dashboard() {
  const [status] = useState<BotStatus>(mockStatus)
  const [positions] = useState<Position[]>(mockPositions)
  const [trades] = useState<Trade[]>(mockTrades)
  const [webhookEvents] = useState<WebhookEvent[]>(mockWebhookEvents)
  const [pnlData] = useState<PnLData[]>(mockPnLData)
  const [activeTab, setActiveTab] = useState('overview')

  useEffect(() => {
    // In production, fetch real data from API
    // fetchData()
  }, [])

  const totalPnL = positions.reduce((sum, p) => sum + p.pnl, 0)
  const totalPnLPercentage = positions.length > 0 
    ? positions.reduce((sum, p) => sum + p.pnl_percentage, 0) / positions.length 
    : 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Real-time overview of your trading bot performance
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          title="Bot Status"
          value={status.status.toUpperCase()}
          subtitle={`Mode: ${status.mode}`}
          icon={Activity}
        />
        <StatusCard
          title="Total P&L"
          value={`$${totalPnL.toFixed(2)}`}
          subtitle={`${totalPnLPercentage >= 0 ? '+' : ''}${totalPnLPercentage.toFixed(2)}%`}
          icon={DollarSign}
        />
        <StatusCard
          title="Open Positions"
          value={positions.length}
          subtitle={`${positions.filter(p => p.side === 'long').length} long, ${positions.filter(p => p.side === 'short').length} short`}
          icon={TrendingUp}
        />
        <StatusCard
          title="Uptime"
          value={`${Math.floor(status.uptime / 3600)}h`}
          subtitle={`Last heartbeat: ${new Date(status.last_heartbeat).toLocaleTimeString()}`}
          icon={Zap}
        />
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

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview" active={activeTab === 'overview'} onClick={() => setActiveTab('overview')}>
            Overview
          </TabsTrigger>
          <TabsTrigger value="positions" active={activeTab === 'positions'} onClick={() => setActiveTab('positions')}>
            Positions
          </TabsTrigger>
          <TabsTrigger value="trades" active={activeTab === 'trades'} onClick={() => setActiveTab('trades')}>
            Trade History
          </TabsTrigger>
          <TabsTrigger value="webhooks" active={activeTab === 'webhooks'} onClick={() => setActiveTab('webhooks')}>
            Webhook Events
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" active={activeTab === 'overview'}>
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Latest trades and positions</CardDescription>
            </CardHeader>
            <CardContent>
              <TradeTable trades={trades.slice(0, 5)} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="positions" active={activeTab === 'positions'}>
          <Card>
            <CardHeader>
              <CardTitle>Open Positions</CardTitle>
              <CardDescription>Current market positions</CardDescription>
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
                  {positions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground">
                        No open positions
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
              <TradeTable trades={trades} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="webhooks" active={activeTab === 'webhooks'}>
          <Card>
            <CardHeader>
              <CardTitle>Webhook Events</CardTitle>
              <CardDescription>Recent webhook signals received</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Details</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {webhookEvents.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        No webhook events
                      </TableCell>
                    </TableRow>
                  ) : (
                    webhookEvents.map((event) => (
                      <TableRow key={event.id}>
                        <TableCell className="font-mono text-sm">
                          {new Date(event.timestamp).toLocaleString()}
                        </TableCell>
                        <TableCell>
                          <Badge variant={event.action === 'buy' ? 'success' : 'destructive'}>
                            {event.action.toUpperCase()}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-medium">{event.symbol}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {JSON.stringify(event.details)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={event.processed ? 'success' : 'warning'}>
                            {event.processed ? 'Processed' : 'Pending'}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
