/**
 * Bundled Monaco setup.
 *
 * The editor and its web worker are imported from `node_modules` (never a CDN),
 * so the interface keeps working with no internet access. The module is loaded
 * lazily: the application shell paints and stays interactive before the ~4 MB
 * editor bundle is parsed.
 */
import type * as Monaco from 'monaco-editor';

let monacoPromise: Promise<typeof Monaco> | null = null;

const DARK_THEME: Monaco.editor.IStandaloneThemeData = {
  base: 'vs-dark',
  inherit: true,
  rules: [],
  colors: {
    'editor.background': '#0b0e13',
    'editorGutter.background': '#0b0e13',
    'editor.lineHighlightBackground': '#141821',
    'editorLineNumber.foreground': '#4a5468',
    'editorLineNumber.activeForeground': '#98a1b3',
    'editor.selectionBackground': '#2a3550',
    'editorIndentGuide.background1': '#1c2331',
  },
};

const LIGHT_THEME: Monaco.editor.IStandaloneThemeData = {
  base: 'vs',
  inherit: true,
  rules: [],
  colors: {
    'editor.background': '#ffffff',
    'editor.lineHighlightBackground': '#f3f5f9',
    'editorLineNumber.foreground': '#a3abba',
    'editorLineNumber.activeForeground': '#556070',
    'editorIndentGuide.background1': '#e8ebf1',
  },
};

/** Load Monaco once and register the local themes. */
export function loadMonaco(): Promise<typeof Monaco> {
  if (!monacoPromise) {
    monacoPromise = (async () => {
      const monaco = await import('monaco-editor');
      const { loader } = await import('@monaco-editor/react');
      const editorWorker = (await import('monaco-editor/editor/editor.worker?worker')).default;

      (self as unknown as { MonacoEnvironment: { getWorker: () => Worker } }).MonacoEnvironment = {
        getWorker: () => new editorWorker(),
      };

      monaco.editor.defineTheme('refactor-dark', DARK_THEME);
      monaco.editor.defineTheme('refactor-light', LIGHT_THEME);
      loader.config({ monaco });

      return monaco;
    })();
  }
  return monacoPromise;
}
