'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

const links = [
  { href: '/', label: 'Dashboard' },
  { href: '/reports', label: 'Relatórios' },
]

export function Navbar() {
  const pathname = usePathname()
  return (
    <nav className="border-b border-zinc-800 bg-zinc-950 px-6 py-4 flex items-center gap-8">
      <span className="text-white font-bold text-lg flex items-center gap-2">
        🤖 <span>Roboto</span>
      </span>
      <div className="flex gap-1">
        {links.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              'px-4 py-1.5 rounded-lg text-sm font-medium transition-colors',
              pathname === href
                ? 'bg-zinc-800 text-white'
                : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
            )}
          >
            {label}
          </Link>
        ))}
      </div>
    </nav>
  )
}
