const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

export interface BotStatus {
  running: boolean
  symbol: string
  interval: string
  balance: number
  initial_balance: number
  drawdown_pct: number
  trades_today: number
  total_trades: number
  consecutive_losses: number
  open_trade: object | null
}

export interface Trade {
  id: string
  symbol: string
  direction: 'CALL' | 'PUT'
  strength: string
  entry_price: number
  exit_price: number | null
  stop_loss: number
  take_profit: number
  pnl_pct: number | null
  result: 'WIN' | 'LOSS' | null
  opened_at: string
  closed_at: string | null
}

export interface Metrics {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  profit_factor: number
  max_drawdown: number
  sharpe_ratio: number
  avg_win_pct: number
  avg_loss_pct: number
  total_pnl_pct: number
  approved: boolean
}

export const api = {
  status: () => get<BotStatus>('/status'),
  trades: () => get<Trade[]>('/trades'),
  tradesHistory: () => get<Trade[]>('/trades/history'),
  metrics: () => get<Metrics>('/metrics'),
  exportCSV: () => `${API_URL}/reports/export/csv`,
}
