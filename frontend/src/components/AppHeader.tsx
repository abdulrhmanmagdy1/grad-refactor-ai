import type { ApiError } from "../api/client";
import type { HealthResponse } from "../api/contracts";
import { shortHash } from "../lib/format";
import { PROVIDER_LABELS } from "../lib/labels";

function BrandMark() {
  // Three bars stepping inwards (nested code) beside one flat column (guard clauses).
  return (
    <svg className="brand__mark" viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="30" height="30" rx="7" className="brand__mark-bg" />
      <rect x="6" y="8" width="9" height="2.6" rx="1.3" className="brand__mark-fg" />
      <rect x="8.5" y="13.7" width="6.5" height="2.6" rx="1.3" className="brand__mark-fg" opacity="0.75" />
      <rect x="11" y="19.4" width="4" height="2.6" rx="1.3" className="brand__mark-fg" opacity="0.5" />
      <rect x="18.5" y="8" width="7.5" height="2.6" rx="1.3" className="brand__mark-fg" />
      <rect x="18.5" y="13.7" width="7.5" height="2.6" rx="1.3" className="brand__mark-fg" />
      <rect x="18.5" y="19.4" width="7.5" height="2.6" rx="1.3" className="brand__mark-fg" />
    </svg>
  );
}

export type ModelState = "ready" | "loading" | "adapter_missing" | "not_ready" | "paused";

/** How far the model is from serving runs, from GET /health. */
export function modelState(health: HealthResponse): ModelState {
  const { provider } = health;
  if (health.refactor_use_adapter && provider.provider_mode === "local_model" && !provider.adapter_id) {
    return "adapter_missing";
  }
  if (provider.ready) return "ready";
  // The service pauses this model while the project review model uses the GPU.
  if ((provider.detail ?? "").startsWith("Paused:")) return "paused";
  return /\bloading\b/i.test(provider.detail ?? "") ? "loading" : "not_ready";
}

export interface RefactorWeights {
  value: string;
  note: string;
  tone: "info" | "warn" | "fail" | "neutral";
}

/** Which weights the refactoring role uses. Analysis and review always use the base model. */
export function refactorWeights(health: HealthResponse): RefactorWeights {
  const { provider } = health;
  if (health.mode === "fake" || provider.provider_mode === "fake") {
    return { value: "Fixed rules (fake provider)", note: "No model is used.", tone: "warn" };
  }
  if (health.refactor_use_adapter) {
    if (!provider.adapter_id) {
      return {
        value: "Adapter requested, none configured",
        note: "Runs fail instead of using the base model.",
        tone: "fail",
      };
    }
    const hash = provider.adapter_sha256 ? ` (sha256 ${shortHash(provider.adapter_sha256)})` : "";
    return {
      value: "Fine-tuned LoRA adapter",
      note: `${provider.adapter_id}${hash}. Analysis and review use the base model.`,
      tone: "info",
    };
  }
  return {
    value: "Base model",
    note: provider.adapter_id
      ? `Adapter ${provider.adapter_id} is configured but not used.`
      : "No adapter is used by any role.",
    tone: "neutral",
  };
}

const MODEL_STATE_TEXT: Record<ModelState, { label: string; tone: string; notice: string }> = {
  ready: { label: "Ready", tone: "pass", notice: "" },
  loading: { label: "Loading", tone: "progress", notice: "The model is loading" },
  adapter_missing: { label: "Adapter missing", tone: "fail", notice: "The fine-tuned adapter is missing" },
  not_ready: { label: "Not ready", tone: "warn", notice: "The model is not ready" },
  paused: { label: "Paused", tone: "neutral", notice: "" },
};

interface AppHeaderProps {
  health: HealthResponse | null;
  error: ApiError | null;
  loading: boolean;
  onRetry: () => void;
}

export function AppHeader({ health, error, loading, onRetry }: AppHeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <div className="brand">
          <BrandMark />
          <div className="brand__text">
            <h1 className="brand__name">Multi-Agent Refactoring for Python</h1>
          </div>
        </div>
        <section className="service" aria-label="Service status">
          {health ? (
            <HealthDetails health={health} stale={error !== null} />
          ) : loading ? (
            <p className="service__message">Checking the service…</p>
          ) : null}
          {error ? (
            <div className="service__error" role="status">
              <span>
                <strong>Service unreachable.</strong> {error.message}
              </span>
              <button type="button" className="button button--small" onClick={onRetry}>
                Check again
              </button>
            </div>
          ) : null}
        </section>
      </div>
    </header>
  );
}

function HealthDetails({ health, stale }: { health: HealthResponse; stale: boolean }) {
  const { provider, runner, queue } = health;
  const fake = health.mode === "fake" || provider.provider_mode === "fake";
  const revision = provider.model_revision ? shortHash(provider.model_revision) : null;
  const weights = refactorWeights(health);
  const state = modelState(health);
  const stateText = MODEL_STATE_TEXT[state];
  const pill = fake
    ? { text: "Demo mode", tone: "warn" }
    : state === "ready"
      ? { text: health.refactor_use_adapter ? "Fine-tuned model ready" : "Base model ready", tone: "pass" }
      : { text: stateText.label, tone: stateText.tone };
  return (
    <>
      <details className="service__details">
        <summary className="service__pill" data-tone={pill.tone}>
          {pill.text}
        </summary>
      <dl className="service__list" data-stale={stale ? "true" : undefined}>
        <div className="service__item">
          <dt>Provider</dt>
          <dd>
            <span className="service__value" data-tone={fake ? "warn" : "info"}>
              {PROVIDER_LABELS[fake ? "fake" : health.mode]}
            </span>
          </dd>
        </div>
        <div className="service__item service__item--model">
          <dt>Model</dt>
          <dd>
            <span className="service__value service__mono" title={provider.model_revision ?? undefined}>
              {provider.model_id ?? "Not reported"}
              {revision ? <span className="service__sub"> at revision {revision}</span> : null}
            </span>
            <span className="service__note">{provider.device ? `Device ${provider.device}` : "Device not reported"}</span>
          </dd>
        </div>
        <div className="service__item service__item--weights">
          <dt>Refactoring role</dt>
          <dd>
            <span className="service__value" data-tone={weights.tone}>
              {weights.value}
            </span>
            <span className="service__note">{weights.note}</span>
          </dd>
        </div>
        <div className="service__item">
          <dt>Model status</dt>
          <dd>
            <span className="service__value" data-tone={stateText.tone}>
              {stateText.label}
            </span>
          </dd>
        </div>
        <div className="service__item">
          <dt>Reference tests</dt>
          <dd>
            <span className="service__value" data-tone={runner.enabled ? "pass" : "neutral"}>
              {runner.enabled ? "Runner enabled" : "Runner disabled"}
            </span>
            {!runner.enabled && runner.reason ? <span className="service__note">{runner.reason}</span> : null}
          </dd>
        </div>
        <div className="service__item">
          <dt>Queue</dt>
          <dd>
            <span className="service__value">
              {queue.pending} of {queue.max_pending} waiting
            </span>
            <span className="service__note">API {health.version}</span>
          </dd>
        </div>
      </dl>
      </details>
      {state !== "ready" && state !== "paused" ? (
        <p className="service__notice" data-tone={stateText.tone} role="status">
          <strong>{stateText.notice}.</strong> {provider.detail ?? "The service gave no reason."}
        </p>
      ) : null}
    </>
  );
}

export function FakeProviderBanner() {
  return (
    <div className="fake-banner" role="note" aria-label="Fake provider warning">
      <div className="fake-banner__inner">
        <span className="fake-banner__icon" aria-hidden="true">
          <svg viewBox="0 0 16 16" width="16" height="16" focusable="false">
            <path d="M8 2.2 14.4 13.4H1.6Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            <path d="M8 6.4v3.2M8 11.5v.1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
        <p>
          <strong>Demo mode: results come from a test stub, not the AI model.</strong>
        </p>
      </div>
    </div>
  );
}
