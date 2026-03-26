// In Docker, the dashboard nginx config proxies /api/, /alerts, and /tv/ to
// the webhook service, so relative URLs work out of the box. For local
// development (npm run dev), set VITE_API_URL=http://localhost:8000 in your
// .env file to point directly at the backend.
const API_BASE_URL = import.meta.env.VITE_API_URL ?? '';

export interface BotStatus {
  status: string;
  mode: 'dry-run' | 'live';
  uptime: number;
  last_heartbeat: string;
  exchange_connected?: boolean;
  exchange_name?: string | null;
  exchange_sandbox?: boolean;
  openai_configured?: boolean;
  sentiment_sources?: string[];
}

export interface Position {
  symbol: string;
  side: 'long' | 'short';
  size: number;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_percentage: number;
  leverage: number;
}

export interface Trade {
  id: string;
  timestamp: string;
  symbol: string;
  side: 'buy' | 'sell';
  size: number;
  price: number;
  pnl?: number;
  status: 'open' | 'closed';
  source?: 'exchange' | 'alerts';
}

export interface WebhookEvent {
  id: string;
  timestamp: string;
  action: string;
  symbol: string;
  details: Record<string, unknown>;
  processed: boolean;
}

export interface Opportunity {
  id: string;
  symbol: string;
  side: 'long' | 'short';
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_reward: number;
  ai_rationale?: string;
}

export interface PnLData {
  timestamp: string;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
}

export interface SentimentSummary {
  overview: {
    combined_score: number;
    trend: string;
    updated_at: string;
  };
  assets: Record<string, {
    score: number;
    trend: string;
    confidence: number;
    updated_at: string;
  }>;
  providers: string[];
}

export interface MLModelStatus {
  model_loaded: boolean;
  model_path: string | null;
  model_version: string | null;
  last_trained: string | null;
  features_count: number;
  training_samples: number | null;
  is_demo: boolean;
}

export interface MLFeature {
  name: string;
  importance: number;
  direction: 'positive' | 'neutral' | 'negative';
}

export interface MLFeatureImportance {
  features: MLFeature[];
  method: 'shap' | 'built_in' | 'demo';
  model_version: string | null;
}

export interface MLConfusionMatrix {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
}

export interface MLRollingAccuracyPoint {
  window_start: string;
  accuracy: number;
}

export interface MLConfidenceBucket {
  bucket: string;
  count: number;
}

export interface MLBacktestMetrics {
  precision: number;
  recall: number;
  f1_score: number;
  accuracy: number;
  total_predictions: number;
  confusion_matrix: MLConfusionMatrix;
  profit_with_ml: number;
  profit_without_ml: number;
  profit_improvement_pct: number;
  rolling_accuracy: MLRollingAccuracyPoint[];
  confidence_distribution: MLConfidenceBucket[];
  feature_importance: MLFeature[];
  feature_importance_method: string;
  is_demo: boolean;
  model_version: string | null;
  backtest_start: string | null;
  backtest_end: string | null;
  pair: string | null;
  timeframe: string | null;
}

export interface MLBacktestResult {
  success: boolean;
  metrics: MLBacktestMetrics;
}

export interface MLPrediction {
  timestamp: string;
  pair: string;
  signal: string;
  confidence: number;
  actual_outcome: string;
  features_used: number;
}

export interface MLRecentPredictions {
  predictions: MLPrediction[];
  total: number;
  is_demo: boolean;
}

export interface BacktestRequest {
  start_date?: string;
  end_date?: string;
  pair?: string;
  timeframe?: string;
}

export interface AdvisoryOutput {
  pair: string;
  timeframe: string;
  bias: string;
  confidence: number;
  rationale: string[];
  risks: string[];
  suggested_action: string;
  disclaimer: string;
  generated_at: string;
  technical_score: number;
  regime_alignment: number;
  sentiment_score: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  }

  async getBotStatus(): Promise<BotStatus> {
    const data = await this.request<{ success: boolean } & BotStatus>('/api/status');
    return data;
  }

  async getPositions(): Promise<Position[]> {
    const data = await this.request<{ success: boolean; positions: Position[] }>('/api/positions');
    return data.positions ?? [];
  }

  async getTrades(limit = 50): Promise<Trade[]> {
    const data = await this.request<{ success: boolean; trades: Trade[] }>(`/api/trades?limit=${limit}`);
    return data.trades ?? [];
  }

  async getWebhookEvents(limit = 50): Promise<WebhookEvent[]> {
    const data = await this.request<{ success: boolean; alerts: WebhookEvent[] }>(`/alerts?limit=${limit}`);
    return (data.alerts ?? []).map((a: WebhookEvent) => ({
      ...a,
      timestamp: a.timestamp ?? new Date().toISOString(),
      action: a.action ?? 'unknown',
    }));
  }

  async getOpportunities(): Promise<Opportunity[]> {
    const data = await this.request<{ success: boolean; opportunities: Opportunity[] }>('/api/opportunities');
    return data.opportunities ?? [];
  }

  async getPnLHistory(period = '24h'): Promise<PnLData[]> {
    const data = await this.request<{ success: boolean; data: PnLData[] }>(`/api/pnl-history?period=${period}`);
    return data.data ?? [];
  }

  async getSentimentSummary(): Promise<SentimentSummary> {
    return this.request<SentimentSummary>('/api/sentiment/summary');
  }

  async getAdvisory(pair: string, timeframe = '5m'): Promise<{ advisory: AdvisoryOutput; exchange_data: boolean }> {
    const encodedPair = encodeURIComponent(pair);
    return this.request<{ advisory: AdvisoryOutput; exchange_data: boolean }>(
      `/api/advisor/${encodedPair}?timeframe=${timeframe}`
    );
  }

  async toggleMode(mode: 'dry-run' | 'live'): Promise<{ success: boolean }> {
    return this.request('/api/toggle-mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    });
  }

  async emergencyStop(): Promise<{ success: boolean }> {
    return this.request('/api/emergency-stop', {
      method: 'POST',
    });
  }

  async pauseBot(): Promise<{ success: boolean }> {
    return this.request('/api/pause', {
      method: 'POST',
    });
  }

  async resumeBot(): Promise<{ success: boolean }> {
    return this.request('/api/resume', {
      method: 'POST',
    });
  }

  async getMLStatus(): Promise<MLModelStatus> {
    return this.request<MLModelStatus>('/api/ml/status');
  }

  async getMLFeatureImportance(): Promise<MLFeatureImportance> {
    return this.request<MLFeatureImportance>('/api/ml/feature-importance');
  }

  async runMLBacktest(params: BacktestRequest = {}): Promise<MLBacktestResult> {
    return this.request<MLBacktestResult>('/api/ml/backtest', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  async getRecentMLPredictions(limit = 50): Promise<MLRecentPredictions> {
    return this.request<MLRecentPredictions>(`/api/ml/predictions/recent?limit=${limit}`);
  }
}

export const apiClient = new ApiClient();
