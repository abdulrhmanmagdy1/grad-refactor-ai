import { Suspense, lazy } from 'react';

import { loadMonaco } from '@/shared/lib/monaco';
import { useThemeStore } from '@/features/theme/theme.store';
import { Spinner } from '@/shared/ui/Button';
import { Segmented } from '@/shared/ui/Inputs';

const MonacoDiffEditor = lazy(async () => {
  await loadMonaco();
  const module = await import('@monaco-editor/react');
  return { default: module.DiffEditor };
});

export type DiffLayout = 'split' | 'inline';

/**
 * Side-by-side / inline diff of the submitted code and the proposed candidate.
 *
 * Uses the real Monaco diff editor (not a text dump), so the reviewer sees
 * syntax-highlighted changes with the exact lines that moved.
 */
export function DiffViewer({
  original,
  modified,
  layout,
  onLayoutChange,
}: {
  original: string;
  modified: string;
  layout: DiffLayout;
  onLayoutChange: (layout: DiffLayout) => void;
}) {
  const theme = useThemeStore((state) => state.theme);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-edge px-3 py-1.5">
        <Segmented
          label="Diff layout"
          value={layout}
          onChange={onLayoutChange}
          options={[
            { value: 'split', label: 'Side by side' },
            { value: 'inline', label: 'Inline' },
          ]}
        />
      </div>
      <div className="min-h-0 flex-1">
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center gap-2 text-xs text-fg-subtle">
              <Spinner size={14} />
              Loading the diff viewer…
            </div>
          }
        >
          <MonacoDiffEditor
            original={original}
            modified={modified}
            theme={theme === 'dark' ? 'refactor-dark' : 'refactor-light'}
            options={{
              renderSideBySide: layout === 'split',
              readOnly: true,
              renderOverviewRuler: false,
              fontSize: 12.5,
              fontFamily: 'var(--f-mono)',
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              ariaLabel: 'Diff between the submitted code and the proposed refactoring',
            }}
            className="h-full"
          />
        </Suspense>
      </div>
    </div>
  );
}
