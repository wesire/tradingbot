import { useEffect, useState, useCallback } from "react"
import { RefreshCw, AlertCircle } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { apiClient } from "@/api/client"
import type { Opportunity } from "@/api/client"

const REFRESH_INTERVAL_MS = 60_000

/** Normalize a confidence value to a percentage (0–100). */
const toConfidencePct = (c: number) => (c > 1 ? c : c * 100)

export function Opportunities() {
  const [filter, setFilter] = useState<'all' | 'long' | 'short'>('all')
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const fetchOpportunities = useCallback(async () => {
    try {
      const data = await apiClient.getOpportunities()
      setOpportunities(data)
      setError(null)
      setLastRefresh(new Date())
    } catch (err) {
      setError('Unable to load opportunities. Is the backend running?')
      console.error('Opportunities fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchOpportunities()
    const interval = setInterval(fetchOpportunities, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchOpportunities])

  const filteredOpportunities = opportunities.filter(
    opp => filter === 'all' || opp.side === filter
  )

  const getConfidenceColor = (confidence: number): 'success' | 'warning' | 'secondary' => {
    const pct = toConfidencePct(confidence)
    if (pct >= 75) return 'success'
    if (pct >= 60) return 'warning'
    return 'secondary'
  }

  const fmtConfidence = (confidence: number) => `${Math.round(toConfidencePct(confidence))}%`

  const fmtPrice = (price: number) => {
    if (!price) return '—'
    return price < 1 ? `$${price.toFixed(4)}` : `$${price.toFixed(2)}`
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Trading Opportunities</h1>
          <p className="text-muted-foreground">
            AI-identified potential trades based on market analysis
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
          {lastRefresh.toLocaleTimeString()}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-500">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

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
              {opportunities.length > 0
                ? fmtConfidence(
                    opportunities.reduce((sum, o) => sum + o.confidence, 0) / opportunities.length
                  )
                : '—'}
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
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Loading opportunities…
            </div>
          ) : (
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
                  <TableHead>Rationale</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredOpportunities.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center text-muted-foreground">
                      {opportunities.length === 0
                        ? 'No opportunities scored above threshold'
                        : 'No opportunities match your filter'}
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
                          {fmtConfidence(opp.confidence)}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono">{fmtPrice(opp.entry_price)}</TableCell>
                      <TableCell className="font-mono text-red-500">{fmtPrice(opp.stop_loss)}</TableCell>
                      <TableCell className="font-mono text-green-500">{fmtPrice(opp.take_profit)}</TableCell>
                      <TableCell className="font-bold">{(opp.risk_reward ?? 0).toFixed(2)}</TableCell>
                      <TableCell className="max-w-xs text-sm text-muted-foreground">
                        {opp.ai_rationale ?? '—'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {!loading && filteredOpportunities.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Top Opportunity</CardTitle>
            <CardDescription>Highest confidence setup</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-2xl font-bold">{filteredOpportunities[0].symbol}</h3>
                    <Badge variant={filteredOpportunities[0].side === 'long' ? 'success' : 'destructive'} className="text-base">
                      {filteredOpportunities[0].side.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-muted-foreground">{filteredOpportunities[0].ai_rationale ?? '—'}</p>
                </div>
                <Badge variant="success" className="text-lg px-3 py-1">
                  {fmtConfidence(filteredOpportunities[0].confidence)} Confidence
                </Badge>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t">
                <div>
                  <p className="text-sm text-muted-foreground">Entry Price</p>
                  <p className="text-xl font-bold">{fmtPrice(filteredOpportunities[0].entry_price)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Stop Loss</p>
                  <p className="text-xl font-bold text-red-500">{fmtPrice(filteredOpportunities[0].stop_loss)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Take Profit</p>
                  <p className="text-xl font-bold text-green-500">{fmtPrice(filteredOpportunities[0].take_profit)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Risk:Reward</p>
                  <p className="text-xl font-bold">{(filteredOpportunities[0].risk_reward ?? 0).toFixed(2)}</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

