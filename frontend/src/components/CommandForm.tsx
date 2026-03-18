import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { CommandEditor } from './CommandEditor'

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
}

interface CommandFormProps {
  channelId: string
  command: Command | null
  onClose: () => void
  onSaved: () => void
}

type CommandType = 'text' | 'lottery' | 'random_list' | 'counter'

interface FormState {
  name: string
  type: CommandType
  response: string
  config: Record<string, unknown>
  enabled: boolean
  cooldown_seconds: number
  user_cooldown_seconds: number
  mod_only: boolean
}

function initialState(cmd: Command | null): FormState {
  if (cmd) {
    return {
      name: cmd.name,
      type: cmd.type as CommandType,
      response: cmd.response,
      config: { ...cmd.config },
      enabled: cmd.enabled,
      cooldown_seconds: cmd.cooldown_seconds,
      user_cooldown_seconds: cmd.user_cooldown_seconds,
      mod_only: cmd.mod_only,
    }
  }
  return {
    name: '',
    type: 'text',
    response: '',
    config: {},
    enabled: true,
    cooldown_seconds: 0,
    user_cooldown_seconds: 0,
    mod_only: false,
  }
}

export function CommandForm({ channelId, command, onClose, onSaved }: CommandFormProps) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FormState>(() => initialState(command))
  const [error, setError] = useState<string | null>(null)
  const isNew = !command

  useEffect(() => {
    setForm(initialState(command))
    setError(null)
  }, [command])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = { ...form }

      if (isNew) {
        return api(`/api/v1/commands/channels/${channelId}/`, {
          method: 'POST',
          body: JSON.stringify(body),
        })
      }

      return api(`/api/v1/commands/${command.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['commands', channelId] })
      onSaved()
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () =>
      api(`/api/v1/commands/${command!.id}/`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['commands', channelId] })
      onClose()
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const updateConfig = (key: string, value: unknown) => {
    setForm((prev) => ({
      ...prev,
      config: { ...prev.config, [key]: value },
    }))
  }

  return (
    <div className="flex flex-col gap-4 border-t border-hive-border pt-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          {isNew ? 'New Command' : `Editing: !${command.name}`}
        </h3>
        <div className="flex items-center gap-2">
          {!isNew && (
            <button
              onClick={() => {
                if (window.confirm(`Delete !${command.name}?`)) {
                  deleteMutation.mutate()
                }
              }}
              disabled={deleteMutation.isPending}
              className="rounded px-3 py-1 text-xs text-red-400 transition-colors hover:bg-red-400/10">
              Delete
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded px-3 py-1 text-xs text-hive-muted transition-colors hover:text-hive-text">
            Cancel
          </button>
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="rounded bg-hive-accent-dim px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-hive-accent-dim/80 disabled:opacity-50">
            {saveMutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="grid grid-cols-[1fr_auto] gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-hive-muted">Name</label>
          <div className="flex items-center gap-1">
            <span className="text-hive-muted">!</span>
            <input
              type="text"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              placeholder="command_name"
              pattern="[a-zA-Z0-9_]+"
              className="flex-1 rounded border border-hive-border bg-hive-surface px-2 py-1 font-mono text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
            />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-hive-muted">Type</label>
          <select
            value={form.type}
            onChange={(e) => update('type', e.target.value as CommandType)}
            className="rounded border border-hive-border bg-hive-surface px-2 py-1 text-sm text-hive-text focus:border-hive-accent focus:outline-none">
            <option value="text">Text</option>
            <option value="lottery">Lottery</option>
            <option value="random_list">Random List</option>
            <option value="counter">Counter</option>
          </select>
        </div>
      </div>

      {form.type === 'text' && (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-hive-muted">Response</label>
          <CommandEditor value={form.response} onChange={(v) => update('response', v)} />
        </div>
      )}

      {form.type === 'lottery' && <LotteryConfig form={form} update={update} updateConfig={updateConfig} />}
      {form.type === 'random_list' && <RandomListConfig form={form} updateConfig={updateConfig} />}
      {form.type === 'counter' && <CounterConfig form={form} update={update} updateConfig={updateConfig} />}

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-hive-muted">Global Cooldown (seconds)</label>
          <input
            type="number"
            min={0}
            value={form.cooldown_seconds}
            onChange={(e) => update('cooldown_seconds', parseInt(e.target.value) || 0)}
            className="rounded border border-hive-border bg-hive-surface px-2 py-1 text-sm text-hive-text focus:border-hive-accent focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-hive-muted">Per-User Cooldown (seconds)</label>
          <input
            type="number"
            min={0}
            value={form.user_cooldown_seconds}
            onChange={(e) => update('user_cooldown_seconds', parseInt(e.target.value) || 0)}
            className="rounded border border-hive-border bg-hive-surface px-2 py-1 text-sm text-hive-text focus:border-hive-accent focus:outline-none"
          />
        </div>
      </div>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => update('enabled', e.target.checked)}
            className="accent-hive-accent"
          />
          <span className="text-hive-text">Enabled</span>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.mod_only}
            onChange={(e) => update('mod_only', e.target.checked)}
            className="accent-hive-accent"
          />
          <span className="text-hive-text">Mod only</span>
        </label>
      </div>
    </div>
  )
}

function LotteryConfig({
  form,
  update,
  updateConfig,
}: {
  form: FormState
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void
  updateConfig: (key: string, value: unknown) => void
}) {
  const odds = (form.config.odds as number) ?? 50

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Win Chance (%)</label>
        <input
          type="number"
          min={1}
          max={100}
          value={odds}
          onChange={(e) => updateConfig('odds', parseInt(e.target.value) || 1)}
          className="w-24 rounded border border-hive-border bg-hive-surface px-2 py-1 text-sm text-hive-text focus:border-hive-accent focus:outline-none"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Success Message</label>
        <CommandEditor
          value={(form.config.success as string) ?? ''}
          onChange={(v) => updateConfig('success', v)}
          height="60px"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Failure Message</label>
        <CommandEditor
          value={(form.config.failure as string) ?? ''}
          onChange={(v) => updateConfig('failure', v)}
          height="60px"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Response (main template, optional)</label>
        <CommandEditor value={form.response} onChange={(v) => update('response', v)} />
      </div>
    </div>
  )
}

function RandomListConfig({
  form,
  updateConfig,
}: {
  form: FormState
  updateConfig: (key: string, value: unknown) => void
}) {
  const prefix = (form.config.prefix as string) ?? ''
  const responses = (form.config.responses as string[]) ?? []

  const updateResponse = (index: number, value: string) => {
    const updated = [...responses]
    updated[index] = value
    updateConfig('responses', updated)
  }

  const addResponse = () => {
    updateConfig('responses', [...responses, ''])
  }

  const removeResponse = (index: number) => {
    updateConfig('responses', responses.filter((_, i) => i !== index))
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Prefix (optional)</label>
        <input
          type="text"
          value={prefix}
          onChange={(e) => updateConfig('prefix', e.target.value)}
          placeholder="e.g. 🐚 "
          className="w-48 rounded border border-hive-border bg-hive-surface px-2 py-1 text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
        />
      </div>
      <div className="flex flex-col gap-2">
        <label className="text-xs text-hive-muted">Responses</label>
        {responses.map((resp, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="mt-1.5 text-xs text-hive-muted">{i + 1}.</span>
            <input
              type="text"
              value={resp}
              onChange={(e) => updateResponse(i, e.target.value)}
              className="flex-1 rounded border border-hive-border bg-hive-surface px-2 py-1 text-sm text-hive-text focus:border-hive-accent focus:outline-none"
            />
            <button
              onClick={() => removeResponse(i)}
              className="mt-0.5 rounded px-2 py-1 text-xs text-red-400 transition-colors hover:bg-red-400/10">
              x
            </button>
          </div>
        ))}
        <button
          onClick={addResponse}
          className="self-start rounded border border-hive-border px-3 py-1 text-xs text-hive-muted transition-colors hover:border-hive-accent hover:text-hive-text">
          + Add Response
        </button>
      </div>
    </div>
  )
}

function CounterConfig({
  form,
  update,
  updateConfig,
}: {
  form: FormState
  update: <K extends keyof FormState>(key: K, value: FormState[K]) => void
  updateConfig: (key: string, value: unknown) => void
}) {
  const counterName = (form.config.counter_name as string) ?? ''

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Counter Name</label>
        <input
          type="text"
          value={counterName}
          onChange={(e) => updateConfig('counter_name', e.target.value)}
          placeholder="Defaults to command name"
          className="w-48 rounded border border-hive-border bg-hive-surface px-2 py-1 font-mono text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Response Template</label>
        <CommandEditor value={form.response} onChange={(v) => update('response', v)} />
      </div>
    </div>
  )
}
