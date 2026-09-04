import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, PenSquare } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { Markdown } from "@/components/Markdown";
import { JdSectionsView } from "@/components/JdSectionsView";
import { useT } from "@/i18n";
import { titleCase } from "@/lib/format";
import type { JobDetail } from "@/types";

/**
 * The job description, editable in place.
 *
 * LinkedIn Job Alert emails announce a job but not its text, and JobPilot won't
 * fetch the posting (robots.txt forbids it). So a job can arrive with nothing to
 * tailor against — this is where you paste it in, and it's called out loudly
 * rather than letting the tailor run on an empty JD and produce noise.
 */
export function JobDescription({ job, onSaved }: { job: JobDetail; onSaved: () => void }) {
  const t = useT("jobs");
  const common = useT("common");
  const empty = !job.description_md.trim();
  const [editing, setEditing] = useState(empty);
  const [draft, setDraft] = useState(job.description_md);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Structured by default when there is one: it is the faster read, and the raw
  // text is one click away for anything that looks off.
  const [view, setView] = useState<"structured" | "raw">("structured");

  useEffect(() => {
    setDraft(job.description_md);
    setEditing(!job.description_md.trim());
  }, [job.id, job.description_md]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.patchJob(job.id, { description_md: draft });
      onSaved();
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="items-center">
        <CardTitle>{t("descriptionTitle")}</CardTitle>
        <div className="flex items-center gap-3">
          {job.apply_channel && (
            <span className="text-xs text-ink-muted">
              {/* The channel name is a backend value (email / portal /
                  external) — shown as stored, in both languages. */}
              {t("appliesVia", { channel: titleCase(job.apply_channel) })}
            </span>
          )}
          {!editing && (
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
              <PenSquare size={13} /> {common("edit")}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardBody>
        {/* Shown while editing too: the editor auto-opens when there is no
            description, which is exactly when the warning matters most. */}
        {empty && (
          <p className="mb-3 flex items-start gap-2 rounded-lg border border-accent/40 bg-accent/8 px-3 py-2 text-xs leading-relaxed">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-accent" />
            <span>
              {job.needs_jd ? t("noJdLinkedIn") : t("noJdPlain")} {t("noJdAdvice")}
            </span>
          </p>
        )}

        {!editing && job.sections && (
          <div className="mb-4 inline-flex rounded-lg border p-0.5 text-xs">
            {/* A toggle, not a second card. The buckets are a reading *of* this
                text, so the original has to stay one click away — that is what
                makes it checkable, and checkable is the only reason it is safe
                to show a model's arrangement of a posting. */}
            {(["structured", "raw"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setView(mode)}
                className={
                  view === mode
                    ? "rounded-md bg-surface-2 px-2.5 py-1 font-medium text-ink"
                    : "px-2.5 py-1 text-ink-muted hover:text-ink"
                }
              >
                {t(mode === "structured" ? "viewStructured" : "viewRaw")}
              </button>
            ))}
          </div>
        )}

        {editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              rows={14}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t("descriptionPlaceholder")}
              className="w-full resize-y rounded-lg border bg-surface px-3 py-2 font-sans text-sm leading-relaxed text-ink placeholder:text-ink-muted/70 focus:border-accent focus:outline-none"
            />
            <div className="flex items-center justify-end gap-2">
              {error ? (
                <span className="mr-auto text-xs text-critical">{error}</span>
              ) : (
                <span className="mr-auto text-xs text-ink-muted">
                  {/* The markers are syntax, so only the words around them
                      change language. */}
                  Markdown: <code className="font-mono">##</code> {t("mdHeading")},{" "}
                  <code className="font-mono">-</code> {t("mdBullet")},{" "}
                  <code className="font-mono">**text**</code> {t("mdBold")}
                </span>
              )}
              {!empty && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setDraft(job.description_md);
                    setEditing(false);
                  }}
                >
                  {common("cancel")}
                </Button>
              )}
              <Button size="sm" onClick={save} disabled={busy || !draft.trim()}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}{" "}
                {busy ? common("saving") : common("save")}
              </Button>
            </div>
          </div>
        ) : job.sections && view === "structured" ? (
          <JdSectionsView sections={job.sections} />
        ) : (
          <Markdown source={job.description_md} />
        )}
      </CardBody>
    </Card>
  );
}
