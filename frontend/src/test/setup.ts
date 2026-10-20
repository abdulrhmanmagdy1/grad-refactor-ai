import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// findBy* and waitFor give up after this long; generous for a busy laptop.
configure({ asyncUtilTimeout: 5_000 });

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
