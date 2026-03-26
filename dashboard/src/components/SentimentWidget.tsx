import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Minus, RefreshCw, AlertCircle, Bell } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { apiClient } from '@/api/client'
import type { SentimentSpike } from '@/api/client'

const BULLISH_THRESHOLD = 0.3
const BEARISH_THRESHOLD = -0.3
const REFRESH_INTERVAL_MS = 60_000 // 60 seconds
const SPIKES_POLL_INTERVAL_MS = 30_000 // 30 seconds


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

function formatScore(score: number): string {
  return `${score >= 0 ? '+' : ''}${score.toFixed(2)}`
}

function formatSpikeMessage(spike: SentimentSpike): string {
  return `${spike.asset} Spike: ${formatScore(spike.old_score)} → ${formatScore(spike.new_score)} (${spike.direction.toUpperCase()}) — ${spike.severity.toUpperCase()}`
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

  const [recentSpikes, setRecentSpikes] = useState<SentimentSpike[]>([])
  const [newSpikeAlert, setNewSpikeAlert] = useState<SentimentSpike | null>(null)

  const fetchSpikes = async () => {
    try {
      const data = await apiClient.getSentimentSpikes()
      const spikes = data.spikes ?? []
      // If there are newer spikes than what we had, show a toast banner for the latest one
      if (spikes.length > 0) {
        const latest = spikes[0]
        const latestTime = new Date(latest.timestamp).getTime()
        const now = Date.now()
        // Show banner only for spikes within the last 5 minutes
        if (now - latestTime < 5 * 60 * 1000) {
          setNewSpikeAlert(latest)
        }
      }
      setRecentSpikes(spikes.slice(0, 5))
    } catch {
      // Spikes endpoint is optional — silently ignore errors
    }
  }

  useEffect(() => {
    fetchSpikes()
    const interval = setInterval(fetchSpikes, SPIKES_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])

  // Auto-dismiss the spike banner after 10 seconds, cleaning up on unmount
  useEffect(() => {
    if (!newSpikeAlert) return
    const timerId = setTimeout(() => setNewSpikeAlert(null), 10_000)
    return () => clearTimeout(timerId)
  }, [newSpikeAlert])

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
        {/* Spike alert banner / toast */}
        {newSpikeAlert && (
          <div
            className={`rounded-lg p-3 text-xs font-medium flex items-start gap-2 cursor-pointer
              ${newSpikeAlert.direction === 'bullish'
                ? 'bg-green-500/15 text-green-400 border border-green-500/30'
                : 'bg-red-500/15 text-red-400 border border-red-500/30'}`}
            onClick={() => setNewSpikeAlert(null)}
            title="Click to dismiss"
          >
            <Bell className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>{formatSpikeMessage(newSpikeAlert)}</span>
          </div>
        )}

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

        {/* Recent Alerts section */}
        {recentSpikes.length > 0 && (
          <div className="border-t border-border pt-3 space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1">
              <Bell className="h-3 w-3" />
              Recent Alerts
            </p>
            {recentSpikes.map((spike, idx) => (
              <div
                key={idx}
                className={`rounded-md px-2 py-1.5 text-xs flex items-start justify-between gap-2
                  ${spike.direction === 'bullish'
                    ? 'bg-green-500/10 text-green-400'
                    : 'bg-red-500/10 text-red-400'}`}
              >
                <span className="font-semibold shrink-0">{spike.asset}</span>
                <span className="tabular-nums">
                  {formatScore(spike.old_score)} → {formatScore(spike.new_score)}
                </span>
                <span className={`shrink-0 font-bold
                  ${spike.severity === 'extreme' ? 'text-red-500' : spike.severity === 'major' ? 'text-yellow-400' : ''}`}>
                  {spike.severity.toUpperCase()}
                </span>
                <span className="text-muted-foreground/70 shrink-0">
                  {new Date(spike.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
