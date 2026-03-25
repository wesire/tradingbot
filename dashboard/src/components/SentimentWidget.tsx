import { TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

const BULLISH_THRESHOLD = 0.3
const BEARISH_THRESHOLD = -0.3

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

interface ProviderScore {
  name: string
  score: number
  lastUpdated: string
}

interface SentimentWidgetProps {
  providers?: ProviderScore[]
  combinedScore?: number
  lastUpdated?: string
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

const DEFAULT_PROVIDERS: ProviderScore[] = [
  { name: 'CryptoPanic', score: 0.42, lastUpdated: new Date(Date.now() - 5 * 60000).toISOString() },
  { name: 'Reddit', score: 0.18, lastUpdated: new Date(Date.now() - 12 * 60000).toISOString() },
  { name: 'Twitter/X', score: 0.55, lastUpdated: new Date(Date.now() - 8 * 60000).toISOString() },
]

export function SentimentWidget({
  providers = DEFAULT_PROVIDERS,
  combinedScore = 0.38,
  lastUpdated = new Date().toISOString(),
}: SentimentWidgetProps) {
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
          <ScoreBadge score={combinedScore} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
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

        {/* Per-provider scores */}
        <div className="space-y-3">
          {providers.map((p) => (
            <div key={p.name} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground font-medium">{p.name}</span>
                <div className="flex items-center gap-2">
                  <span className={`tabular-nums font-semibold ${getSentimentColorClass(p.score)}`}>
                    {p.score >= 0 ? '+' : ''}{p.score.toFixed(3)}
                  </span>
                  <span className="text-muted-foreground/60">
                    {new Date(p.lastUpdated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
              <ScoreBar score={p.score} />
            </div>
          ))}
        </div>

        {/* Last updated */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <RefreshCw className="h-3 w-3" />
          Updated {new Date(lastUpdated).toLocaleTimeString()}
        </div>
      </CardContent>
    </Card>
  )
}
