import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Minus, RefreshCw, AlertCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { apiClient } from '@/api/client'

const BULLISH_THRESHOLD = 0.3
const BEARISH_THRESHOLD = -0.3
const REFRESH_INTERVAL_MS = 60_000 // 60 seconds

function getSentimentColorClass(score: number): string {
  if (score > BULLISH_THRESHOLD) return 'text-green-400'
  if (score < BEARISH_THRESHOLD) return 'text-red-400'
  return 'text-gray-400'
}

function getBarColorClass(score: number): string {
  if (score > BULLISH_THRESHOLD) return 'bg-green-500'
  if (score < BEARISH_THRESHOLD) return 'bg-red-500'
  return 'bg-gray-400'
}

/** Map a provider class name to a human-readable label. */
function providerLabel(name: string): string {
  const map: Record<string, string> = {
    CryptoPanicSentimentProvider: 'CryptoPanic',
    RedditSentimentProvider: 'Reddit',
    TwitterSentimentProvider: 'Twitter/X',
    FearGreedProvider: 'Fear & Greed',
    MockSentimentProvider: 'Demo (Mock)',
  }
  return map[name] ?? name
}

function ScoreBar({ score }: { score: number }) {
  const pct = ((score + 1) / 2) * 100
  return (
    <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${getBarColorClass(score)}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function ScoreBadge({ score }: { score: number }) {
  if (score > BULLISH_THRESHOLD) {
    return (
      <Badge className="bg-green-500/20 text-green-400 border-green-500/30 gap-1">
        <TrendingUp className="h-3 w-3" />
        Bullish
      </Badge>
    )
  }
  if (score < BEARISH_THRESHOLD) {
    return (
      <Badge className="bg-red-500/20 text-red-400 border-red-500/30 gap-1">
        <TrendingDown className="h-3 w-3" />
        Bearish
      </Badge>
    )
  }
  return (
    <Badge className="bg-gray-500/20 text-gray-400 border-gray-500/30 gap-1">
      <Minus className="h-3 w-3" />
      Neutral
    </Badge>
  )
}

export function SentimentWidget() {
  const [combinedScore, setCombinedScore] = useState<number>(0)
  const [providers, setProviders] = useState<string[]>([])
  const [assetScores, setAssetScores] = useState<Record<string, number>>({})
  const [lastUpdated, setLastUpdated] = useState<string>(new Date().toISOString())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSentiment = async () => {
    try {
      const data = await apiClient.getSentimentSummary()
      const overview = data.overview as { combined_score?: number; score?: number } | undefined
      const score = overview?.combined_score ?? overview?.score ?? 0
      setCombinedScore(score)
      setProviders(data.providers ?? [])

      const scores: Record<string, number> = {}
      if (data.assets) {
        for (const [asset, info] of Object.entries(data.assets)) {
          if (info && typeof info === 'object' && 'score' in info) {
            scores[asset] = (info as { score: number }).score
          }
        }
      }
      setAssetScores(scores)
      setLastUpdated(new Date().toISOString())
      setError(null)
    } catch (err) {
      setError('Unable to load sentiment data')
      console.error('Sentiment fetch error:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSentiment()
    const interval = setInterval(fetchSentiment, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">Market Sentiment</CardTitle>
            <CardDescription className="text-xs">
              Multi-source weighted analysis
            </CardDescription>
          </div>
          {!loading && !error && <ScoreBadge score={combinedScore} />}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading sentiment…
          </div>
        )}

        {error && !loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
            <AlertCircle className="h-4 w-4 text-yellow-500" />
            {error}
          </div>
        )}

        {!loading && !error && (
          <>
            {/* Combined score */}
            <div className="rounded-lg bg-muted/50 p-3 space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">Combined Score</span>
                <span className={`font-bold tabular-nums ${getSentimentColorClass(combinedScore)}`}>
                  {combinedScore >= 0 ? '+' : ''}{combinedScore.toFixed(3)}
                </span>
              </div>
              <ScoreBar score={combinedScore} />
            </div>

            {/* Per-provider / per-asset rows */}
            <div className="space-y-3">
              {providers.length > 0 ? (
                providers.map((p) => {
                  const label = providerLabel(p)
                  // The sentiment API returns aggregated scores per asset rather than per provider.
                  // We show the average asset score as a proxy for this provider's contribution
                  // until the API exposes per-provider breakdowns.
                  const scores = Object.values(assetScores)
                  const score = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : combinedScore
                  return (
                    <div key={p} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground font-medium">{label}</span>
                        <div className="flex items-center gap-2">
                          <span className={`tabular-nums font-semibold ${getSentimentColorClass(score)}`}>
                            {score >= 0 ? '+' : ''}{score.toFixed(3)}
                          </span>
                          <span className="text-muted-foreground/60">
                            {new Date(lastUpdated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                      </div>
                      <ScoreBar score={score} />
                    </div>
                  )
                })
              ) : (
                <p className="text-xs text-muted-foreground">No sentiment providers active</p>
              )}
            </div>

            {/* Last updated */}
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <RefreshCw className="h-3 w-3" />
              Updated {new Date(lastUpdated).toLocaleTimeString()}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
