import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { CommandList } from '@/components/CommandList'
import { CommandForm } from '@/components/CommandForm'

interface Command {
  id: string
  name: string
  type: string
  response: string
  config: Record<string, unknown>
  enabled: boolean
  use_count: number
  cooldown_seconds: number
  user_cooldown_seconds: number
  mod_only: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export const Route = createFileRoute('/$channelId/commands')({
  component: CommandsPage,
})

function CommandsPage() {
  const { channelId } = Route.useParams()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isNew, setIsNew] = useState(false)

  const { data: commands = [], isLoading } = useQuery<Command[]>({
    queryKey: ['commands', channelId],
    queryFn: () => api<Command[]>(`/api/v1/commands/channels/${channelId}/`),
  })

  const selectedCommand = selectedId ? commands.find((c) => c.id === selectedId) ?? null : null

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <p className="text-hive-muted">Loading commands...</p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-hidden p-4">
      <CommandList
        commands={commands}
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
      {(selectedCommand || isNew) && (
        <CommandForm
          channelId={channelId}
          command={isNew ? null : selectedCommand}
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
