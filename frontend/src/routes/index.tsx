import { useEffect } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface ChannelBrief {
  id: string
  name: string
  bot_name: string
}

interface MeResponse {
  twitch_id: string
  twitch_username: string
  twitch_display_name: string
  twitch_avatar: string
  channels: ChannelBrief[]
}

export const Route = createFileRoute('/')({
  component: Index,
})

function Index() {
  const navigate = useNavigate()

  const { data: user, isLoading } = useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: () => api<MeResponse>('/api/v1/me'),
    retry: false,
  })

  useEffect(() => {
    if (user && user.channels.length > 0) {
      navigate({
        to: '/$channelId/commands',
        params: { channelId: user.channels[0].id },
      })
    }
  }, [user, navigate])

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-hive-muted">Loading...</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6">
        <h1 className="text-3xl font-bold tracking-tight">Synthhive</h1>
        <a
          href="/auth/twitch/login/"
          className="rounded-lg bg-hive-accent-dim px-6 py-3 font-medium text-white transition-colors hover:bg-hive-accent-dim/80">
          Login with Twitch
        </a>
      </div>
    )
  }

  if (user.channels.length > 0) {
    return null
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <p className="text-hive-muted">No channels found.</p>
      <a
        href="/auth/logout/"
        className="text-sm text-hive-muted transition-colors hover:text-hive-text">
        Logout
      </a>
    </div>
  )
}
