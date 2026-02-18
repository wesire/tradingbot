import { Brain, TrendingUp, AlertTriangle, Info } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

export function AIOverview() {
  // Mock AI guidance data
  const aiGuidance = {
    overall_sentiment: 'bullish',
    confidence: 78,
    recommendations: [
      {
        type: 'position',
        symbol: 'BTC/USDT',
        action: 'hold',
        rationale: 'Current position showing strong momentum. RSI indicates continued strength.',
        confidence: 82,
      },
      {
        type: 'entry',
        symbol: 'ETH/USDT',
        action: 'consider_long',
        rationale: 'Breaking out of consolidation pattern. Volume confirms strength.',
        confidence: 75,
      },
      {
        type: 'exit',
        symbol: 'SOL/USDT',
        action: 'take_profit',
        rationale: 'Target reached. Overbought conditions suggest potential reversal.',
        confidence: 70,
      },
    ],
    market_analysis: {
      trend: 'Uptrend',
      volatility: 'Medium',
      key_levels: {
        support: 44500,
        resistance: 47000,
      },
    },
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 75) return 'success'
    if (confidence >= 50) return 'warning'
    return 'destructive'
  }

  const getSentimentBadge = (sentiment: string) => {
    const variants: Record<string, 'success' | 'destructive' | 'secondary'> = {
      bullish: 'success',
      bearish: 'destructive',
      neutral: 'secondary',
    }
    return variants[sentiment] || 'secondary'
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">AI Advisor</h1>
        <p className="text-muted-foreground">
          AI-powered market analysis and trading guidance
        </p>
      </div>

      <Alert variant="warning">
        <Info className="h-4 w-4" />
        <AlertTitle>Advisory Only</AlertTitle>
        <AlertDescription>
          AI recommendations are for informational purposes only. Always verify signals and use proper risk management.
          This is not financial advice.
        </AlertDescription>
      </Alert>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Overall Sentiment</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <Badge variant={getSentimentBadge(aiGuidance.overall_sentiment)} className="text-lg px-3 py-1">
                {aiGuidance.overall_sentiment.toUpperCase()}
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
              <div className="text-3xl font-bold">{aiGuidance.confidence}%</div>
              <TrendingUp className="h-8 w-8 text-muted-foreground" />
            </div>
            <div className="mt-2 h-2 bg-secondary rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary transition-all"
                style={{ width: `${aiGuidance.confidence}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Active Recommendations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{aiGuidance.recommendations.length}</div>
            <p className="text-sm text-muted-foreground mt-1">signals detected</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Market Analysis</CardTitle>
          <CardDescription>Current market conditions and key levels</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Trend</p>
              <p className="text-2xl font-bold">{aiGuidance.market_analysis.trend}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Volatility</p>
              <p className="text-2xl font-bold">{aiGuidance.market_analysis.volatility}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Key Levels</p>
              <div className="space-y-1 mt-1">
                <p className="text-sm">
                  <span className="text-muted-foreground">Support:</span>{' '}
                  <span className="font-mono">${aiGuidance.market_analysis.key_levels.support}</span>
                </p>
                <p className="text-sm">
                  <span className="text-muted-foreground">Resistance:</span>{' '}
                  <span className="font-mono">${aiGuidance.market_analysis.key_levels.resistance}</span>
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>AI Recommendations</CardTitle>
          <CardDescription>Actionable trading signals and guidance</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {aiGuidance.recommendations.map((rec, index) => (
              <Card key={index}>
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <h4 className="font-semibold">{rec.symbol}</h4>
                        <Badge variant={rec.action.includes('long') || rec.action === 'hold' ? 'success' : 'destructive'}>
                          {rec.action.replace('_', ' ').toUpperCase()}
                        </Badge>
                        <Badge variant={getConfidenceColor(rec.confidence)}>
                          {rec.confidence}% confident
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">{rec.rationale}</p>
                    </div>
                    <Brain className="h-5 w-5 text-muted-foreground ml-4" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Strategy Insights</CardTitle>
          <CardDescription>AI-detected patterns and trends</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="h-2 w-2 rounded-full bg-green-500 mt-2" />
              <div>
                <p className="font-medium">Strong Momentum Detected</p>
                <p className="text-sm text-muted-foreground">
                  BTC showing consistent higher highs and higher lows across multiple timeframes
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="h-2 w-2 rounded-full bg-yellow-500 mt-2" />
              <div>
                <p className="font-medium">Volume Confirmation</p>
                <p className="text-sm text-muted-foreground">
                  Rising volume supporting the current price action in ETH
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="h-2 w-2 rounded-full bg-blue-500 mt-2" />
              <div>
                <p className="font-medium">Key Support Holding</p>
                <p className="text-sm text-muted-foreground">
                  Major support level at $44,500 has been tested and held multiple times
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Risk Disclaimer</AlertTitle>
        <AlertDescription>
          AI recommendations are based on historical data and technical analysis. They do not guarantee future performance.
          Always use proper risk management and never risk more than you can afford to lose.
        </AlertDescription>
      </Alert>
    </div>
  )
}
