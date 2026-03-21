import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { CounterList } from '@/components/CounterList'
import { CounterForm } from '@/components/CounterForm'

export interface Counter {
  id: string
  name: string
  label: string
  value: number
}

export const Route = createFileRoute('/$channelSlug/counters')({
  component: CountersPage,
})

function CountersPage() {
  const { channelSlug } = Route.useParams()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isNew, setIsNew] = useState(false)

  const { data: counters = [], isLoading } = useQuery<Counter[]>({
    queryKey: ['counters', channelSlug],
    queryFn: () => api<Counter[]>(`/api/v1/counters/channels/${channelSlug}/`),
  })

  const selectedCounter = selectedId ? counters.find((c) => c.id === selectedId) ?? null : null

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <p className="text-hive-muted">Loading counters...</p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 gap-4 overflow-hidden p-4">
      <CounterList
        counters={counters}
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
      {(selectedCounter || isNew) && (
        <CounterForm
          channelSlug={channelSlug}
          counter={isNew ? null : selectedCounter}
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
