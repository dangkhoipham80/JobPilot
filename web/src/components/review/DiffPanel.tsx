import { ArrowRight, Eye, EyeOff, MoveVertical, PenLine, Plus, Scissors } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { CvDiff, DiffStatus, TailorChange } from "@/types";

/**
 * The tailor mostly *moves* content, so a line diff would mark every bullet as
 * changed. This renders the structural diff from jobpilot/tailor/diff.py: what
 * moved, what was trimmed, what was rewritten — the questions a reviewer has.
 *
 * Shared with CV Studio's version compare, which passes no `changes` (there is
 * no tailor plan behind a hand edit) and its own `title`.
 *
 * Only the *frame* is translated. Section titles, the per-section notes (which
 * `tailor/diff.py` picks from `TAILOR_LABELS` / `VERSION_LABELS`) and the
 * before/after prose are CV content and agent output: they render exactly as
 * the API sent them, in whatever language the CV is written in.
 */

const STATUS: Record<DiffStatus, { icon: typeof PenLine; className: string }> = {
  rewritten: { icon: PenLine, className: "text-accent border-accent/40 bg-accent/10" },
  trimmed: { icon: Scissors, className: "text-critical border-critical/40 bg-critical/8" },
  // Content the CV did not have before. Given the accent rather than a quiet
  // colour deliberately: this is the one status under which a fabricated claim
  // would appear, so it is the one a reviewer must not skim past.
  expanded: { icon: Plus, className: "text-accent border-accent/40 bg-accent/10" },
  hidden: { icon: EyeOff, className: "text-ink-muted border-border bg-surface-2" },
  reordered: { icon: MoveVertical, className: "text-good border-good/40 bg-good/8" },
  unchanged: { icon: Eye, className: "text-ink-muted border-border" },
};

export function DiffPanel({
  diff,
  changes = [],
  title,
  action,
}: {
  diff: CvDiff;
  changes?: TailorChange[];
  title?: string;
  action?: React.ReactNode;
}) {
  const t = useT("review");
  const touched = diff.sections.filter((s) => s.status !== "unchanged");
  const untouched = diff.sections.filter((s) => s.status === "unchanged");

  return (
    <Card>
      <CardHeader className="gap-3">
        {/* CV Studio passes a version pair ("v3 → v7") — data, not copy. */}
        <CardTitle>{title ?? t("whatChanged")}</CardTitle>
        <span className="ml-auto font-mono text-[11px] text-ink-muted">
          {t("sectionsChanged", { changed: touched.length, total: diff.sections.length })}
        </span>
        {action}
      </CardHeader>
      <CardBody className="flex flex-col gap-4 pt-3">
        {changes.length > 0 && (
          <ul className="flex flex-col gap-2">
            {changes.map((c, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                <span>
                  <span className="font-medium">{c.what}</span>
                  <span className="text-ink-muted"> — {c.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        )}

        {diff.order_changed && (
          <div className="rounded-lg border bg-surface-2/60 px-3 py-2 text-xs">
            <span className="font-semibold uppercase tracking-[0.1em] text-ink-muted">
              {t("sectionOrder")}
            </span>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 font-mono">
              {diff.order_after.map((key, i) => (
                <span key={key} className="flex items-center gap-1.5">
                  {i > 0 && <ArrowRight size={11} className="text-ink-muted/60" />}
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5",
                      diff.order_before[i] === key ? "text-ink-muted" : "bg-accent/12 text-ink",
                    )}
                  >
                    {key}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-2">
          {touched.map((section) => {
            const meta = STATUS[section.status];
            const Icon = meta.icon;
            return (
              <div key={section.key} className="rounded-lg border p-3">
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
                      meta.className,
                    )}
                  >
                    <Icon size={11} /> {t(`status_${section.status}`)}
                  </span>
                  <span className="text-sm font-medium">{section.title}</span>
                </div>

                {section.before !== null && section.after !== null ? (
                  <div className="mt-2 grid gap-2 text-[13px] leading-relaxed sm:grid-cols-2">
                    <p className="rounded-md border bg-surface-2/60 p-2 text-ink-muted line-through decoration-critical/50">
                      {section.before}
                    </p>
                    <p className="rounded-md border border-accent/30 bg-accent/6 p-2">
                      {section.after}
                    </p>
                  </div>
                ) : (
                  section.notes.length > 0 && (
                    <ul className="mt-1.5 flex flex-col gap-1 pl-1 text-xs text-ink-muted">
                      {section.notes.map((note, i) => (
                        <li key={i}>· {note}</li>
                      ))}
                    </ul>
                  )
                )}
              </div>
            );
          })}
        </div>

        {untouched.length > 0 && (
          <p className="text-xs text-ink-muted">
            {t("unchangedList", { list: untouched.map((s) => s.title).join(", ") })}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
