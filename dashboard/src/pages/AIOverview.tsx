import { useEffect, useState, useCallback } from "react"
import { Brain, TrendingUp, AlertTriangle, Info, RefreshCw, AlertCircle } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { apiClient } from "@/api/client"
import type { AdvisoryOutput } from "@/api/client"

const DEFAULT_PAIR = 'BTC/USDT:USDT'
const REFRESH_INTERVAL_MS = 60_000

export function AIOverview() {
  const [advisory, setAdvisory] = useState<AdvisoryOutput | null>(null)
  const [exchangeData, setExchangeData] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const fetchAdvisory = useCallback(async () => {
    try {
      const result = await apiClient.getAdvisory(DEFAULT_PAIR)
      setAdvisory(result.advisory)
      setExchangeData(result.exchange_data)
      setError(null)
      setLastRefresh(new Date())
    } catch (err) {
      setError('Unable to load AI advisor. Is the backend running?')
      console.error('AI advisor fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAdvisory()
    const interval = setInterval(fetchAdvisory, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchAdvisory])

  const getBiasVariant = (bias: string): 'success' | 'destructive' | 'secondary' => {
    const map: Record<string, 'success' | 'destructive' | 'secondary'> = {
      bullish: 'success',
      bearish: 'destructive',
      neutral: 'secondary',
    }
    return map[bias] ?? 'secondary'
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">AI Advisor</h1>
          <p className="text-muted-foreground">
            AI-powered market analysis and trading guidance
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
          {lastRefresh.toLocaleTimeString()}
        </div>
      </div>

      <Alert variant="warning">
        <Info className="h-4 w-4" />
        <AlertTitle>Advisory Only</AlertTitle>
        <AlertDescription>
          AI recommendations are for informational purposes only. Always verify signals and use proper risk management.
          This is not financial advice.
        </AlertDescription>
      </Alert>

      {!exchangeData && !loading && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Exchange not connected — analysis uses default market context. Add <code className="font-mono">EXCHANGE_API_KEY</code> for live data.
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-500">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading AI analysis…
        </div>
      )}

      {!loading && advisory && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Market Bias</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <Badge variant={getBiasVariant(advisory.bias)} className="text-lg px-3 py-1">
                    {advisory.bias.toUpperCase()}
                  </Badge>
                  <Brain className="h-8 w-8 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">AI Confidence</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div className="text-3xl font-bold">{Math.round(advisory.confidence * 100)}%</div>
                  <TrendingUp className="h-8 w-8 text-muted-foreground" />
                </div>
                <div className="mt-2 h-2 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${advisory.confidence * 100}%` }}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Suggested Action</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold capitalize">
                  {advisory.suggested_action.replace(/_/g, ' ')}
                </div>
                <p className="text-sm text-muted-foreground mt-1">{DEFAULT_PAIR}</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Signal Scores</CardTitle>
              <CardDescription>Breakdown of technical, regime, and sentiment analysis</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3">
                {[
                  { label: 'Technical Score', value: advisory.technical_score },
                  { label: 'Regime Alignment', value: advisory.regime_alignment },
                  { label: 'Sentiment Score', value: advisory.sentiment_score },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-sm font-medium text-muted-foreground">{label}</p>
                    <p className="text-2xl font-bold">{(value * 100).toFixed(0)}%</p>
                    <div className="mt-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${Math.min(100, Math.abs(value) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {advisory.rationale.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Analysis Rationale</CardTitle>
                <CardDescription>Why the AI has this view</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {advisory.rationale.map((point, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <div className="h-2 w-2 rounded-full bg-primary mt-2 shrink-0" />
                      <p className="text-sm text-muted-foreground">{point}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {advisory.risks.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Key Risks</CardTitle>
                <CardDescription>Factors that could invalidate the analysis</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {advisory.risks.map((risk, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <div className="h-2 w-2 rounded-full bg-yellow-500 mt-2 shrink-0" />
                      <p className="text-sm text-muted-foreground">{risk}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Risk Disclaimer</AlertTitle>
            <AlertDescription>{advisory.disclaimer}</AlertDescription>
          </Alert>
        </>
      )}
    </div>
  )
}

