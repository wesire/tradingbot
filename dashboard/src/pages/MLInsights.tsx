import { Brain, CheckCircle, Clock, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

// Mock data — replace with real API calls
const mockModelStatus = {
  loaded: true,
  version: 'v1.2.0',
  lastTrained: new Date(Date.now() - 2 * 24 * 3600000).toISOString(),
  algorithm: 'XGBoost',
  features: 22,
}

const mockPredictions = [
  { id: '1', symbol: 'BTC/USDT', signal: 'long', confidence: 0.87, timestamp: new Date(Date.now() - 300000).toISOString() },
  { id: '2', symbol: 'ETH/USDT', signal: 'neutral', confidence: 0.61, timestamp: new Date(Date.now() - 600000).toISOString() },
  { id: '3', symbol: 'SOL/USDT', signal: 'short', confidence: 0.74, timestamp: new Date(Date.now() - 900000).toISOString() },
  { id: '4', symbol: 'BTC/USDT', signal: 'long', confidence: 0.92, timestamp: new Date(Date.now() - 1200000).toISOString() },
  { id: '5', symbol: 'ETH/USDT', signal: 'long', confidence: 0.78, timestamp: new Date(Date.now() - 1500000).toISOString() },
]

const mockFeatureImportance = [
  { feature: 'RSI(14)', importance: 0.18 },
  { feature: 'MACD', importance: 0.15 },
  { feature: 'BB Width', importance: 0.13 },
  { feature: 'Vol Ratio', importance: 0.11 },
  { feature: 'ATR', importance: 0.09 },
  { feature: 'EMA Slope', importance: 0.08 },
  { feature: 'ADX', importance: 0.07 },
  { feature: 'OBV', importance: 0.06 },
  { feature: 'Momentum', importance: 0.05 },
  { feature: 'Sentiment', importance: 0.08 },
].sort((a, b) => b.importance - a.importance)

const mockPerformance = {
  accuracy: 0.673,
  precision: 0.712,
  recall: 0.641,
  f1: 0.675,
  totalPredictions: 1247,
}

function SignalBadge({ signal }: { signal: string }) {
  if (signal === 'long') return <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Long</Badge>
  if (signal === 'short') return <Badge className="bg-red-500/20 text-red-400 border-red-500/30">Short</Badge>
  return <Badge variant="secondary">Neutral</Badge>
}

function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 0.8 ? 'bg-green-500' : value >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="text-xs tabular-nums">{(value * 100).toFixed(0)}%</span>
    </div>
  )
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-muted/50 p-3 text-center">
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
    </div>
  )
}

export function MLInsights() {
  const daysSinceTrained = Math.floor(
    (Date.now() - new Date(mockModelStatus.lastTrained).getTime()) / (24 * 3600000)
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">ML Insights</h1>
        <p className="text-muted-foreground text-sm lg:text-base">
          Machine learning model status, predictions, and feature analysis
        </p>
      </div>

      {/* Model Status */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-base lg:text-lg">
                <Brain className="h-5 w-5 text-primary" />
                Model Status
              </CardTitle>
              <CardDescription>Current ML model information</CardDescription>
            </div>
            {mockModelStatus.loaded ? (
              <Badge className="bg-green-500/20 text-green-400 border-green-500/30 gap-1">
                <CheckCircle className="h-3 w-3" />
                Loaded
              </Badge>
            ) : (
              <Badge variant="destructive">Not Loaded</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <MetricCard label="Version" value={mockModelStatus.version} />
            <MetricCard label="Algorithm" value={mockModelStatus.algorithm} />
            <MetricCard label="Features" value={mockModelStatus.features} />
            <MetricCard
              label="Last Trained"
              value={`${daysSinceTrained}d ago`}
            />
          </div>
          {daysSinceTrained > 7 && (
            <div className="mt-3 flex items-center gap-2 text-xs text-yellow-400">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              Model was trained {daysSinceTrained} days ago. Consider retraining for best performance.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Performance Metrics */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base lg:text-lg">Model Performance</CardTitle>
          <CardDescription>
            Metrics computed on {mockPerformance.totalPredictions.toLocaleString()} historical predictions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <MetricCard label="Accuracy" value={`${(mockPerformance.accuracy * 100).toFixed(1)}%`} />
            <MetricCard label="Precision" value={`${(mockPerformance.precision * 100).toFixed(1)}%`} />
            <MetricCard label="Recall" value={`${(mockPerformance.recall * 100).toFixed(1)}%`} />
            <MetricCard label="F1 Score" value={`${(mockPerformance.f1 * 100).toFixed(1)}%`} />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Feature Importance */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base lg:text-lg">Feature Importance</CardTitle>
            <CardDescription>Top 10 most influential features (SHAP values)</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart
                data={mockFeatureImportance}
                layout="vertical"
                margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="hsl(var(--border))" />
                <XAxis
                  type="number"
                  tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="feature"
                  tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={false}
                  tickLine={false}
                  width={64}
                />
                <Tooltip
                  formatter={(v: number | undefined) => [`${((v ?? 0) * 100).toFixed(1)}%`, 'Importance'] as [string, string]}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
                <Bar dataKey="importance" fill="hsl(var(--primary))" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Recent Predictions */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base lg:text-lg">Recent Predictions</CardTitle>
            <CardDescription>Latest ML signal classifications</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {mockPredictions.map((pred) => (
                <div
                  key={pred.id}
                  className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-medium text-sm shrink-0">{pred.symbol}</span>
                    <SignalBadge signal={pred.signal} />
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <ConfidenceBar value={pred.confidence} />
                    <div className="hidden sm:flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {new Date(pred.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
