import { useEffect } from 'react'
import Editor from '@monaco-editor/react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { registerSynthhiveLanguage, LANGUAGE_ID } from '@/lib/monaco-synthhive'
import {
  ensureCompletionProvider,
  updateCompletionSchema,
  type VariableDescriptor,
} from '@/lib/monaco-completions'
import type { Monaco } from '@monaco-editor/react'

interface CommandEditorProps {
  value: string
  onChange: (value: string) => void
  height?: string
}

export function CommandEditor({ value, onChange, height = '120px' }: CommandEditorProps) {
  const { data: schema } = useQuery<VariableDescriptor[]>({
    queryKey: ['variable-schema'],
    queryFn: () => api<VariableDescriptor[]>('/api/v1/variables/schema/'),
    staleTime: 1000 * 60 * 30,
  })

  useEffect(() => {
    if (schema) {
      updateCompletionSchema(schema)
    }
  }, [schema])

  function handleBeforeMount(monaco: Monaco) {
    registerSynthhiveLanguage(monaco)
    ensureCompletionProvider(monaco)
    if (schema) {
      updateCompletionSchema(schema)
    }
  }

  return (
    <div className="overflow-hidden rounded border border-hive-border">
      <Editor
        height={height}
        language={LANGUAGE_ID}
        theme="synthhive-dark"
        value={value}
        onChange={(v) => onChange(v ?? '')}
        beforeMount={handleBeforeMount}
        loading={<div className="bg-hive-surface p-4 text-hive-muted">Loading editor...</div>}
        options={{
          minimap: { enabled: false },
          lineNumbers: 'off',
          wordWrap: 'on',
          fontSize: 14,
          fontFamily: 'var(--font-mono)',
          automaticLayout: true,
          scrollBeyondLastLine: false,
          folding: false,
          glyphMargin: false,
          lineDecorationsWidth: 8,
          lineNumbersMinChars: 0,
          renderLineHighlight: 'none',
          overviewRulerBorder: false,
          hideCursorInOverviewRuler: true,
          scrollbar: {
            vertical: 'auto',
            horizontal: 'hidden',
            verticalScrollbarSize: 8,
          },
          padding: { top: 8, bottom: 8 },
          suggestOnTriggerCharacters: true,
          quickSuggestions: true,
        }}
      />
    </div>
  )
}
