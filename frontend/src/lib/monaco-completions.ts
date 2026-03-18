import type { Monaco } from '@monaco-editor/react'
import type { editor, Position } from 'monaco-editor'
import { LANGUAGE_ID } from './monaco-synthhive'

export interface VariableDescriptor {
  namespace: string
  property: string | null
  args_hint: string | null
  description: string
  example: string
}

let _schema: VariableDescriptor[] = []
let _registered = false

export function updateCompletionSchema(schema: VariableDescriptor[]) {
  _schema = schema
}

export function ensureCompletionProvider(monaco: Monaco) {
  if (_registered) return
  _registered = true

  monaco.languages.registerCompletionItemProvider(LANGUAGE_ID, {
    triggerCharacters: ['$', '(', '.'],

    provideCompletionItems: (model: editor.ITextModel, position: Position) => {
      const textUntilPosition = model.getValueInRange({
        startLineNumber: position.lineNumber,
        startColumn: 1,
        endLineNumber: position.lineNumber,
        endColumn: position.column,
      })

      const variableMatch = textUntilPosition.match(/\$\(([a-zA-Z0-9_.]*)$/)
      if (!variableMatch) {
        return { suggestions: [] }
      }

      const typed = variableMatch[1]
      const dollarParenStart = position.column - typed.length - 2

      const suggestions = _schema.map((desc) => {
        let insertText = desc.example.slice(2, -1)
        if (desc.args_hint) {
          insertText = insertText.replace(
            ` ${desc.args_hint}`,
            ` \${1:${desc.args_hint}}`,
          )
        }

        const label = desc.example

        return {
          label,
          kind: monaco.languages.CompletionItemKind.Variable,
          insertText: insertText + ')',
          insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
          detail: desc.description,
          documentation: `Example: ${desc.example}`,
          range: {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: dollarParenStart + 1,
            endColumn: position.column,
          },
          filterText: desc.example,
          sortText: desc.namespace + (desc.property ?? ''),
        }
      })

      return { suggestions }
    },
  })
}
