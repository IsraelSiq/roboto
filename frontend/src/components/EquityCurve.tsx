'use client'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Trade } from '@/services/api'

interface Props {
  trades: Trade[]
  initialBalance: number
}

export function EquityCurve({ trades, initialBalance }: Props) {
  const closed = trades.filter(t => t.pnl_pct !== null && t.closed_at)
  if (closed.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-zinc-500 text-sm">
        Nenhum trade fechado ainda.
      </div>
    )
  }

  let equity = initialBalance
  const data = [
    { name: 'Início', equity: initialBalance },
    ...closed.map((t, i) => {
      equity = equity * (1 + (t.pnl_pct! / 100))
      return {
        name: `#${i + 1}`,
        equity: Math.round(equity * 100) / 100,
      }
    }),
  ]

  const min = Math.min(...data.map(d => d.equity))
  const max = Math.max(...data.map(d => d.equity))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="name" tick={{ fill: '#71717a', fontSize: 11 }} />
        <YAxis
          tick={{ fill: '#71717a', fontSize: 11 }}
          domain={[min * 0.995, max * 1.005]}
          tickFormatter={(v) => `$${v.toLocaleString()}`}
        />
        <Tooltip
          contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }}
          labelStyle={{ color: '#a1a1aa' }}
          formatter={(v: number) => [`$${v.toLocaleString()}`, 'Saldo']}
        />
        <ReferenceLine y={initialBalance} stroke="#52525b" strokeDasharray="4 4" />
        <Line
          type="monotone"
          dataKey="equity"
          stroke="#34d399"
          strokeWidth={2}
          dot={{ r: 3, fill: '#34d399' }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
