import { useT } from "@/i18n";
import { matchPercent } from "@/lib/format";
import { useLabels } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { JobQuality } from "@/types";

// Sequential magnitude (0..100%) as a single-hue meter — blue, light→dark by
// value. Tabular figure so rows align.
//
// The tooltip carries the reasons: a bare "25%" is a verdict with no argument
// attached, and the score comes from a list you configured, so naming that list
// is what makes it reviewable. The skill names inside it come from the crawler
// and stay as stored — the prose around them is what gets translated.
export function MatchMeter({
  score,
  quality,
  className,
}: {
  score: number;
  quality?: JobQuality | null;
  className?: string;
}) {
  const t = useT("jobs");
  const pct = matchPercent(score);
  const hue = pct >= 66 ? "#256abf" : pct >= 33 ? "#3987e5" : "#86b6ef";

  const matched = quality?.matched ?? [];
  const missing = quality?.missing ?? [];
  const reasons: string[] = [];
  if (matched.length) reasons.push(t("mentions", { list: matched.join(", ") }));
  if (missing.length) reasons.push(t("doesntMention", { list: missing.join(", ") }));

  const label = t("match", { pct });
  return (
    <div
      className={cn("flex items-center gap-2", className)}
      title={reasons.length ? `${label}\n${reasons.join("\n")}` : label}
    >
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ink/10">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: hue }} />
      </div>
      <span className="w-8 font-mono text-[11px] tabular-nums text-ink-muted">{pct}%</span>
    </div>
  );
}

/**
 * Advisory badges. These never hide a job — they annotate it and leave the
 * decision with you, the same way the crawler surfaces a gap rather than
 * quietly closing it.
 *
 * The badge text is a deliberately terser wording than `useLabels().qualityLabel`
 * ("no JD" vs "No description") because it has to fit a chip in a table row —
 * but a flag nobody has written copy for yet falls back to the shared label, so
 * a new one out of the crawler still reads in the right language on day one.
 */
export function QualityFlags({
  quality,
  className,
}: {
  quality?: JobQuality | null;
  className?: string;
}) {
  const t = useT("jobs");
  const labels = useLabels();
  const flags = quality?.flags ?? [];
  const known: Record<string, { short: string; why: string }> = {
    no_jd: { short: t("flagNoJd"), why: t("flagNoJdWhy") },
    thin_jd: { short: t("flagThinJd"), why: t("flagThinJdWhy") },
    stale: { short: t("flagStale"), why: t("flagStaleWhy") },
    undated: { short: t("flagUndated"), why: t("flagUndatedWhy") },
  };
  if (!flags.length) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {flags.map((f) => {
        const fallback = labels.qualityLabel(f);
        const meta = known[f] ?? { short: fallback, why: fallback };
        return (
          <span
            key={f}
            title={meta.why}
            className="rounded border border-caution/40 bg-caution/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-caution"
          >
            {meta.short}
          </span>
        );
      })}
    </div>
  );
}
