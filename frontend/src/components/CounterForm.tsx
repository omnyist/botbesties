import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

interface Counter {
  id: string
  name: string
  label: string
  value: number
}

interface CounterFormProps {
  channelSlug: string
  counter: Counter | null
  onClose: () => void
  onSaved: () => void
}

interface FormState {
  name: string
  label: string
  value: number
}

function initialState(counter: Counter | null): FormState {
  if (counter) {
    return {
      name: counter.name,
      label: counter.label,
      value: counter.value,
    }
  }
  return {
    name: '',
    label: '',
    value: 0,
  }
}

export function CounterForm({ channelSlug, counter, onClose, onSaved }: CounterFormProps) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FormState>(() => initialState(counter))
  const [error, setError] = useState<string | null>(null)
  const isNew = !counter

  useEffect(() => {
    setForm(initialState(counter))
    setError(null)
  }, [counter])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = { ...form }

      if (isNew) {
        return api(`/api/v1/counters/channels/${channelSlug}/`, {
          method: 'POST',
          body: JSON.stringify(body),
        })
      }

      return api(`/api/v1/counters/${counter.id}/`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['counters', channelSlug] })
      onSaved()
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () =>
      api(`/api/v1/counters/${counter!.id}/`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['counters', channelSlug] })
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
          {isNew ? 'New Counter' : `Editing: ${counter.name}`}
        </h3>
        <div className="flex items-center gap-2">
          {!isNew && (
            <button
              onClick={() => {
                if (window.confirm(`Delete counter "${counter.name}"?`)) {
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
        <label className="text-xs text-hive-muted">Name</label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => update('name', e.target.value)}
          placeholder="counter_name"
          pattern="[a-zA-Z0-9_]+"
          className="w-48 rounded border border-hive-border bg-hive-surface px-2 py-1 font-mono text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Label</label>
        <input
          type="text"
          value={form.label}
          onChange={(e) => update('label', e.target.value)}
          placeholder="Display label (e.g. Death Count)"
          className="w-64 rounded border border-hive-border bg-hive-surface px-2 py-1 text-sm text-hive-text placeholder-hive-muted focus:border-hive-accent focus:outline-none"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-hive-muted">Value</label>
        <input
          type="number"
          value={form.value}
          onChange={(e) => update('value', parseInt(e.target.value) || 0)}
          className="w-32 rounded border border-hive-border bg-hive-surface px-2 py-1 font-mono text-sm text-hive-text focus:border-hive-accent focus:outline-none"
        />
      </div>
    </div>
  )
}
