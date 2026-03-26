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

export interface SentimentSpike {
  asset: string;
  old_score: number;
  new_score: number;
  change: number;
  direction: 'bullish' | 'bearish';
  severity: 'minor' | 'major' | 'extreme';
  timestamp: string;
  sources_contributing: string[];
}

export interface SentimentSpikesResponse {
  spikes: SentimentSpike[];
  detector_config: {
    spike_threshold: number;
    window_minutes: number;
    cooldown_minutes: number;
    max_history: number;
  };
  active_cooldowns: Array<{ asset: string; cooldown_remaining_seconds: number }>;
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

  async getSentimentSpikes(): Promise<SentimentSpikesResponse> {
    return this.request<SentimentSpikesResponse>('/api/sentiment/spikes');
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
}

export const apiClient = new ApiClient();
