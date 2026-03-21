import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { AliasList } from '@/components/AliasList'
import { AliasForm } from '@/components/AliasForm'

export interface Alias {
  id: string
  name: string
  target: string
}

export const Route = createFileRoute('/$channelSlug/aliases')({
  component: AliasesPage,
})

function AliasesPage() {
  const { channelSlug } = Route.useParams()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isNew, setIsNew] = useState(false)

  const { data: aliases = [], isLoading } = useQuery<Alias[]>({
    queryKey: ['aliases', channelSlug],
    queryFn: () => api<Alias[]>(`/api/v1/aliases/channels/${channelSlug}/`),
  })

  const selectedAlias = selectedId ? aliases.find((a) => a.id === selectedId) ?? null : null

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <p className="text-hive-muted">Loading aliases...</p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 gap-4 overflow-hidden p-4">
      <AliasList
        aliases={aliases}
        selectedId={selectedId}
        onSelect={(id) => {
          setSelectedId(id)
          setIsNew(false)
        }}
        onNew={() => {
          setSelectedId(null)
          setIsNew(true)
        }}
      />
      {(selectedAlias || isNew) && (
        <AliasForm
          channelSlug={channelSlug}
          alias={isNew ? null : selectedAlias}
          onClose={() => {
            setSelectedId(null)
            setIsNew(false)
          }}
          onSaved={() => {
            if (isNew) setIsNew(false)
          }}
        />
      )}
    </div>
  )
}
