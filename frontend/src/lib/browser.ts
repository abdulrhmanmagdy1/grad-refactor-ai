/** Clipboard and file-save helpers. Neither touches the person's files without a click. */

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to the selection-based copy below.
  }
  const exec = (document as Document & { execCommand?: unknown }).execCommand;
  if (typeof exec !== "function") return false;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  try {
    area.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

/** Offers a Blob to the browser as a download with the given file name. */
export function saveBlob(blob: Blob, filename: string): void {
  if (typeof URL.createObjectURL !== "function") {
    throw new Error("This browser cannot save files from the page.");
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoke later: some browsers read the URL after click() returns.
  setTimeout(() => {
    if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url);
  }, 10_000);
}
