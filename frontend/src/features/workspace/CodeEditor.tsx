import { Suspense, lazy } from 'react';
import type { editor as MonacoEditorType } from 'monaco-editor';

import { loadMonaco } from '@/shared/lib/monaco';
import { useThemeStore } from '@/features/theme/theme.store';
import { Spinner } from '@/shared/ui/Button';

type MonacoEditorInstance = MonacoEditorType.IStandaloneCodeEditor;

const MonacoEditor = lazy(async () => {
  await loadMonaco();
  const module = await import('@monaco-editor/react');
  return { default: module.Editor };
});

export interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: string;
  readOnly?: boolean;
  ariaLabel: string;
  className?: string;
  /** Receives the editor instance so findings can reveal their line. */
  onMount?: (editor: MonacoEditorInstance) => void;
}

/**
 * Controlled Monaco editor.
 *
 * The editor is a controlled component: the buffer lives in the workspace
 * store, so the same source is used by the analyzer, the pipeline and the
 * report — there is no second copy of the code anywhere in the app.
 */
export function CodeEditor({
  value,
  onChange,
  language = 'python',
  readOnly = false,
  ariaLabel,
  className,
  onMount,
}: CodeEditorProps) {
  const theme = useThemeStore((state) => state.theme);

  return (
    <Suspense
      fallback={
        <div className="flex h-full min-h-32 items-center justify-center gap-2 text-xs text-fg-subtle">
          <Spinner size={14} />
          Loading the editor…
        </div>
      }
    >
      <MonacoEditor
        value={value}
        language={language}
        theme={theme === 'dark' ? 'refactor-dark' : 'refactor-light'}
        onChange={(next) => onChange?.(next ?? '')}
        onMount={onMount}
        options={{
          readOnly,
          domReadOnly: readOnly,
          fontSize: 12.5,
          fontFamily: 'var(--f-mono)',
          lineNumbers: 'on',
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          renderLineHighlight: 'line',
          smoothScrolling: true,
          tabSize: 4,
          insertSpaces: true,
          automaticLayout: true,
          padding: { top: 10, bottom: 10 },
          scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
          ariaLabel,
        }}
        className={className}
      />
    </Suspense>
  );
}
