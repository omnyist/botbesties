import type { Monaco } from '@monaco-editor/react'

export const LANGUAGE_ID = 'synthhive-response'

export function registerSynthhiveLanguage(monaco: Monaco) {
  if (monaco.languages.getLanguages().some((l: { id: string }) => l.id === LANGUAGE_ID)) return

  monaco.languages.register({ id: LANGUAGE_ID })

  monaco.languages.setMonarchTokensProvider(LANGUAGE_ID, {
    tokenizer: {
      root: [
        [/\$\(/, { token: 'variable.bracket', next: '@variable' }],
        [/\/me\b/, 'keyword'],
        [/./, 'text'],
      ],
      variable: [
        [/\)/, { token: 'variable.bracket', next: '@pop' }],
        [/\./, 'variable.separator'],
        [/\s+/, 'variable.args'],
        [/[a-zA-Z_]\w*/, 'variable.name'],
        [/\d+/, 'variable.name'],
        [/[^)]+/, 'variable.args'],
      ],
    },
  })

  monaco.languages.setLanguageConfiguration(LANGUAGE_ID, {
    brackets: [['$(', ')']],
    autoClosingPairs: [{ open: '$(', close: ')' }],
    surroundingPairs: [{ open: '$(', close: ')' }],
  })

  monaco.editor.defineTheme('synthhive-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'text', foreground: 'e4e4e7' },
      { token: 'variable.bracket', foreground: 'a78bfa', fontStyle: 'bold' },
      { token: 'variable.name', foreground: 'c4b5fd' },
      { token: 'variable.separator', foreground: 'a78bfa' },
      { token: 'variable.args', foreground: '93c5fd' },
      { token: 'keyword', foreground: 'fbbf24', fontStyle: 'italic' },
    ],
    colors: {
      'editor.background': '#1a1a1f',
      'editor.foreground': '#e4e4e7',
      'editor.lineHighlightBackground': '#2a2a3200',
      'editorCursor.foreground': '#a78bfa',
      'editor.selectionBackground': '#7c3aed44',
    },
  })
}
