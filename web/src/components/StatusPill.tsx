import type { JobStatus } from "@/types";
import { useStatuses } from "@/lib/statuses";
import { cn } from "@/lib/utils";

// Status is state, not a data series — a reserved, labeled vocabulary. Color
// never carries meaning alone; the text label always shows.
//
// The mid-stage hues are literal hex rather than theme tokens, so they need an
// explicit dark variant: a colour picked for contrast against white paper is
// unreadable on a near-black surface.
//
// DISCOVERED and SKIPPED used to be two grey outlines, told apart only by a
// strikethrough at 70% opacity — and that is the pair a Jobs list actually
// shows, since nearly every row is one or the other. DISCOVERED now has a hue
// of its own (a cyan between REVIEW's blue and APPROVED's green; 5.2:1 on the
// light surface, 8.4:1 on the dark one). SKIPPED stays grey because it is the
// one state with nothing left to do, but hollow and dashed, and at full
// `ink-muted`: at 70% the label measured 2.9:1 light and 3.7:1 dark.
const STYLES: Record<JobStatus, string> = {
  DISCOVERED: "border-[#1493ad]/40 text-[#0c6f85] bg-[#1493ad]/10 dark:text-[#6fcbe0]",
  SHORTLISTED: "border-accent/40 text-accent bg-accent/10",
  TAILORING: "border-[#4a3aa7]/40 text-[#5b4bd0] bg-[#4a3aa7]/10 dark:text-[#a99cf0]",
  REVIEW: "border-[#2a78d6]/40 text-[#2a78d6] bg-[#2a78d6]/10 dark:text-[#79b0f0]",
  APPROVED: "border-[#1baf7a]/40 text-[#128a5f] bg-[#1baf7a]/10 dark:text-[#45d3a0]",
  SUBMITTING: "border-[#eda100]/50 text-[#a97600] bg-[#eda100]/10 dark:text-[#e8bb4e]",
  SUBMITTED: "border-good/40 text-good bg-good/10",
  FAILED: "border-critical/40 text-critical bg-critical/10",
  SKIPPED: "border-dashed border-ink/25 text-ink-muted line-through",
};

export function StatusPill({ status, className }: { status: JobStatus; className?: string }) {
  const statuses = useStatuses();
  return (
    <span
      // Nine one-word states carry a lot of meaning; hovering explains what the
      // word means and whose move it is, without a trip to the Guide. It also
      // carries the raw DB state, which the translated pill no longer shows.
      title={statuses.tooltip(status)}
      className={cn(
        // `whitespace-nowrap` is load-bearing, not cosmetic. Every English state
        // is one word, so the pill could never wrap; Vietnamese "mới tìm thấy"
        // is three, and in a table cell it broke onto three lines and pushed
        // every row taller. A pill is a label — it should widen its column, not
        // reflow inside itself.
        "inline-flex cursor-help items-center whitespace-nowrap rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        STYLES[status],
        className,
      )}
    >
      {statuses.info(status).label}
    </span>
  );
}
