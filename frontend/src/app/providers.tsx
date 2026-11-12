import { useEffect, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ErrorBoundary } from './ErrorBoundary';
import { Toaster } from '@/shared/ui/Toast';
import { applyTheme, useThemeStore } from '@/features/theme/theme.store';

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // The service is local: refetching on every window focus adds noise.
        staleTime: 10_000,
        gcTime: 5 * 60_000,
        retry: 1,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

/** Keeps the document theme in sync with the store (the boot script set it pre-paint). */
function ThemeBridge({ children }: { children: ReactNode }) {
  const theme = useThemeStore((state) => state.theme);
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  return <>{children}</>;
}

/** Application providers: error boundary, data layer, theme, notifications. */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeBridge>{children}</ThemeBridge>
        <Toaster />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
