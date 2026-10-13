import { useRef, useState } from "react";
import {
  CircleCheck,
  CircleHelp,
  ExternalLink,
  FileUp,
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
  UploadError,
  formatBytes,
  prepareImportFile,
  readAsDataUri,
} from "@/lib/upload";
import type { CvImportResult } from "@/types";

/** A draft that is sitting in the editor, with the files it was read from. */
export interface ImportedDraft {
  result: CvImportResult;
  /** Object URLs of the uploaded files, so the original opens beside the draft.
   *  Created here, revoked by CvStudio, which owns the draft's lifetime. */
  sources: { name: string; url: string }[];
}

/** Free the object URLs of a draft nobody is showing any more. */
export function releaseDraft(draft: ImportedDraft): void {
  draft.sources.forEach((source) => URL.revokeObjectURL(source.url));
}

/**
 * Read a CV off page images or a PDF into the editor (Master scope only).
 *
 * This is the second place a model may put words on the Master CV, and the only
 * one with no text to hold them against: a photograph cannot be diffed. So the
 * card never saves — it fills the editor and leaves the Save button where it
 * always was — and what it says afterwards is deliberately not congratulatory.
 * The three check states are worded as three different claims because they are:
 * "every number was found", "these were not", and "nothing could be checked".
 * Collapsing the last into silence would read as the first.
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
  const [files, setFiles] = useState<File[]>([]);
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

  const read = async () => {
    if (running.current || !files.length || blocked) return;
    running.current = true;
    setBusy(true);
    setError(null);
    onStart();
    try {
      const payload = await Promise.all(
        files.map(async (file) => ({ name: file.name, data: await readAsDataUri(file) })),
      );
      const result = await api.importCv(payload);
      onDraft({
        result,
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

        <p className="mt-3 text-xs leading-relaxed text-ink-muted">
          {t("importLead")} <span className="text-ink">{t("importLeadEmphasis")}</span>{" "}
          {t("importLeadRest")}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button onClick={read} disabled={!files.length || busy || blocked}>
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
  const { result, sources } = draft;
  const missing = result.unbacked_numbers;

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
            {source.name || t("importPage", { n: i + 1 })} <ExternalLink size={11} />
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
            {t("importNumbersMissing")}{" "}
            <span className="font-medium tabular-nums">{missing.join(", ")}</span>
          </span>
        </p>
      ) : (
        <p className="mt-2.5 flex items-start gap-1.5 text-ink">
          <CircleCheck size={14} className="mt-0.5 shrink-0 text-good" />
          <span>{t("importNumbersFound")}</span>
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
