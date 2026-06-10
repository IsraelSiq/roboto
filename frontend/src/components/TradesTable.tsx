'use client'
import { Trade } from '@/services/api'
import { formatCurrency, formatPct, formatDate, cn } from '@/lib/utils'

interface Props {
  trades: Trade[]
}

export function TradesTable({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500 text-sm">
        Nenhum trade registrado ainda.
      </div>
    )
  }

  const sorted = [...trades].sort(
    (a, b) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime()
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-zinc-400 text-xs uppercase">
            <th className="text-left py-3 px-4">Data</th>
            <th className="text-left py-3 px-4">Par</th>
            <th className="text-left py-3 px-4">Direção</th>
            <th className="text-right py-3 px-4">Entry</th>
            <th className="text-right py-3 px-4">Exit</th>
            <th className="text-right py-3 px-4">PnL</th>
            <th className="text-center py-3 px-4">Resultado</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((t) => (
            <tr key={t.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
              <td className="py-3 px-4 text-zinc-400">{formatDate(t.opened_at)}</td>
              <td className="py-3 px-4 font-medium">{t.symbol}</td>
              <td className="py-3 px-4">
                <span className={cn(
                  'px-2 py-0.5 rounded text-xs font-semibold',
                  t.direction === 'CALL' ? 'bg-emerald-900/50 text-emerald-400' : 'bg-red-900/50 text-red-400'
                )}>
                  {t.direction}
                </span>
              </td>
              <td className="py-3 px-4 text-right">{formatCurrency(t.entry_price)}</td>
              <td className="py-3 px-4 text-right">
                {t.exit_price ? formatCurrency(t.exit_price) : <span className="text-zinc-500">aberto</span>}
              </td>
              <td className={cn(
                'py-3 px-4 text-right font-medium',
                t.pnl_pct === null ? 'text-zinc-500' :
                t.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
              )}>
                {t.pnl_pct !== null ? formatPct(t.pnl_pct) : '—'}
              </td>
              <td className="py-3 px-4 text-center">
                {t.result ? (
                  <span className={cn(
                    'px-2 py-0.5 rounded text-xs font-semibold',
                    t.result === 'WIN' ? 'bg-emerald-900/50 text-emerald-400' : 'bg-red-900/50 text-red-400'
                  )}>
                    {t.result}
                  </span>
                ) : (
                  <span className="text-zinc-500 text-xs">em aberto</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
