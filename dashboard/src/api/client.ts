const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface BotStatus {
  status: string;
  mode: 'dry-run' | 'live';
  uptime: number;
  last_heartbeat: string;
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
    return this.request<BotStatus>('/api/status');
  }

  async getPositions(): Promise<Position[]> {
    return this.request<Position[]>('/api/positions');
  }

  async getTrades(limit = 50): Promise<Trade[]> {
    return this.request<Trade[]>(`/api/trades?limit=${limit}`);
  }

  async getWebhookEvents(limit = 50): Promise<WebhookEvent[]> {
    return this.request<WebhookEvent[]>(`/api/webhook-events?limit=${limit}`);
  }

  async getOpportunities(): Promise<Opportunity[]> {
    return this.request<Opportunity[]>('/api/opportunities');
  }

  async getPnLHistory(period = '24h'): Promise<PnLData[]> {
    return this.request<PnLData[]>(`/api/pnl-history?period=${period}`);
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
