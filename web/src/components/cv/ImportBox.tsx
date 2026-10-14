import { useRef, useState } from "react";
import {
  CircleCheck,
  CircleHelp,
  ClipboardPaste,
  ExternalLink,
  FileUp,
  Images,
  Loader2,
  TriangleAlert,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import {
  IMPORT_TYPES,
  MAX_IMPORT_FILES,
  MAX_IMPORT_TEXT_CHARS,
  UploadError,
  formatBytes,
  prepareImportFile,
  readAsDataUri,
} from "@/lib/upload";
import type { CvImportResult } from "@/types";

/** Where a reading came from. The draft notice words its claims by this: "in
 *  the PDF's own text" is not a thing to say about a paste. */
type ImportKind = "files" | "text";

/** A draft that is sitting in the editor, with what it was read from. */
export interface ImportedDraft {
  result: CvImportResult;
  kind: ImportKind;
  /** Object URLs of the uploaded files — or of the pasted text, as one
   *  nameless entry — so the original opens beside the draft. Created here,
   *  revoked by CvStudio, which owns the draft's lifetime. */
  sources: { name: string; url: string }[];
}

/** Free the object URLs of a draft nobody is showing any more. */
export function releaseDraft(draft: ImportedDraft): void {
  draft.sources.forEach((source) => URL.revokeObjectURL(source.url));
}

/**
 * Read a CV off page images, a PDF or pasted text into the editor (Master
 * scope only).
 *
 * This is the second place a model may put words on the Master CV, and the only
 * one with no text to hold them against: a photograph cannot be diffed. So the
 * card never saves — it fills the editor and leaves the Save button where it
 * always was — and what it says afterwards is deliberately not congratulatory.
 * The three check states are worded as three different claims because they are:
 * "every number was found", "these were not", and "nothing could be checked".
 * Collapsing the last into silence would read as the first.
 *
 * A paste is the one source that always has text to compare with, so it never
 * lands in the third state — but its numbers are all that is compared, and the
 * notice says so: a model handed text can still file a line under the wrong job.
 */
export function ImportBox({
  imported,
  unchanged,
  held,
  blocked,
  onStart,
  onDraft,
  onLoadHeld,
  onDropHeld,
  onDiscard,
}: {
  imported: ImportedDraft | null;
  /** The reading came out identical to the saved CV, so there is nothing to save. */
  unchanged: boolean;
  /** A reading that arrived after the editor changed — waiting to be asked for. */
  held: ImportedDraft | null;
  /** The editor holds unsaved edits of the user's own; an import would erase them. */
  blocked: boolean;
  /** Called as the read begins, so the page can tell later what changed meanwhile. */
  onStart: () => void;
  /** Called when the read ends. The page decides whether it may still land:
   *  this card only knows what was true when the button was pressed. */
  onDraft: (draft: ImportedDraft) => void;
  onLoadHeld: () => void;
  onDropHeld: () => void;
  onDiscard: () => void;
}) {
  const t = useT("cv");
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<ImportKind>("files");
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  // A ref, not `busy`: two clicks in one tick both read the same stale state
  // (web/src/CLAUDE.md), and the second would spend a second model call.
  const running = useRef(false);

  const problem = (e: unknown): string => {
    if (e instanceof UploadError) {
      if (e.problem === "type") return t("importUnsupported", { name: e.file });
      if (e.problem === "size") return t("importTooLarge", { name: e.file });
      return t("importUndecodable", { name: e.file });
    }
    // The backend's own sentence (a refusal, or the provider's error).
    return e instanceof ApiError ? e.message : t("importFailed");
  };

  const add = async (picked: FileList | File[]) => {
    setError(null);
    try {
      const ready: File[] = [];
      for (const file of Array.from(picked)) ready.push(await prepareImportFile(file));
      const next = [...files, ...ready];
      if (next.length > MAX_IMPORT_FILES) {
        setError(t("importTooMany", { max: MAX_IMPORT_FILES }));
        return;
      }
      setFiles(next);
    } catch (e) {
      setError(problem(e));
    }
  };

  // Trimmed, as the server counts it — so the counter and the refusal agree.
  const pasted = text.trim();
  const tooLong = pasted.length > MAX_IMPORT_TEXT_CHARS;
  const ready = kind === "text" ? pasted.length > 0 && !tooLong : files.length > 0;

  const read = async () => {
    if (running.current || !ready || blocked) return;
    running.current = true;
    setBusy(true);
    setError(null);
    onStart();
    try {
      if (kind === "text") {
        const result = await api.importCv({ text: pasted });
        // The paste as a file of its own, so "Original" opens it beside the
        // draft exactly as it opens an upload. The charset is spelled out:
        // without it a browser guesses, and guesses wrong for Vietnamese.
        const blob = new Blob([pasted], { type: "text/plain;charset=utf-8" });
        onDraft({ result, kind, sources: [{ name: "", url: URL.createObjectURL(blob) }] });
        setText("");
        return;
      }
      const payload = await Promise.all(
        files.map(async (file) => ({ name: file.name, data: await readAsDataUri(file) })),
      );
      const result = await api.importCv({ files: payload });
      onDraft({
        result,
        kind,
        sources: files.map((file) => ({ name: file.name, url: URL.createObjectURL(file) })),
      });
      setFiles([]);
    } catch (e) {
      setError(problem(e));
    } finally {
      running.current = false;
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="inline-flex items-center gap-1.5">
            <FileUp size={14} className="text-accent" /> {t("importTitle")}
          </span>
        </CardTitle>
      </CardHeader>
      <CardBody className="pt-3">
        {/* Whatever is in the other tab stays there: switching is a way to
            look, and losing six picked pages to it would be a punishment. */}
        <div className="mb-3 inline-flex items-center gap-0.5 rounded-lg border p-0.5">
          {(
            [
              { id: "files", label: t("importModeFiles"), icon: Images },
              { id: "text", label: t("importModeText"), icon: ClipboardPaste },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              aria-pressed={kind === id}
              disabled={busy}
              onClick={() => {
                setKind(id);
                setError(null);
              }}
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium transition-colors disabled:opacity-60",
                kind === id
                  ? "bg-accent/12 text-ink"
                  : "text-ink-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>

        {kind === "text" ? (
          <div>
            <textarea
              rows={9}
              value={text}
              disabled={busy}
              onChange={(e) => setText(e.target.value)}
              placeholder={t("importTextPlaceholder")}
              aria-label={t("importModeText")}
              className="w-full resize-y rounded-lg border bg-surface px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-ink-muted/70 focus:border-accent focus:outline-none disabled:opacity-60"
            />
            <p
              className={cn(
                "mt-1 text-xs tabular-nums",
                tooLong ? "text-critical" : "text-ink-muted",
              )}
            >
              {t(tooLong ? "importTextTooLong" : "importTextCount", {
                count: pasted.length,
                max: MAX_IMPORT_TEXT_CHARS,
              })}
            </p>
          </div>
        ) : (
          <>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setOver(true);
              }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setOver(false);
                if (!busy) void add(e.dataTransfer.files);
              }}
              className={cn(
                "rounded-lg border border-dashed px-3 py-4 text-center transition-colors",
                over ? "border-accent bg-accent/8" : "bg-surface",
              )}
            >
              <input
                ref={input}
                type="file"
                multiple
                accept={IMPORT_TYPES.join(",")}
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) void add(e.target.files);
                  // Same file twice in a row must still fire `change`.
                  e.target.value = "";
                }}
              />
              <Button variant="outline" size="sm" disabled={busy} onClick={() => input.current?.click()}>
                {t("importChoose")}
              </Button>
              <p className="mt-2 text-xs text-ink-muted">{t("importDropHint")}</p>
            </div>

            {files.length > 0 && (
              <ul className="mt-3 flex flex-col gap-1">
                {files.map((file, i) => (
                  <li
                    key={`${file.name}-${i}`}
                    className="flex items-center gap-2 rounded-md bg-surface-2 px-2.5 py-1.5 text-xs"
                  >
                    <span className="tabular-nums text-ink-muted">{i + 1}</span>
                    <span className="min-w-0 flex-1 truncate text-ink">{file.name}</span>
                    <span className="shrink-0 tabular-nums text-ink-muted">{formatBytes(file.size)}</span>
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={t("importRemove", { name: file.name })}
                      title={t("importRemove", { name: file.name })}
                      onClick={() => setFiles(files.filter((_, j) => j !== i))}
                      className="shrink-0 rounded p-0.5 text-ink-muted hover:bg-surface hover:text-ink disabled:opacity-50"
                    >
                      <X size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        <p className="mt-3 text-xs leading-relaxed text-ink-muted">
          {t("importLead")} <span className="text-ink">{t("importLeadEmphasis")}</span>{" "}
          {t("importLeadRest")}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button onClick={read} disabled={!ready || busy || blocked}>
            {busy && <Loader2 size={15} className="animate-spin" />}
            {busy ? t("importReading") : t("importRead")}
          </Button>
          {busy && <span className="text-xs text-ink-muted">{t("importReadingHint")}</span>}
          {blocked && !busy && <span className="text-xs text-accent">{t("importBlocked")}</span>}
        </div>

        {error && <p className="mt-3 text-sm text-critical">{error}</p>}

        {held && (
          <div className="mt-4 rounded-lg border border-accent/40 bg-accent/5 p-3 text-xs leading-relaxed">
            <p className="text-sm font-medium text-ink">{t("importHeldTitle")}</p>
            <p className="mt-1 text-ink-muted">{t("importHeldBody")}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={onLoadHeld}>
                {t("importHeldLoad")}
              </Button>
              <Button size="sm" variant="ghost" onClick={onDropHeld}>
                {t("importHeldDrop")}
              </Button>
            </div>
          </div>
        )}

        {imported && <DraftNotice draft={imported} unchanged={unchanged} onDiscard={onDiscard} />}
      </CardBody>
    </Card>
  );
}

function DraftNotice({
  draft,
  unchanged,
  onDiscard,
}: {
  draft: ImportedDraft;
  unchanged: boolean;
  onDiscard: () => void;
}) {
  const t = useT("cv");
  const { result, sources, kind } = draft;
  const missing = result.unbacked_numbers;
  const pasted = kind === "text";

  return (
    <div className="mt-4 rounded-lg border border-accent/40 bg-accent/5 p-3 text-xs leading-relaxed">
      {/* Re-importing the CV you already saved leaves nothing unsaved, and a
          card insisting "not saved" beside a greyed-out Save button would be
          telling the user to do something the page will not let them do. */}
      <p className="text-sm font-medium text-ink">
        {t(unchanged ? "importSameTitle" : "importDraftTitle")}
      </p>
      <p className="mt-1 text-ink-muted">{t(unchanged ? "importSameBody" : "importDraftBody")}</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-ink-muted">{t("importOriginals")}</span>
        {sources.map((source, i) => (
          <a
            key={source.url}
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-ink underline decoration-ink-muted/50 underline-offset-2 hover:decoration-ink"
          >
            {pasted ? t("importPastedName") : source.name || t("importPage", { n: i + 1 })}{" "}
            <ExternalLink size={11} />
          </a>
        ))}
      </div>

      {/* Three states, three different claims — see the component comment. */}
      {!result.checked ? (
        <p className="mt-2.5 flex items-start gap-1.5 text-ink">
          <CircleHelp size={14} className="mt-0.5 shrink-0 text-ink-muted" />
          <span>{t("importUnchecked")}</span>
        </p>
      ) : missing.length ? (
        <p className="mt-2.5 flex items-start gap-1.5 text-ink">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-critical" />
          <span>
            {t(pasted ? "importTextNumbersMissing" : "importNumbersMissing")}{" "}
            <span className="font-medium tabular-nums">{missing.join(", ")}</span>
          </span>
        </p>
      ) : (
        <p className="mt-2.5 flex items-start gap-1.5 text-ink">
          <CircleCheck size={14} className="mt-0.5 shrink-0 text-good" />
          <span>{t(pasted ? "importTextNumbersFound" : "importNumbersFound")}</span>
        </p>
      )}

      {result.markup.length > 0 && (
        <div className="mt-2.5 flex items-start gap-1.5 text-ink">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-critical" />
          <div>
            <p>{t("importMarkup")}</p>
            <ul className="mt-1 flex flex-col gap-0.5 font-mono text-[11px] text-ink-muted">
              {result.markup.map((span, i) => (
                <li key={i}>{span}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {result.unreadable.length > 0 && (
        <div className="mt-2.5">
          <p className="text-ink">{t("importUnreadableLead")}</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-ink-muted">
            {/* The model's own sentences, in the CV's language — not UI copy. */}
            {result.unreadable.map((note, i) => (
              <li key={i} className="flex gap-1.5">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-muted" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3">
        <Button size="sm" variant="outline" onClick={onDiscard}>
          {t(unchanged ? "importDismiss" : "importDiscard")}
        </Button>
      </div>
    </div>
  );
}
