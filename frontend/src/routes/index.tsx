import { createFileRoute } from '@tanstack/react-router'
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
  const { data: user, isLoading } = useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: () => api<MeResponse>('/api/v1/me'),
    retry: false,
  })

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

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <div className="flex items-center gap-3">
        {user.twitch_avatar && (
          <img src={user.twitch_avatar} alt="" className="h-10 w-10 rounded-full" />
        )}
        <span className="text-lg">{user.twitch_display_name}</span>
      </div>
      {user.channels.length > 0 ? (
        <div className="flex flex-col items-center gap-2">
          <p className="text-sm text-hive-muted">Channels</p>
          {user.channels.map((channel) => (
            <p key={channel.id} className="text-hive-text">
              {channel.name}
              <span className="ml-2 text-xs text-hive-muted">({channel.bot_name})</span>
            </p>
          ))}
        </div>
      ) : (
        <p className="text-hive-muted">No channels found.</p>
      )}
      <a
        href="/auth/logout/"
        className="text-sm text-hive-muted transition-colors hover:text-hive-text">
        Logout
      </a>
    </div>
  )
}
