import { create } from 'zustand';

export type ToastKind = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
  detail?: string;
}

interface ToastState {
  toasts: Toast[];
  push: (kind: ToastKind, text: string, detail?: string) => number;
  dismiss: (id: number) => void;
  clear: () => void;
}

let counter = 0;

/** Auto-dismiss delay per kind; errors stay longer because they carry state. */
const LIFETIME: Record<ToastKind, number> = {
  success: 4200,
  info: 4200,
  warning: 6500,
  error: 9000,
};

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (kind, text, detail) => {
    counter += 1;
    const id = counter;
    const toast: Toast = { id, kind, text, detail };
    set((state) => ({ toasts: [...state.toasts, toast] }));
    window.setTimeout(() => get().dismiss(id), LIFETIME[kind]);
    return id;
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
  clear: () => set({ toasts: [] }),
}));

/** Imperative helper usable outside React components. */
export const toast = {
  success: (text: string, detail?: string) => useToastStore.getState().push('success', text, detail),
  error: (text: string, detail?: string) => useToastStore.getState().push('error', text, detail),
  info: (text: string, detail?: string) => useToastStore.getState().push('info', text, detail),
  warning: (text: string, detail?: string) => useToastStore.getState().push('warning', text, detail),
};
