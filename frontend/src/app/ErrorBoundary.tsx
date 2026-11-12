import { Component, type ErrorInfo, type ReactNode } from 'react';

import { Button } from '@/shared/ui/Button';

interface Props {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time failures so a single broken panel never blanks the app.
 *
 * The stack is logged locally (no third-party reporting service — the project
 * runs with a zero budget) and the user gets a recovery action.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled UI error:', error, info.componentStack);
  }

  private readonly reset = () => this.setState({ error: null });

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-8 text-center">
        <h1 className="text-base font-semibold">The interface hit an unexpected error</h1>
        <p className="max-w-md text-xs text-fg-muted">
          The API is unaffected. Reload the panel to continue; the error was written to the browser
          console for diagnosis.
        </p>
        <pre className="scroll-thin max-h-40 w-full max-w-xl overflow-auto rounded-md border border-edge bg-surface-2 p-3 text-left font-mono text-[11px] text-fg-muted">
          {error.message}
        </pre>
        <Button variant="primary" onClick={this.reset}>
          Try again
        </Button>
      </div>
    );
  }
}
