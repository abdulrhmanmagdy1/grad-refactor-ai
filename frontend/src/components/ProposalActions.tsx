import { useEffect, useRef, useState } from "react";
import { type ApiError, fetchProposal, toApiError } from "../api/client";
import { copyText, saveBlob } from "../lib/browser";
import { Icon } from "./Icon";

type CopyState = "idle" | "copied" | "failed";
type DownloadState = { status: "idle" } | { status: "pending" } | { status: "done"; filename: string } | { status: "error"; error: ApiError };

/** Copy and download for a run that has a proposal. Neither changes the editor or any file. */
export function ProposalActions({ runId, proposedCode }: { runId: string; proposedCode: string }) {
  const [copy, setCopy] = useState<CopyState>("idle");
  const [download, setDownload] = useState<DownloadState>({ status: "idle" });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);

  const onCopy = async () => {
    const ok = await copyText(proposedCode);
    if (!mounted.current) return;
    setCopy(ok ? "copied" : "failed");
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopy("idle"), 4000);
  };

  const onDownload = async () => {
    setDownload({ status: "pending" });
    try {
      const file = await fetchProposal(runId);
      saveBlob(file.blob, file.filename);
      if (mounted.current) setDownload({ status: "done", filename: file.filename });
    } catch (error) {
      if (mounted.current) setDownload({ status: "error", error: toApiError(error) });
    }
  };

  return (
    <div className="proposal-actions">
      <div className="proposal-actions__buttons">
        <button type="button" className="button button--small" onClick={() => void onCopy()}>
          <Icon name="copy" />
          Copy proposed code
        </button>
        <button
          type="button"
          className="button button--small"
          onClick={() => void onDownload()}
          disabled={download.status === "pending"}
        >
          <Icon name="download" />
          {download.status === "pending" ? "Downloading…" : "Download proposal"}
        </button>
      </div>
      <p className="proposal-actions__status" role="status">
        {copy === "copied" ? "Proposed code copied to the clipboard." : null}
        {copy === "failed" ? "Copy failed. Select the code in the side-by-side view and copy it manually." : null}
        {download.status === "done" ? `Download started: ${download.filename}.` : null}
      </p>
      {download.status === "error" ? (
        <p className="field-message" data-tone="fail" role="alert">
          Download failed: {download.error.message}
        </p>
      ) : null}
    </div>
  );
}
