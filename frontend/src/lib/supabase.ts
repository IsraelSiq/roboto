import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// Tipos das tabelas
export type Signal = {
  id: string
  created_at: string
  symbol: string
  timeframe: string
  technical_signal: 'CALL' | 'PUT' | 'AGUARDAR'
  sentiment_signal: 'positive' | 'negative' | 'neutral'
  final_decision: 'CALL_FORTE' | 'PUT_FORTE' | 'CALL_FRACO' | 'PUT_FRACO' | 'AGUARDAR'
  rsi: number | null
  macd: number | null
  ema50: number | null
  current_price: number | null
  sentiment_score: number | null
  reason: string | null
  cycle: number | null
  mode: 'paper' | 'testnet' | 'real'
}

export type Trade = {
  id: string
  created_at: string
  closed_at: string | null
  signal_id: string | null
  symbol: string
  direction: 'CALL' | 'PUT'
  strength: 'FORTE' | 'FRACO'
  entry_price: number | null
  exit_price: number | null
  pnl_pct: number | null
  result: 'WIN' | 'LOSS' | 'PENDING'
  mode: 'paper' | 'testnet' | 'real'
}

export type BacktestRun = {
  id: string
  created_at: string
  symbol: string
  timeframe: string
  period_start: string
  period_end: string
  total_trades: number | null
  win_rate: number | null
  profit_factor: number | null
  max_drawdown: number | null
  sharpe_ratio: number | null
  approved: boolean
  notes: string | null
}
