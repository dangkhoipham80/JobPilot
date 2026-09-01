import { useMemo } from "react";
import type { JobStatus } from "@/types";
import { useI18n } from "@/i18n";
import { dict } from "@/i18n/dict";

/**
 * What each job status means, in one place.
 *
 * The status vocabulary is the spine of the whole app — the funnel, the filter
 * dropdown, the pills in the table and the Guide page all name the same nine
 * states. Describing them in nine different components is how those wordings
 * drift apart, so every surface reads from here.
 *
 * `actor` answers the only question that matters when you are staring at a
 * board: is this waiting on me, or on the agent? It is data, not copy, so it
 * stays here while the prose moved to `i18n/dict/statuses.ts`.
 */
export interface StatusInfo {
  /** Translated one-word name for the pill. */
  label: string;
  /** One line: what the state means. */
  meaning: string;
  /** What happens next, phrased as the action you'd take. */
  next: string;
}

/** Who moves each state forward. Language-independent. */
export const STATUS_ACTOR: Record<JobStatus, "you" | "agent" | "done"> = {
  DISCOVERED: "you",
  SHORTLISTED: "you",
  TAILORING: "agent",
  REVIEW: "you",
  APPROVED: "you",
  SUBMITTING: "agent",
  SUBMITTED: "done",
  FAILED: "you",
  SKIPPED: "done",
};

/** The happy path, in order. FAILED and SKIPPED are exits, not steps. */
export const FUNNEL_STEPS: JobStatus[] = [
  "DISCOVERED",
  "SHORTLISTED",
  "TAILORING",
  "REVIEW",
  "APPROVED",
  "SUBMITTED",
];

/**
 * The nine descriptions in the current language, plus a pill tooltip.
 *
 * The tooltip leads with the raw state name in both languages. `SUBMITTED` is
 * the word the API returns, the CLI prints and `PHASES.md` records; translating
 * the pill without keeping the original one hover away would make the UI and
 * the logs impossible to line up.
 */
export function useStatuses() {
  const { lang } = useI18n();
  return useMemo(() => {
    const table = dict.statuses[lang] as Record<string, string>;
    const info = (status: JobStatus): StatusInfo => ({
      label: table[status] ?? status.toLowerCase(),
      meaning: table[`${status}_meaning`] ?? "",
      next: table[`${status}_next`] ?? "",
    });
    return {
      info,
      tooltip: (status: JobStatus) => {
        const { meaning, next } = info(status);
        return `${status} · ${meaning} → ${next}`;
      },
    };
  }, [lang]);
}
