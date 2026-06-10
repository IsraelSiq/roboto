import { api } from '@/services/api'
import { MetricCard } from '@/components/MetricCard'
import { TradesTable } from '@/components/TradesTable'
import { EquityCurve } from '@/components/EquityCurve'
import { formatPct } from '@/lib/utils'

export const revalidate = 30

export default async function ReportsPage() {
  let trades: Awaited<ReturnType<typeof api.tradesHistory>> = []
  let metrics = null
  let status = null

  try { trades = await api.tradesHistory() } catch {}
  try { metrics = await api.metrics() } catch {}
  try { status = await api.status() } catch {}

  const initialBalance = status?.initial_balance ?? 10000
  const closedTrades = trades.filter(t => t.result !== null)

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Relatórios</h1>
          <p className="text-zinc-400 text-sm mt-1">{closedTrades.length} trades fechados</p>
        </div>
        <a
          href={api.exportCSV()}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          download
        >
          ⬇️ Exportar CSV
        </a>
      </div>

      {metrics ? (
        <section>
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">Métricas de Performance</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <MetricCard title="Win Rate" value={`${metrics.win_rate.toFixed(1)}%`} positive={metrics.win_rate >= 65} icon="🎯" />
            <MetricCard title="Profit Factor" value={metrics.profit_factor.toFixed(2)} positive={metrics.profit_factor >= 1.5} icon="⚖️" />
            <MetricCard title="PnL Total" value={formatPct(metrics.total_pnl_pct)} positive={metrics.total_pnl_pct >= 0} icon="📈" />
            <MetricCard title="Max Drawdown" value={`${metrics.max_drawdown.toFixed(1)}%`} positive={metrics.max_drawdown < 20} icon="📉" />
            <MetricCard title="Sharpe" value={metrics.sharpe_ratio.toFixed(2)} positive={metrics.sharpe_ratio >= 1} icon="✨" />
          </div>
        </section>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center text-zinc-500 text-sm">
          Métricas indisponíveis — API offline ou nenhum trade fechado.
        </div>
      )}

      <section>
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">Curva de Equity</h2>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <EquityCurve trades={trades} initialBalance={initialBalance} />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">Histórico de Trades</h2>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <TradesTable trades={trades} />
        </div>
      </section>
    </div>
  )
}
