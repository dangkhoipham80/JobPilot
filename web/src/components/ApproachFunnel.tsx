import { FUNNEL_ORDER, type Stats } from "@/types";
import { ORDINAL_BLUE_DARK, ORDINAL_BLUE_LIGHT, isDark } from "@/components/charts/palette";
import { useT } from "@/i18n";
import { useStatuses } from "@/lib/statuses";

// Signature element: the pipeline as an approach — jobs descending stage by
// stage toward the runway (SUBMITTED). Width tapers with volume; the ordinal
// blue ramp deepens with depth. SKIPPED/FAILED are shown apart as diverted.
//
// Stage names come from `useStatuses()`, the same table the pills and the Guide
// read: this file used to keep its own `Record<JobStatus, string>`, and a second
// copy of the status vocabulary is exactly how "In review" here drifts from
// "review" three screens away. `first-letter:uppercase` restores the sentence
// case the local copy had — `capitalize` would upper-case every word, which is
// right for English and wrong for "mới tìm thấy".
export function ApproachFunnel({ stats }: { stats: Stats }) {
  const t = useT("dashboard");
  const statuses = useStatuses();
  const ramp = isDark() ? ORDINAL_BLUE_DARK : ORDINAL_BLUE_LIGHT;
  // The widest stage, not DISCOVERED. `by_status` counts jobs by their *current*
  // status, and a job that gets submitted leaves DISCOVERED — so SUBMITTED
  // overtaking it is the normal end state of using the tool, not an anomaly.
  // Normalising against DISCOVERED rendered those bars at well over 100% and the
  // bar escaped its card across the whole page: the funnel broke precisely when
  // the search was going well.
  const top = Math.max(...FUNNEL_ORDER.map((s) => stats.by_status[s] ?? 0), 1);

  return (
    <div className="flex flex-col gap-1.5">
      {FUNNEL_ORDER.map((stage, i) => {
        const count = stats.by_status[stage] ?? 0;
        const widthPct = Math.max((count / top) * 100, count > 0 ? 8 : 3);
        const color = ramp[Math.min(i, ramp.length - 1)];
        return (
          <div key={stage} className="group flex items-center gap-3">
            <div className="w-20 shrink-0 text-right text-xs text-ink-muted first-letter:uppercase">
              {statuses.info(stage).label}
            </div>
            <div className="relative flex-1">
              <div
                className="flex h-7 items-center rounded-md px-2 transition-[width] duration-500 group-hover:brightness-105"
                style={{ width: `${widthPct}%`, background: color, minWidth: 28 }}
              >
                <span className="font-mono text-xs font-semibold tabular-nums text-white">
                  {count}
                </span>
              </div>
            </div>
          </div>
        );
      })}

      <div className="mt-2 flex items-center gap-3 border-t pt-2.5 text-xs text-ink-muted">
        <span className="w-20 shrink-0 text-right">{t("diverted")}</span>
        <span className="rounded-md border border-ink/10 px-2 py-0.5 font-mono tabular-nums">
          {t("skippedCount", { n: stats.by_status.SKIPPED })}
        </span>
        <span className="rounded-md border border-critical/30 px-2 py-0.5 font-mono tabular-nums text-critical">
          {t("failedCount", { n: stats.by_status.FAILED })}
        </span>
      </div>
    </div>
  );
}
