import type { ApiError } from "../api/client";

export interface SyntaxLocation {
  line: number;
  column: number | null;
}

/** Line and column from an invalid_syntax error's details, when the service reported them. */
export function syntaxLocation(error: ApiError | null): SyntaxLocation | null {
  if (!error || error.code !== "invalid_syntax") return null;
  for (const item of error.details) {
    const line = item.line ?? item.lineno;
    if (typeof line === "number" && Number.isInteger(line) && line >= 1) {
      const column = item.column ?? item.offset;
      return { line, column: typeof column === "number" && column >= 1 ? column : null };
    }
  }
  return null;
}

interface ErrorCopy {
  title: string;
  advice: string | null;
}

export function describeSubmissionError(error: ApiError): ErrorCopy {
  switch (error.code) {
    case "invalid_syntax":
      return {
        title: "The code is not valid Python",
        advice: "Fix the syntax error and submit again. The service only parsed the code; it did not run it.",
      };
    case "validation_error":
      return { title: "The request was not accepted", advice: null };
    case "reference_case_mismatch":
      return {
        title: "The code does not match the demonstration case",
        advice:
          "Reference tests apply only to the exact case code. Restore the case code, or remove the link and submit without reference tests.",
      };
    case "unknown_reference_case":
      return {
        title: "The demonstration case is not available",
        advice: "Reload the list of cases, or remove the link and submit without reference tests.",
      };
    case "busy": {
      const wait = error.retryAfterSeconds;
      return {
        title: "The service is busy",
        advice:
          wait !== null
            ? `The run queue is full. Wait about ${wait} s for queued runs to finish, then submit again.`
            : "The run queue is full. Wait for queued runs to finish, then submit again.",
      };
    }
    case "service_unavailable":
      return {
        title: "The run service is not running",
        advice: "Start or restart the backend, then submit again.",
      };
    case "payload_too_large":
      return { title: "The code is too large to send", advice: "Shorten the code and submit again." };
    case "network_error":
      return {
        title: "Cannot reach the service",
        advice: "Check that the backend is running on 127.0.0.1:8000, then submit again.",
      };
    case "timeout":
      return { title: "The service did not answer in time", advice: "Submit again in a moment." };
    case "internal_error":
      return {
        title: "The service hit an unexpected error",
        advice: "Submit again. If the error repeats, the server log has the details.",
      };
    default:
      return { title: "The run could not be started", advice: null };
  }
}

interface SubmissionErrorViewProps {
  error: ApiError;
  location: SyntaxLocation | null;
  onGoToLine?: (location: SyntaxLocation) => void;
  onUnlinkCase?: () => void;
  onRestoreCaseCode?: () => void;
  onReloadCases?: () => void;
  onRetry?: () => void;
  retryDisabled?: boolean;
  onDismiss?: () => void;
  inputNote?: string;
}

export function SubmissionErrorView({
  error,
  location,
  onGoToLine,
  onUnlinkCase,
  onRestoreCaseCode,
  onReloadCases,
  onRetry,
  retryDisabled,
  onDismiss,
  inputNote = "Your code was not changed.",
}: SubmissionErrorViewProps) {
  const copy = describeSubmissionError(error);
  const caseProblem = error.code === "reference_case_mismatch" || error.code === "unknown_reference_case";
  const validationItems =
    error.code === "validation_error" && error.details.length > 1
      ? error.details
          .map((item) => (typeof item.message === "string" ? item.message : null))
          .filter((message): message is string => message !== null)
      : [];
  return (
    <div className="callout" data-tone={error.code === "busy" ? "warn" : "fail"} role="alert">
      <p className="callout__title">{copy.title}</p>
      <p className="callout__text">
        {error.message}
        {error.kind === "http" && error.code ? (
          <>
            {" "}
            <code className="code-tag">{error.code}</code>
          </>
        ) : null}
      </p>
      {validationItems.length > 0 ? (
        <ul className="callout__list">
          {validationItems.map((message, index) => (
            <li key={index}>{message}</li>
          ))}
        </ul>
      ) : null}
      {location ? (
        <p className="callout__text">
          Line {location.line}
          {location.column !== null ? `, column ${location.column}` : ""}.{" "}
          {onGoToLine ? (
            <button type="button" className="link-button" onClick={() => onGoToLine(location)}>
              Go to line {location.line}
            </button>
          ) : null}
        </p>
      ) : null}
      {copy.advice ? <p className="callout__text">{copy.advice}</p> : null}
      <div className="callout__actions">
        {error.code === "reference_case_mismatch" && onRestoreCaseCode ? (
          <button type="button" className="button button--small" onClick={onRestoreCaseCode}>
            Restore the case code
          </button>
        ) : null}
        {error.code === "unknown_reference_case" && onReloadCases ? (
          <button type="button" className="button button--small" onClick={onReloadCases}>
            Reload cases
          </button>
        ) : null}
        {caseProblem && onUnlinkCase ? (
          <button type="button" className="button button--small" onClick={onUnlinkCase}>
            Remove the case link
          </button>
        ) : null}
        {error.transient && onRetry ? (
          <button type="button" className="button button--small" onClick={onRetry} disabled={retryDisabled}>
            Submit again
          </button>
        ) : null}
        {onDismiss ? (
          <button type="button" className="button button--small button--quiet" onClick={onDismiss}>
            Dismiss
          </button>
        ) : null}
      </div>
      <p className="callout__foot">{inputNote}</p>
    </div>
  );
}
