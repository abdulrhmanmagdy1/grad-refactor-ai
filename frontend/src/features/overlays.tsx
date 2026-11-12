import { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '@/shared/api/endpoints';
import { errorMessage } from '@/shared/api/http';
import { useResultsStore, type ResultTab } from '@/features/results/results.store';
import { useThemeStore } from '@/features/theme/theme.store';
import { useRunPipeline } from '@/features/workspace/useRunPipeline';
import { downloadText } from '@/shared/lib/download';
import { shortId } from '@/shared/lib/format';
import { Dialog } from '@/shared/ui/Overlays';
import { toast } from '@/shared/ui/toast.store';

interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void | Promise<void>;
}

/** Command palette: every primary action is reachable from the keyboard. */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const currentRunId = useResultsStore((state) => state.currentRunId);
  const setTab = useResultsStore((state) => state.setTab);
  const { runPipeline } = useRunPipeline();

  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const list: Command[] = [
      {
        id: 'run',
        label: 'Run the multi-agent pipeline',
        hint: 'Ctrl+Enter',
        run: () => void runPipeline(),
      },
      {
        id: 'theme',
        label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`,
        run: toggleTheme,
      },
    ];

    const tabs: ResultTab[] = ['diff', 'verification', 'metrics', 'traces', 'tests', 'graph'];
    for (const tab of tabs) {
      list.push({
        id: `tab-${tab}`,
        label: `Show the ${tab} view`,
        run: () => setTab(tab),
      });
    }

    if (currentRunId) {
      list.push({
        id: 'export',
        label: 'Export the current run as a Markdown report',
        run: async () => {
          try {
            const markdown = await api.report(currentRunId);
            downloadText(`run-${shortId(currentRunId)}.md`, markdown, 'text/markdown');
            toast.success('Markdown report exported.');
          } catch (error) {
            toast.error('The report could not be exported.', errorMessage(error));
          }
        },
      });
    }

    return list;
  }, [theme, toggleTheme, currentRunId, setTab, runPipeline]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) => command.label.toLowerCase().includes(needle));
  }, [commands, query]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((index) => (index + 1) % Math.max(filtered.length, 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((index) => (index - 1 + filtered.length) % Math.max(filtered.length, 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const command = filtered[active];
      if (command) {
        void command.run();
        onClose();
      }
    }
  };

  const inputId = 'command-palette-input';

  return (
    <Dialog open={open} onClose={onClose} title="Command palette" size="sm">
      <label htmlFor={inputId} className="sr-only">
        Search commands
      </label>
      <input
        id={inputId}
        ref={inputRef}
        value={query}
        placeholder="Type a command…"
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={onKeyDown}
        className="h-9 w-full rounded-md border border-edge bg-surface-2 px-2.5 text-sm text-fg placeholder:text-fg-subtle"
      />
      <ul ref={listRef} className="mt-2 max-h-72 overflow-y-auto scroll-thin" role="listbox" aria-label="Commands">
        {filtered.length === 0 ? (
          <li className="px-2 py-3 text-xs text-fg-subtle">No command matches.</li>
        ) : (
          filtered.map((command, index) => (
            <li key={command.id}>
              <button
                type="button"
                role="option"
                aria-selected={index === active}
                onMouseEnter={() => setActive(index)}
                onClick={() => {
                  void command.run();
                  onClose();
                }}
                className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs ${
                  index === active ? 'bg-accent-soft text-accent' : 'text-fg'
                }`}
              >
                <span>{command.label}</span>
                {command.hint ? (
                  <kbd className="font-mono text-[10px] text-fg-subtle">{command.hint}</kbd>
                ) : null}
              </button>
            </li>
          ))
        )}
      </ul>
    </Dialog>
  );
}

const SHORTCUTS: { keys: string[]; description: string }[] = [
  { keys: ['Ctrl', 'Enter'], description: 'Run the multi-agent pipeline' },
  { keys: ['Ctrl', 'K'], description: 'Open the command palette' },
  { keys: ['Ctrl', 'B'], description: 'Toggle the run history drawer' },
  { keys: ['Ctrl', '/'], description: 'Show this shortcut list' },
  { keys: ['Esc'], description: 'Close the active dialog or panel' },
  { keys: ['←', '→'], description: 'Move between result tabs' },
];

/** Reference sheet for the keyboard shortcuts. */
export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Keyboard shortcuts"
      description="Every primary action is reachable without a mouse."
      size="sm"
    >
      <dl className="flex flex-col gap-2">
        {SHORTCUTS.map((shortcut) => (
          <div key={shortcut.description} className="flex items-center justify-between gap-3">
            <dt className="text-xs text-fg-muted">{shortcut.description}</dt>
            <dd className="flex shrink-0 gap-1">
              {shortcut.keys.map((key) => (
                <kbd
                  key={key}
                  className="rounded border border-edge bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-fg-muted"
                >
                  {key}
                </kbd>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </Dialog>
  );
}
