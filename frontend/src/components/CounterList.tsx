import { useState } from 'react'
import { cn } from '@/lib/utils'

interface Counter {
  id: string
  name: string
  label: string
  value: number
}

interface CounterListProps {
  counters: Counter[]
  selectedId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}

export function CounterList({ counters, selectedId, onSelect, onNew }: CounterListProps) {
  const [search, setSearch] = useState('')

  const filtered = counters.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="flex w-80 shrink-0 flex-col gap-2 overflow-hidden">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search counters..."
          className="flex-1 rounded border border-hive-border bg-hive-surface px-3 py-1.5 text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
        />
        <button
          onClick={onNew}
          className="rounded bg-hive-accent-dim px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-hive-accent-dim/80">
          + New
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-px overflow-y-auto">
        {filtered.map((counter) => (
          <button
            key={counter.id}
            onClick={() => onSelect(counter.id)}
            className={cn(
              'flex items-center gap-3 rounded px-3 py-2 text-left text-sm transition-colors',
              selectedId === counter.id
                ? 'bg-hive-accent-dim/20 text-hive-text'
                : 'text-hive-muted hover:bg-hive-surface hover:text-hive-text',
            )}>
            <span className="font-mono font-medium">{counter.name}</span>
            {counter.label && (
              <span className="text-xs text-hive-muted">{counter.label}</span>
            )}
            <span className="ml-auto font-mono text-xs text-hive-muted">{counter.value}</span>
          </button>
        ))}
        {filtered.length === 0 && (
          <p className="px-3 py-4 text-center text-sm text-hive-muted">
            {search ? 'No counters match your search.' : 'No counters yet.'}
          </p>
        )}
      </div>
    </div>
  )
}
