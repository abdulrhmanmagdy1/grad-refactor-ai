import { useEffect, useState } from 'react';
import { AlertTriangle, Keyboard, Moon, Search, Sun } from 'lucide-react';

import { useHealth, useProviders } from '@/entities/queries';
import { useHotkeys } from '@/shared/hooks/useHotkeys';
import { useMediaQuery, useOnlineStatus } from '@/shared/hooks/useUi';
import { Button, IconButton } from '@/shared/ui/Button';
import { Badge } from '@/shared/ui/Feedback';
import { Select } from '@/shared/ui/Inputs';
import { useThemeStore } from '@/features/theme/theme.store';
import { useWorkspaceStore } from '@/features/workspace/workspace.store';
import { useRunPipeline } from '@/features/workspace/useRunPipeline';
import { WorkspacePanel } from '@/features/workspace/WorkspacePanel';
import { ResultsPanel } from '@/features/results/ResultsPanel';
import { HistoryDrawer } from '@/features/history/HistoryDrawer';
import { CompareDialog } from '@/features/compare/CompareDialog';
import { useUrlSync } from '@/features/results/useUrlSync';
import { CommandPalette, ShortcutsDialog } from '@/features/overlays';

type MobileView = 'workspace' | 'results';

export function AppShell() {
  const health = useHealth();
  const online = useOnlineStatus();
  const providers = useProviders();
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const provider = useWorkspaceStore((state) => state.provider);
  const setProvider = useWorkspaceStore((state) => state.setProvider);
  const { runPipeline } = useRunPipeline();

  const [historyOpen, setHistoryOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareRunId, setCompareRunId] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<MobileView>('workspace');

  const wide = useMediaQuery('(min-width: 1024px)');

  useUrlSync();

  useHotkeys([
    { combo: 'mod+enter', handler: () => void runPipeline(), description: 'Run the pipeline' },
    { combo: 'mod+k', handler: () => setPaletteOpen(true), description: 'Open the command palette' },
    { combo: 'mod+b', handler: () => setHistoryOpen((open) => !open), description: 'Toggle run history' },
    { combo: 'mod+/', handler: () => setShortcutsOpen(true), description: 'Show keyboard shortcuts' },
  ]);

  // Keep the provider selection valid against the live catalog.
  useEffect(() => {
    const catalog = providers.data;
    if (!catalog || catalog.length === 0) return;
    const current = catalog.find((entry) => entry.id === provider);
    if (current) return;
    const fallback = catalog.find((entry) => entry.available) ?? catalog[0];
    setProvider(fallback.id);
  }, [providers.data, provider, setProvider]);

  const providerOptions = (providers.data ?? []).map((entry) => ({
    value: entry.id,
    label: `${entry.label}${entry.available ? '' : ' (unavailable)'}`,
  }));

  const apiDown = !online || health.isError;

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg text-fg">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-edge bg-surface px-3">
        <div className="flex min-w-0 items-center gap-2">
          <span
            aria-hidden="true"
            className="grid size-7 shrink-0 place-items-center rounded-md bg-accent text-[13px] font-bold text-on-accent"
          >
            R
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm leading-tight font-semibold">Refactor AI</p>
            <p className="hidden truncate text-[11px] leading-tight text-fg-subtle sm:block">
              Multi-agent Python refactoring with deterministic verification
            </p>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Badge tone={apiDown ? 'danger' : 'success'} title={apiDown ? 'The API is unreachable' : undefined}>
            <span
              aria-hidden="true"
              className={`size-1.5 rounded-full ${apiDown ? 'bg-danger' : 'bg-success'}`}
            />
            {apiDown ? 'api offline' : `api ${health.data?.version ?? 'online'}`}
          </Badge>

          {providerOptions.length > 0 ? (
            <Select
              label="Model provider"
              className="hidden sm:flex"
              value={provider || providerOptions[0]?.value || 'mock'}
              onChange={setProvider}
              options={providerOptions}
            />
          ) : null}

          <IconButton
            label="Open command palette"
            onClick={() => setPaletteOpen(true)}
            className="hidden sm:inline-flex"
          >
            <Search size={14} aria-hidden="true" />
          </IconButton>
          <IconButton label="Show keyboard shortcuts" onClick={() => setShortcutsOpen(true)}>
            <Keyboard size={14} aria-hidden="true" />
          </IconButton>
          <IconButton
            label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            onClick={toggleTheme}
          >
            {theme === 'dark' ? <Sun size={14} aria-hidden="true" /> : <Moon size={14} aria-hidden="true" />}
          </IconButton>
          <IconButton label="Toggle run history" onClick={() => setHistoryOpen((open) => !open)}>
            <span className="text-[11px] font-semibold">History</span>
          </IconButton>
        </div>
      </header>

      {apiDown ? (
        <div
          role="status"
          className="flex items-center gap-2 border-b border-danger/40 bg-danger-soft px-3 py-1.5 text-xs text-danger"
        >
          <AlertTriangle size={13} aria-hidden="true" />
          <span className="min-w-0 flex-1">
            The API is not reachable. Start it with{' '}
            <code className="font-mono">uv run uvicorn refactor_ai.api:app --port 8000</code>.
          </span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void health.refetch()}
            loading={health.isFetching}
          >
            Reconnect
          </Button>
        </div>
      ) : null}

      <main id="main-content" className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row">
        {wide ? <WorkspacePanel className="lg:w-[44%] lg:min-w-[24rem]" /> : null}
        {wide ? <ResultsPanel className="min-w-0 flex-1" /> : null}
        {!wide ? (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            <div
              role="tablist"
              aria-label="Workspace sections"
              className="flex shrink-0 gap-1 rounded-lg border border-edge bg-surface p-1"
            >
              {(['workspace', 'results'] as MobileView[]).map((view) => (
                <button
                  key={view}
                  type="button"
                  role="tab"
                  aria-selected={mobileView === view}
                  onClick={() => setMobileView(view)}
                  className={`h-8 flex-1 rounded-md text-xs font-medium transition-colors ${
                    mobileView === view ? 'bg-surface-2 text-fg' : 'text-fg-muted'
                  }`}
                >
                  {view === 'workspace' ? 'Source' : 'Results'}
                </button>
              ))}
            </div>
            {mobileView === 'workspace' ? (
              <WorkspacePanel className="min-h-0 flex-1" />
            ) : (
              <ResultsPanel className="min-h-0 flex-1" />
            )}
          </div>
        ) : null}
      </main>

      <footer className="flex h-7 shrink-0 items-center gap-3 border-t border-edge bg-surface px-3 text-[11px] text-fg-subtle">
        <span>
          Mode <code className="font-mono">{health.data?.mode ?? '—'}</code>
        </span>
        <span className="hidden sm:inline">
          Press <kbd className="font-mono">Ctrl</kbd> + <kbd className="font-mono">Enter</kbd> to run ·{' '}
          <kbd className="font-mono">Ctrl</kbd> + <kbd className="font-mono">K</kbd> for commands
        </span>
      </footer>

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onCompare={(runId) => {
          setCompareRunId(runId);
          setCompareOpen(true);
          setHistoryOpen(false);
        }}
      />
      <CompareDialog
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        initialRunId={compareRunId}
      />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
