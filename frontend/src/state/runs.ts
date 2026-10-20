/**
 * Client-side state of the runs this page knows about: the run submitted here, runs
 * reopened from the history, and which of them is displayed. Runs whose poll state is
 * "polling" each get a RunPoller; everything else is a snapshot of the last answer.
 */

import type { ApiError } from "../api/client";
import {
  type RunAccepted,
  type RunCreateRequest,
  type RunRecord,
  type RunStatus,
  isTerminalStatus,
} from "../api/contracts";
import type { PollEvent } from "../lib/polling";

export type PollState = "idle" | "polling" | "done" | "timed_out" | "failed";

export interface RunEntry {
  runId: string;
  /** Latest record from the service, or null before the first answer. */
  record: RunRecord | null;
  /** The request this page submitted, or null for runs opened from the history. */
  request: RunCreateRequest | null;
  /** Latest status known from RunAccepted or a record. */
  knownStatus: RunStatus | null;
  /** Client clock (ms) when this page started tracking the run. */
  trackedSince: number;
  poll: PollState;
  /** Incremented to start a fresh poller (first start, reopen, resume). */
  pollGeneration: number;
  /** Set while a transient polling error is being retried. */
  retry: { error: ApiError; attempt: number } | null;
  /** Error that stopped polling or loading. */
  error: ApiError | null;
  /** Set when polling gave up after the maximum wait. */
  timedOutAfterMs: number | null;
  /** True while the record is being (re)loaded for display. */
  loading: boolean;
  /** Distinct statuses seen in order, to label a correction (verifying -> generating). */
  statusTrail: RunStatus[];
}

export interface RunsState {
  entries: Record<string, RunEntry>;
  selectedId: string | null;
}

export type RunsAction =
  | { type: "submitted"; accepted: RunAccepted; request: RunCreateRequest; now: number }
  | { type: "open"; runId: string; now: number }
  | { type: "loaded"; record: RunRecord }
  | { type: "load_failed"; runId: string; error: ApiError }
  | { type: "poll"; runId: string; event: PollEvent }
  | { type: "resume"; runId: string }
  | { type: "removed"; runId: string }
  | { type: "select"; runId: string | null };

export const initialRunsState: RunsState = { entries: {}, selectedId: null };

function appendStatus(trail: RunStatus[], status: RunStatus): RunStatus[] {
  return trail[trail.length - 1] === status ? trail : [...trail, status];
}

function newEntry(runId: string, now: number): RunEntry {
  return {
    runId,
    record: null,
    request: null,
    knownStatus: null,
    trackedSince: now,
    poll: "idle",
    pollGeneration: 0,
    retry: null,
    error: null,
    timedOutAfterMs: null,
    loading: false,
    statusTrail: [],
  };
}

function withRecord(entry: RunEntry, record: RunRecord): RunEntry {
  return {
    ...entry,
    record,
    knownStatus: record.status,
    statusTrail: appendStatus(entry.statusTrail, record.status),
  };
}

function update(state: RunsState, runId: string, change: (entry: RunEntry) => RunEntry): RunsState {
  const entry = state.entries[runId];
  if (!entry) return state;
  const next = change(entry);
  return next === entry ? state : { ...state, entries: { ...state.entries, [runId]: next } };
}

export function runsReducer(state: RunsState, action: RunsAction): RunsState {
  switch (action.type) {
    case "submitted": {
      const { accepted } = action;
      const entry: RunEntry = {
        ...newEntry(accepted.run_id, action.now),
        request: action.request,
        knownStatus: accepted.status,
        poll: "polling",
        pollGeneration: 1,
        statusTrail: [accepted.status],
      };
      return { entries: { ...state.entries, [accepted.run_id]: entry }, selectedId: accepted.run_id };
    }
    case "open": {
      const existing = state.entries[action.runId];
      if (existing?.poll === "polling") return { ...state, selectedId: action.runId };
      const entry = existing
        ? { ...existing, loading: true, error: null }
        : { ...newEntry(action.runId, action.now), loading: true };
      return { entries: { ...state.entries, [action.runId]: entry }, selectedId: action.runId };
    }
    case "loaded": {
      const { record } = action;
      const existing = state.entries[record.run_id];
      // A late answer for a run that was deleted (or never opened) is ignored.
      if (!existing) return state;
      let entry: RunEntry = { ...withRecord(existing, record), loading: false, error: null };
      if (isTerminalStatus(record.status)) {
        entry = { ...entry, poll: "done", retry: null, timedOutAfterMs: null };
      } else if (existing.poll !== "polling") {
        entry = {
          ...entry,
          poll: "polling",
          pollGeneration: existing.pollGeneration + 1,
          retry: null,
          timedOutAfterMs: null,
        };
      }
      return { ...state, entries: { ...state.entries, [record.run_id]: entry } };
    }
    case "load_failed":
      return update(state, action.runId, (entry) => ({ ...entry, loading: false, error: action.error }));
    case "poll":
      return update(state, action.runId, (entry) => {
        if (entry.poll !== "polling") return entry;
        const { event } = action;
        switch (event.type) {
          case "update":
            return { ...withRecord(entry, event.record), retry: null, error: null };
          case "terminal":
            return { ...withRecord(entry, event.record), poll: "done", retry: null, error: null };
          case "retrying":
            return { ...entry, retry: { error: event.error, attempt: event.attempt } };
          case "fatal":
            return { ...entry, poll: "failed", retry: null, error: event.error };
          case "timeout":
            return {
              ...entry,
              poll: "timed_out",
              retry: null,
              error: event.lastError,
              timedOutAfterMs: event.waitedMs,
            };
        }
      });
    case "resume":
      return update(state, action.runId, (entry) =>
        entry.poll === "polling"
          ? entry
          : {
              ...entry,
              poll: "polling",
              pollGeneration: entry.pollGeneration + 1,
              retry: null,
              error: null,
              timedOutAfterMs: null,
            },
      );
    case "removed": {
      if (!(action.runId in state.entries) && state.selectedId !== action.runId) return state;
      const entries = { ...state.entries };
      delete entries[action.runId];
      return { entries, selectedId: state.selectedId === action.runId ? null : state.selectedId };
    }
    case "select":
      return { ...state, selectedId: action.runId };
  }
}

export function isAnyRunActive(state: RunsState): boolean {
  return Object.values(state.entries).some((entry) => entry.poll === "polling");
}

export function selectedEntry(state: RunsState): RunEntry | null {
  return state.selectedId === null ? null : (state.entries[state.selectedId] ?? null);
}
