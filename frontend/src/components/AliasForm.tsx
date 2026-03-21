import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface Alias {
  id: string
  name: string
  target: string
}

interface AliasFormProps {
  channelSlug: string
  alias: Alias | null
  onClose: () => void
  onSaved: () => void
}

interface FormState {
  name: string
  target: string
}

function initialState(alias: Alias | null): FormState {
  if (alias) {
    return {
      name: alias.name,
      target: alias.target,
    }
  }
  return {
    name: '',
    target: '',
  }
}

export function AliasForm({ channelSlug, alias, onClose, onSaved }: AliasFormProps) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FormState>(() => initialState(alias))
  const [error, setError] = useState<string | null>(null)
  const isNew = !alias

  useEffect(() => {
    setForm(initialState(alias))
    setError(null)
  }, [alias])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = { ...form }

      if (isNew) {
        return api(`/api/v1/aliases/channels/${channelSlug}/`, {
          method: 'POST',
          body: JSON.stringify(body),
        })
      }

      return api(`/api/v1/aliases/${alias.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['aliases', channelSlug] })
      onSaved()
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () =>
      api(`/api/v1/aliases/${alias!.id}/`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['aliases', channelSlug] })
      onClose()
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto border-l border-hive-border pl-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          {isNew ? 'New Alias' : `Editing: !${alias.name}`}
        </h3>
        <div className="flex items-center gap-2">
          {!isNew && (
            <button
              onClick={() => {
                if (window.confirm(`Delete alias !${alias.name}?`)) {
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

      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Alias Name</label>
        <div className="flex items-center gap-1">
          <span className="text-hive-muted">!</span>
          <input
            type="text"
            value={form.name}
            onChange={(e) => update('name', e.target.value)}
            placeholder="alias_name"
            pattern="[a-zA-Z0-9_]+"
            className="w-48 rounded border border-hive-border bg-hive-surface px-2 py-1 font-mono text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
          />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Target</label>
        <div className="flex items-center gap-1">
          <span className="text-hive-muted">!</span>
          <input
            type="text"
            value={form.target}
            onChange={(e) => update('target', e.target.value)}
            placeholder="command_name args"
            className="w-64 rounded border border-hive-border bg-hive-surface px-2 py-1 font-mono text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
          />
        </div>
      </div>
    </div>
  )
}
