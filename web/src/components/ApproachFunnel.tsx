import { FUNNEL_ORDER, type JobStatus, type Stats } from "@/types";
import { ORDINAL_BLUE_DARK, ORDINAL_BLUE_LIGHT, isDark } from "@/components/charts/palette";

// Signature element: the pipeline as an approach — jobs descending stage by
// stage toward the runway (SUBMITTED). Width tapers with volume; the ordinal
// blue ramp deepens with depth. SKIPPED/FAILED are shown apart as diverted.
const LABELS: Record<JobStatus, string> = {
  DISCOVERED: "Discovered",
  SHORTLISTED: "Shortlisted",
  TAILORING: "Tailoring",
  REVIEW: "In review",
  APPROVED: "Approved",
  SUBMITTING: "Submitting",
  SUBMITTED: "Submitted",
  FAILED: "Failed",
  SKIPPED: "Skipped",
};

export function ApproachFunnel({ stats }: { stats: Stats }) {
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
            <div className="w-20 shrink-0 text-right text-xs text-ink-muted">{LABELS[stage]}</div>
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
        <span className="w-20 shrink-0 text-right">Diverted</span>
        <span className="rounded-md border border-ink/10 px-2 py-0.5 font-mono tabular-nums">
          {stats.by_status.SKIPPED} skipped
        </span>
        <span className="rounded-md border border-critical/30 px-2 py-0.5 font-mono tabular-nums text-critical">
          {stats.by_status.FAILED} failed
        </span>
      </div>
    </div>
  );
}
