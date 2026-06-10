import { api } from '@/services/api'
import { MetricCard } from '@/components/MetricCard'
import { formatCurrency, formatPct } from '@/lib/utils'

export const revalidate = 30

export default async function DashboardPage() {
  let status = null
  let metrics = null

  try { status = await api.status() } catch {}
  try { metrics = await api.metrics() } catch {}

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-zinc-400 text-sm mt-1">
          {status?.running ? (
            <span className="text-emerald-400">● Bot rodando — {status.symbol} {status.interval}</span>
          ) : (
            <span className="text-zinc-500">● Bot parado</span>
          )}
        </p>
      </div>

      <section>
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">Status</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard title="Saldo" value={status ? formatCurrency(status.balance) : '—'} sub={status ? `Inicial: ${formatCurrency(status.initial_balance)}` : undefined} icon="💰" />
          <MetricCard title="Drawdown" value={status ? `${status.drawdown_pct.toFixed(1)}%` : '—'} positive={status ? status.drawdown_pct < 10 : null} icon="📉" />
          <MetricCard title="Trades hoje" value={status ? String(status.trades_today) : '—'} sub={status ? `Total: ${status.total_trades}` : undefined} icon="🔄" />
          <MetricCard title="Perdas seguidas" value={status ? String(status.consecutive_losses) : '—'} positive={status ? status.consecutive_losses === 0 : null} icon="⚠️" />
        </div>
      </section>

      {metrics && (
        <section>
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">Performance</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard title="Win Rate" value={`${metrics.win_rate.toFixed(1)}%`} sub={`${metrics.wins}W / ${metrics.losses}L`} positive={metrics.win_rate >= 65} icon="🎯" />
            <MetricCard title="Profit Factor" value={metrics.profit_factor.toFixed(2)} positive={metrics.profit_factor >= 1.5} icon="⚖️" />
            <MetricCard title="PnL Total" value={formatPct(metrics.total_pnl_pct)} positive={metrics.total_pnl_pct >= 0} icon="📈" />
            <MetricCard title="Sharpe" value={metrics.sharpe_ratio.toFixed(2)} positive={metrics.sharpe_ratio >= 1} icon="✨" />
          </div>
        </section>
      )}

      {!status && !metrics && (
        <div className="text-center py-16 text-zinc-500">
          <p className="text-4xl mb-4">🤖</p>
          <p>API offline. Inicie o bot para ver os dados.</p>
          <code className="text-xs text-zinc-600 mt-2 block">python -m backend.api.routes</code>
        </div>
      )}
    </div>
  )
}
