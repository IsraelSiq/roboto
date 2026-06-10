import { cn } from '@/lib/utils'

interface Props {
  title: string
  value: string
  sub?: string
  positive?: boolean | null
  icon?: string
}

export function MetricCard({ title, value, sub, positive, icon }: Props) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400 uppercase tracking-wider">{title}</span>
        {icon && <span className="text-lg">{icon}</span>}
      </div>
      <span
        className={cn(
          'text-2xl font-bold',
          positive === true && 'text-emerald-400',
          positive === false && 'text-red-400',
          positive === null || positive === undefined ? 'text-white' : ''
        )}
      >
        {value}
      </span>
      {sub && <span className="text-xs text-zinc-500">{sub}</span>}
    </div>
  )
}
