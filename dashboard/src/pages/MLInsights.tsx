import { useEffect, useState, useCallback } from 'react'
import {
  Brain, CheckCircle, AlertTriangle, RefreshCw, PlayCircle, Clock,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line,
} from 'recharts'
import { apiClient } from '@/api/client'
import type {
  MLModelStatus,
  MLFeatureImportance,
  MLBacktestMetrics,
  MLRecentPredictions,
  MLFeature,
  RollingAccuracy,
  MLPrediction,
} from '@/api/client'

// ---------------------------------------------------------------------------
// Small helper components
// ---------------------------------------------------------------------------

function MetricCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg bg-muted/50 p-3 text-center">
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
      {sub && <p className="text-xs text-muted-foreground/70 mt-0.5">{sub}</p>}
    </div>
  )
}

function SignalBadge({ signal }: { signal: string }) {
  if (signal === 'buy' || signal === 'long')
    return <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Buy</Badge>
  if (signal === 'sell' || signal === 'short')
    return <Badge className="bg-red-500/20 text-red-400 border-red-500/30">Sell</Badge>
  return <Badge variant="secondary">Hold</Badge>
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  if (outcome === 'win')
    return <Badge className="bg-green-500/20 text-green-400 border-green-500/30 text-xs">Win</Badge>
  if (outcome === 'loss')
    return <Badge className="bg-red-500/20 text-red-400 border-red-500/30 text-xs">Loss</Badge>
  return <Badge variant="outline" className="text-xs">Pending</Badge>
}

const CHART_STYLE = {
  backgroundColor: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: '8px',
  fontSize: '12px',
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function MLInsights() {
  const [modelStatus, setModelStatus] = useState<MLModelStatus | null>(null)
  const [featureImportance, setFeatureImportance] = useState<MLFeatureImportance | null>(null)
  const [backtestMetrics, setBacktestMetrics] = useState<MLBacktestMetrics | null>(null)
  const [predictions, setPredictions] = useState<MLRecentPredictions | null>(null)
  const [loading, setLoading] = useState(true)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState(new Date())

  const fetchData = useCallback(async () => {
    try {
      const [status, importance, preds] = await Promise.all([
        apiClient.getMLStatus(),
        apiClient.getMLFeatureImportance(),
        apiClient.getRecentMLPredictions(20),
      ])
      setModelStatus(status)
      setFeatureImportance(importance)
      setPredictions(preds)
      setError(null)
      setLastRefresh(new Date())
    } catch (err) {
      setError('Unable to load ML data. Is the backend running?')
      console.error('MLInsights fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  const runBacktest = useCallback(async () => {
    setBacktestLoading(true)
    try {
      const result = await apiClient.runMLBacktest({
        start_date: '2025-01-01',
        end_date: new Date().toISOString().slice(0, 10),
        pair: 'BTC/USDT:USDT',
        timeframe: '5m',
      })
      if (result.success) {
        setBacktestMetrics(result.metrics)
      }
    } catch (err) {
      console.error('Backtest error:', err)
    } finally {
      setBacktestLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Auto-run backtest on first mount only
  const backtestRan = useState(false)
  useEffect(() => {
    if (!backtestRan[0]) {
      backtestRan[1](true)
      runBacktest()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const topFeatures = (featureImportance?.features ?? [])
    .slice(0, 15)
    .map((f: MLFeature) => ({ feature: f.name, importance: f.importance }))

  const confDist = backtestMetrics?.confidence_distribution ?? []
  const rollingAcc = (backtestMetrics?.rolling_accuracy ?? []).map((p: RollingAccuracy) => ({
    t: new Date(p.window_start).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    accuracy: +(p.accuracy * 100).toFixed(1),
  }))

  const cm = backtestMetrics?.confusion_matrix
  const cmTotal = cm ? cm.tp + cm.fp + cm.tn + cm.fn : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">ML Insights</h1>
          <p className="text-muted-foreground text-sm">
            Model performance, feature analysis &amp; backtesting
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {lastRefresh.toLocaleTimeString()}
          </span>
          <Button size="sm" variant="outline" onClick={fetchData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

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
            {modelStatus?.model_loaded ? (
              <Badge className="bg-green-500/20 text-green-400 border-green-500/30 gap-1">
                <CheckCircle className="h-3 w-3" />
                Loaded
              </Badge>
            ) : (
              <Badge variant="secondary" className="gap-1">
                <AlertTriangle className="h-3 w-3" />
                Demo Mode
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <MetricCard
              label="Version"
              value={modelStatus?.model_version ?? 'N/A'}
            />
            <MetricCard
              label="Features"
              value={modelStatus?.features_count ?? 0}
            />
            <MetricCard
              label="Last Trained"
              value={
                modelStatus?.last_trained
                  ? new Date(modelStatus.last_trained).toLocaleDateString()
                  : 'N/A'
              }
            />
            <MetricCard
              label="Training Samples"
              value={
                modelStatus?.training_samples
                  ? modelStatus.training_samples.toLocaleString()
                  : 'N/A'
              }
            />
          </div>
          {modelStatus?.is_demo && (
            <p className="mt-3 text-xs text-muted-foreground flex items-center gap-1">
              <AlertTriangle className="h-3 w-3 shrink-0 text-yellow-400" />
              No trained model loaded. Set <code className="mx-1 rounded bg-muted px-1">ML_MODEL_PATH</code> to enable real predictions. Showing demo data.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Performance Metrics + Run Backtest */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <CardTitle className="text-base lg:text-lg">Performance Metrics</CardTitle>
              <CardDescription>
                {backtestMetrics
                  ? `Based on ${backtestMetrics.total_predictions.toLocaleString()} predictions${backtestMetrics.is_demo ? ' (demo)' : ''}`
                  : 'Run a backtest to see metrics'}
              </CardDescription>
            </div>
            <Button
              size="sm"
              onClick={runBacktest}
              disabled={backtestLoading}
              className="gap-1.5"
            >
              {backtestLoading ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <PlayCircle className="h-4 w-4" />
              )}
              {backtestLoading ? 'Running…' : 'Run Backtest'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {backtestMetrics ? (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <MetricCard label="Accuracy" value={`${(backtestMetrics.accuracy * 100).toFixed(1)}%`} />
              <MetricCard label="Precision" value={`${(backtestMetrics.precision * 100).toFixed(1)}%`} />
              <MetricCard label="Recall" value={`${(backtestMetrics.recall * 100).toFixed(1)}%`} />
              <MetricCard label="F1 Score" value={`${(backtestMetrics.f1_score * 100).toFixed(1)}%`} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-6">
              Click "Run Backtest" to compute metrics
            </p>
          )}
        </CardContent>
      </Card>

      {backtestMetrics && (
        <>
          {/* Profit Impact */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base lg:text-lg">Profit Impact</CardTitle>
              <CardDescription>Simulated P&amp;L with ML filter ON vs OFF</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3 mb-4">
                <MetricCard
                  label="With ML Filter"
                  value={`${backtestMetrics.profit_with_ml > 0 ? '+' : ''}${backtestMetrics.profit_with_ml.toFixed(1)}%`}
                />
                <MetricCard
                  label="Without ML Filter"
                  value={`${backtestMetrics.profit_without_ml > 0 ? '+' : ''}${backtestMetrics.profit_without_ml.toFixed(1)}%`}
                />
                <MetricCard
                  label="Improvement"
                  value={`${backtestMetrics.profit_improvement_pct > 0 ? '+' : ''}${backtestMetrics.profit_improvement_pct.toFixed(1)}%`}
                />
              </div>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart
                  data={[
                    { name: 'With ML', value: backtestMetrics.profit_with_ml },
                    { name: 'Without ML', value: backtestMetrics.profit_without_ml },
                  ]}
                  margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} tickFormatter={v => `${v}%`} />
                  <Tooltip contentStyle={CHART_STYLE} formatter={(v: number | undefined) => [`${(v ?? 0).toFixed(1)}%`, 'P&L']} />
                  <Bar dataKey="value" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Confusion Matrix */}
          {cm && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base lg:text-lg">Confusion Matrix</CardTitle>
                <CardDescription>Long signal classification results</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-2 max-w-xs mx-auto">
                  {[
                    { label: 'True Positive', value: cm.tp, bg: 'bg-green-500/20 text-green-400' },
                    { label: 'False Positive', value: cm.fp, bg: 'bg-red-500/15 text-red-400' },
                    { label: 'False Negative', value: cm.fn, bg: 'bg-orange-500/15 text-orange-400' },
                    { label: 'True Negative', value: cm.tn, bg: 'bg-blue-500/15 text-blue-400' },
                  ].map(cell => (
                    <div key={cell.label} className={`rounded-lg p-4 text-center ${cell.bg}`}>
                      <p className="text-2xl font-bold tabular-nums">{cell.value.toLocaleString()}</p>
                      <p className="text-xs mt-1">{cell.label}</p>
                      {cmTotal > 0 && (
                        <p className="text-xs opacity-70">{((cell.value / cmTotal) * 100).toFixed(1)}%</p>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Rolling Accuracy */}
            {rollingAcc.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base lg:text-lg">Rolling Accuracy</CardTitle>
                  <CardDescription>Accuracy over time (100-trade window)</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={rollingAcc} margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="t" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                      <YAxis domain={['dataMin - 5', 100]} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} tickFormatter={v => `${v}%`} />
                      <Tooltip contentStyle={CHART_STYLE} formatter={(v: number | undefined) => [`${(v ?? 0).toFixed(1)}%`, 'Accuracy']} />
                      <Line type="monotone" dataKey="accuracy" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Confidence Distribution */}
            {confDist.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base lg:text-lg">Confidence Distribution</CardTitle>
                  <CardDescription>Prediction confidence histogram</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={confDist} margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={CHART_STYLE} />
                      <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Feature Importance */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base lg:text-lg">Feature Importance</CardTitle>
            <CardDescription>
              Top 15 features
              {featureImportance && featureImportance.method !== 'demo'
                ? ` (${featureImportance.method === 'shap' ? 'SHAP values' : 'built-in'})`
                : ' (demo)'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={topFeatures}
                layout="vertical"
                margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="hsl(var(--border))" />
                <XAxis
                  type="number"
                  tickFormatter={v => `${(v * 100).toFixed(0)}%`}
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
                  width={80}
                />
                <Tooltip
                  contentStyle={CHART_STYLE}
                  formatter={(v: number | undefined) => [`${((v ?? 0) * 100).toFixed(1)}%`, 'Importance']}
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
            <CardDescription>
              Last {predictions?.predictions.length ?? 0} ML signal classifications
              {predictions?.is_demo ? ' (demo)' : ''}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {(predictions?.predictions ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No predictions yet. Deploy a model to see live results.
              </p>
            ) : (
              <div className="space-y-2">
                {(predictions?.predictions ?? []).map((pred: MLPrediction, i: number) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2 text-sm"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium shrink-0">{pred.pair}</span>
                      <SignalBadge signal={pred.signal} />
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <OutcomeBadge outcome={pred.actual_outcome} />
                      <span className="tabular-nums text-xs text-muted-foreground w-12 text-right">
                        {(pred.confidence * 100).toFixed(0)}%
                      </span>
                      <span className="hidden sm:block text-xs text-muted-foreground">
                        {new Date(pred.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
