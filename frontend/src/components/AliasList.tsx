import { useState } from 'react'
import { cn } from '@/lib/utils'

interface Alias {
  id: string
  name: string
  target: string
}

interface AliasListProps {
  aliases: Alias[]
  selectedId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}

export function AliasList({ aliases, selectedId, onSelect, onNew }: AliasListProps) {
  const [search, setSearch] = useState('')

  const filtered = aliases.filter((a) =>
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.target.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="flex w-80 shrink-0 flex-col gap-2 overflow-hidden">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search aliases..."
          className="flex-1 rounded border border-hive-border bg-hive-surface px-3 py-1.5 text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
        />
        <button
          onClick={onNew}
          className="rounded bg-hive-accent-dim px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-hive-accent-dim/80">
          + New
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-px overflow-y-auto">
        {filtered.map((alias) => (
          <button
            key={alias.id}
            onClick={() => onSelect(alias.id)}
            className={cn(
              'flex items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors',
              selectedId === alias.id
                ? 'bg-hive-accent-dim/20 text-hive-text'
                : 'text-hive-muted hover:bg-hive-surface hover:text-hive-text',
            )}>
            <span className="font-mono font-medium">!{alias.name}</span>
            <span className="text-xs text-hive-muted">&rarr;</span>
            <span className="font-mono text-xs text-hive-muted">!{alias.target}</span>
          </button>
        ))}
        {filtered.length === 0 && (
          <p className="px-3 py-4 text-center text-sm text-hive-muted">
            {search ? 'No aliases match your search.' : 'No aliases yet.'}
          </p>
        )}
      </div>
    </div>
  )
}
