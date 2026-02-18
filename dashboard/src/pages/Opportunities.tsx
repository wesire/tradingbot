import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import type { Opportunity } from "@/api/client"

export function Opportunities() {
  const [filter, setFilter] = useState<'all' | 'long' | 'short'>('all')

  // Mock opportunities data
  const opportunities: Opportunity[] = [
    {
      id: '1',
      symbol: 'BTC/USDT',
      side: 'long',
      confidence: 85,
      entry_price: 46000,
      stop_loss: 44500,
      take_profit: 48000,
      risk_reward: 2.67,
      ai_rationale: 'Strong bullish momentum with volume confirmation. Breaking resistance.',
    },
    {
      id: '2',
      symbol: 'ETH/USDT',
      side: 'long',
      confidence: 78,
      entry_price: 2480,
      stop_loss: 2420,
      take_profit: 2600,
      risk_reward: 2.0,
      ai_rationale: 'Consolidation breakout pattern. RSI showing strength.',
    },
    {
      id: '3',
      symbol: 'SOL/USDT',
      side: 'short',
      confidence: 72,
      entry_price: 105,
      stop_loss: 108,
      take_profit: 98,
      risk_reward: 2.33,
      ai_rationale: 'Overbought conditions. Divergence on momentum indicators.',
    },
    {
      id: '4',
      symbol: 'MATIC/USDT',
      side: 'long',
      confidence: 68,
      entry_price: 0.85,
      stop_loss: 0.82,
      take_profit: 0.91,
      risk_reward: 2.0,
      ai_rationale: 'Support bounce with increasing volume.',
    },
    {
      id: '5',
      symbol: 'AVAX/USDT',
      side: 'short',
      confidence: 65,
      entry_price: 38,
      stop_loss: 39.5,
      take_profit: 34.5,
      risk_reward: 2.33,
      ai_rationale: 'Resistance rejection. Bearish divergence forming.',
    },
  ]

  const filteredOpportunities = opportunities.filter(
    opp => filter === 'all' || opp.side === filter
  )

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 75) return 'success'
    if (confidence >= 60) return 'warning'
    return 'secondary'
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Trading Opportunities</h1>
        <p className="text-muted-foreground">
          AI-identified potential trades based on market analysis
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Total Opportunities</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{opportunities.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Long Signals</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-green-500">
              {opportunities.filter(o => o.side === 'long').length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Short Signals</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-red-500">
              {opportunities.filter(o => o.side === 'short').length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Avg Confidence</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {Math.round(opportunities.reduce((sum, o) => sum + o.confidence, 0) / opportunities.length)}%
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Opportunities</CardTitle>
              <CardDescription>Filter and review potential trading setups</CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant={filter === 'all' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilter('all')}
              >
                All
              </Button>
              <Button
                variant={filter === 'long' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilter('long')}
              >
                Long
              </Button>
              <Button
                variant={filter === 'short' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilter('short')}
              >
                Short
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Side</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Entry</TableHead>
                <TableHead>Stop Loss</TableHead>
                <TableHead>Take Profit</TableHead>
                <TableHead>R:R</TableHead>
                <TableHead>AI Rationale</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredOpportunities.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-muted-foreground">
                    No opportunities match your filter
                  </TableCell>
                </TableRow>
              ) : (
                filteredOpportunities.map((opp) => (
                  <TableRow key={opp.id}>
                    <TableCell className="font-medium">{opp.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={opp.side === 'long' ? 'success' : 'destructive'}>
                        {opp.side.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getConfidenceColor(opp.confidence)}>
                        {opp.confidence}%
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono">${opp.entry_price}</TableCell>
                    <TableCell className="font-mono text-red-500">${opp.stop_loss}</TableCell>
                    <TableCell className="font-mono text-green-500">${opp.take_profit}</TableCell>
                    <TableCell className="font-bold">{opp.risk_reward.toFixed(2)}</TableCell>
                    <TableCell className="max-w-xs text-sm text-muted-foreground">
                      {opp.ai_rationale}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Top Opportunity</CardTitle>
          <CardDescription>Highest confidence setup</CardDescription>
        </CardHeader>
        <CardContent>
          {opportunities.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-2xl font-bold">{opportunities[0].symbol}</h3>
                    <Badge variant={opportunities[0].side === 'long' ? 'success' : 'destructive'} className="text-base">
                      {opportunities[0].side.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-muted-foreground">{opportunities[0].ai_rationale}</p>
                </div>
                <Badge variant="success" className="text-lg px-3 py-1">
                  {opportunities[0].confidence}% Confidence
                </Badge>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t">
                <div>
                  <p className="text-sm text-muted-foreground">Entry Price</p>
                  <p className="text-xl font-bold">${opportunities[0].entry_price}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Stop Loss</p>
                  <p className="text-xl font-bold text-red-500">${opportunities[0].stop_loss}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Take Profit</p>
                  <p className="text-xl font-bold text-green-500">${opportunities[0].take_profit}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Risk:Reward</p>
                  <p className="text-xl font-bold">{opportunities[0].risk_reward.toFixed(2)}</p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
