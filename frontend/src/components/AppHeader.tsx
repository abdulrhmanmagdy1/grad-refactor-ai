import type { ApiError } from "../api/client";
import type { HealthResponse, ProviderInfo } from "../api/contracts";
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

function modelIdentity(provider: ProviderInfo): { model: string; revision: string | null; adapter: string } {
  const model = provider.model_id ?? "Not reported";
  const revision = provider.model_revision ? shortHash(provider.model_revision) : null;
  const adapter = provider.adapter_id
    ? `Adapter ${provider.adapter_id}${provider.adapter_sha256 ? ` (sha256 ${shortHash(provider.adapter_sha256)})` : ""}`
    : "Base model, no adapter";
  return { model, revision, adapter };
}

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
          <div>
            <h1 className="brand__name">Multi-Agent Refactoring for Python</h1>
            <p className="brand__tagline">Guard-clause proposals with separate verification</p>
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
  const identity = modelIdentity(provider);
  return (
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
            {identity.model}
            {identity.revision ? <span className="service__sub"> at revision {identity.revision}</span> : null}
          </span>
          <span className="service__note">
            {identity.adapter}
            {provider.device ? `, device ${provider.device}` : ""}
          </span>
        </dd>
      </div>
      <div className="service__item">
        <dt>Model status</dt>
        <dd>
          <span className="service__value" data-tone={provider.ready ? "pass" : "warn"}>
            {provider.ready ? "Ready" : "Not ready"}
          </span>
          {!provider.ready && provider.detail ? <span className="service__note">{provider.detail}</span> : null}
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
  );
}

export function FakeProviderBanner() {
  return (
    <div className="fake-banner" role="note" aria-label="Fake provider warning">
      <div className="fake-banner__inner">
        <p>
          <strong>Fake provider: these are not language-model results.</strong> The service is running its
          deterministic test provider, so every proposal, explanation and review here comes from fixed rules. Do
          not present these results as AI output.
        </p>
      </div>
    </div>
  );
}
