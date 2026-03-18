import { createRootRoute, Outlet, Link, useMatchRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

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

export const Route = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  const { data: user } = useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: () => api<MeResponse>('/api/v1/me'),
    retry: false,
  })

  if (!user) {
    return <Outlet />
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar user={user} />
      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}

function Sidebar({ user }: { user: MeResponse }) {
  const matchRoute = useMatchRoute()
  const currentChannel = user.channels.length > 0 ? user.channels[0] : null
  const isCommands = currentChannel
    ? matchRoute({ to: '/$channelSlug/commands', params: { channelSlug: currentChannel.name } })
    : false

  return (
    <aside className="flex w-48 flex-col border-r border-hive-border bg-hive-surface">
      <div className="border-b border-hive-border px-4 py-3">
        <h1 className="text-sm font-bold tracking-tight text-hive-text">Synthhive</h1>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2">
        {currentChannel && (
          <Link
            to="/$channelSlug/commands"
            params={{ channelSlug: currentChannel.name }}
            className={cn(
              'rounded px-3 py-1.5 text-sm transition-colors',
              isCommands
                ? 'bg-hive-accent-dim/20 text-hive-text'
                : 'text-hive-muted hover:text-hive-text',
            )}>
            Commands
          </Link>
        )}
        <span className="cursor-default px-3 py-1.5 text-sm text-hive-muted/50">Counters</span>
        <span className="cursor-default px-3 py-1.5 text-sm text-hive-muted/50">Aliases</span>
      </nav>
      <div className="border-t border-hive-border p-3">
        <div className="flex items-center gap-2">
          {user.twitch_avatar && (
            <img src={user.twitch_avatar} alt="" className="h-6 w-6 rounded-full" />
          )}
          <span className="flex-1 truncate text-xs text-hive-text">
            {user.twitch_display_name}
          </span>
        </div>
        <a
          href="/auth/logout/"
          className="mt-2 block text-xs text-hive-muted transition-colors hover:text-hive-text">
          Logout
        </a>
      </div>
    </aside>
  )
}
