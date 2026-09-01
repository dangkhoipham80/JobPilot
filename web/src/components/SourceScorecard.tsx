import { useState } from "react";
import { AlertTriangle, Clock, Repeat } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useT } from "@/i18n";
import { titleCase } from "@/lib/format";
import { useLabels } from "@/lib/labels";
import type { OutcomeAnalytics, OutcomeBucket, OutcomeSplit } from "@/types";

/**
 * "Which source is worth crawling again?" — PLAN.md §9.1 slot 20.
 *
 * **A table, not a bar chart, and that is the design.** Roughly half these rows
 * legitimately have no rate: below the backend's `min_sample` a bucket carries
 * counts only. A bar chart has no way to draw that — it would either plot a
 * suppressed rate as zero (reads as "this source never answers") or quietly
 * omit the row (reads as "this source doesn't exist). A table can print
 * `n=3 · too few to rate` in the cell where the number would go, which is the
 * honest mark for "we looked and cannot say yet".
 *
 * Rates are never recomputed here. The backend nulls them below the threshold,
 * and dividing `answered / sent` in the view would put back exactly the
 * percentage the suppression exists to prevent.
 */
// The second element is a dictionary key, not a visible string: the tab and the
// first column head must resolve at render time so they follow the language
// switch (see `i18n/CLAUDE.md`).
const DIMENSIONS = [
  ["by_source", "dimSource"],
  ["by_channel", "dimChannel"],
  ["by_level", "dimLevel"],
] as const;

type Dimension = (typeof DIMENSIONS)[number][0];

export function SourceScorecard({ data }: { data: OutcomeAnalytics }) {
  const t = useT("dashboard");
  const [dimension, setDimension] = useState<Dimension>("by_source");
  const split = data[dimension];
  // The header follows the tab. It used to be the literal "Source", so
  // switching to Channel showed `email`/`portal` rows under a column headed
  // "Source" — right numbers, wrong label, which is worse than either.
  const label = t(DIMENSIONS.find(([key]) => key === dimension)![1]);
  // How to spell a row key depends on which tab you are on: board names have
  // their own capitalisation, the seniority ladder has a canonical form, and a
  // channel is a plain lowercase word the dispatcher wrote.
  const labels = useLabels();
  const keyLabel =
    dimension === "by_source"
      ? labels.sourceLabel
      : dimension === "by_level"
        ? labels.levelLabel
        : titleCase;

  // A repeat posting is a fact about the crawled corpus, not about applying —
  // "this ad has been reposted five times in four months" is worth knowing
  // *before* an evening goes into it. Tying it to the outcome tables would hide
  // it from exactly the user who can still act on it: crawled a lot, applied to
  // nothing yet.
  if (data.total_sent === 0) return <RepeatsCard data={data} />;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-wrap gap-2">
          <div>
            <CardTitle>{t("scorecardTitle")}</CardTitle>
            <p className="mt-0.5 text-xs text-ink-muted">
              {data.total_sent === 1
                ? t("scorecardMetaOne", { min: data.min_sample })
                : t("scorecardMeta", { n: data.total_sent, min: data.min_sample })}
            </p>
          </div>
          <div className="flex gap-1 rounded-lg bg-surface-2 p-0.5">
            {DIMENSIONS.map(([key, tab]) => (
              <button
                key={key}
                onClick={() => setDimension(key)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  dimension === key
                    ? "bg-surface text-ink shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {t(tab)}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardBody>
          <SplitTable split={split} minSample={data.min_sample} label={label} keyLabel={keyLabel} />
        </CardBody>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <TimingCard data={data} />
        <RepeatsCard data={data} />
      </div>
    </div>
  );
}

function SplitTable({
  split,
  minSample,
  label,
  keyLabel,
}: {
  split: OutcomeSplit;
  minSample: number;
  label: string;
  keyLabel: (key: string) => string;
}) {
  const t = useT("dashboard");
  const common = useT("common");
  if (split.rows.length === 0) {
    // `split.note` is a sentence the analytics backend composed; it is data
    // about this corpus, not UI copy, so it is printed as it arrived.
    return (
      <p className="py-6 text-center text-sm text-ink-muted">
        {split.note || common("noData")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-muted">
              <th className="pb-2 font-medium">{label}</th>
              <th className="pb-2 text-right font-medium">{t("colSent")}</th>
              <th className="pb-2 text-right font-medium">{t("colAnswered")}</th>
              <th className="pb-2 text-right font-medium">{t("colInterviews")}</th>
              <th className="pb-2 text-right font-medium">{t("colOffers")}</th>
              <th className="pb-2 pl-4 font-medium">{t("colReplyRate")}</th>
            </tr>
          </thead>
          <tbody>
            {split.rows.map((row) => (
              <Row key={row.key} row={row} minSample={minSample} keyLabel={keyLabel} />
            ))}
          </tbody>
        </table>
      </div>
      {split.note && (
        <p className="flex items-start gap-1.5 text-xs text-ink-muted">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          {split.note}
        </p>
      )}
    </div>
  );
}

function Row({
  row,
  minSample,
  keyLabel,
}: {
  row: OutcomeBucket;
  minSample: number;
  keyLabel: (key: string) => string;
}) {
  const t = useT("dashboard");
  return (
    <tr className="border-b border-line/50 last:border-0">
      {/* Untranslated by design — a board name, `email`/`portal` as the
          dispatcher records it, and a seniority ladder the Vietnamese market
          advertises in English. But *spelling* is not translation: title-casing
          a raw key writes "Itviec" and "Wework remotely", names no board uses,
          so the row goes through the label helper for its dimension. */}
      <td className="py-2.5 font-medium">{keyLabel(row.key)}</td>
      <td className="py-2.5 text-right tabular-nums">{row.sent}</td>
      <td className="py-2.5 text-right tabular-nums">{row.answered}</td>
      <td className="py-2.5 text-right tabular-nums">{row.interviewed}</td>
      <td className="py-2.5 text-right tabular-nums">
        {row.offered > 0 ? <span className="font-semibold text-accent">{row.offered}</span> : "—"}
      </td>
      <td className="py-2.5 pl-4">
        {row.reply_rate === null ? (
          // The honest cell. Not "0%", not blank — the sample is stated so the
          // reader can see how far it is from being readable.
          <span className="text-xs text-ink-muted">
            {t("needsSample", { n: row.sent, min: minSample })}
          </span>
        ) : (
          <RateBar value={row.reply_rate} />
        )}
      </td>
    </tr>
  );
}

/** One measure, one hue — a rate is the same quantity on every row, so the
 *  colour never varies by rank. Width carries the value; the number is printed
 *  because a 40px bar cannot be read to the percent. */
function RateBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${Math.max(Math.round(value * 100), 2)}%` }}
        />
      </div>
      <span className="tabular-nums text-xs">{Math.round(value * 100)}%</span>
    </div>
  );
}

function TimingCard({ data }: { data: OutcomeAnalytics }) {
  const t = useT("dashboard");
  const timing = data.timing;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock size={15} /> {t("timingTitle")}
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-2">
        {timing.median_days === null ? (
          <p className="text-sm text-ink-muted">{t("timingEmpty")}</p>
        ) : (
          <>
            <div className="flex items-baseline gap-2">
              <span className="font-display text-3xl font-semibold tabular-nums">
                {timing.median_days}
              </span>
              <span className="text-sm text-ink-muted">{t("timingUnit")}</span>
            </div>
            {/* `?? "?"`: the three come from the same list so the backend never
                splits them, but the type says nullable and "fastest nulld" is a
                worse way to learn that than a question mark. */}
            <p className="text-xs text-ink-muted">
              {t("timingRange", {
                fast: timing.fastest_days ?? "?",
                slow: timing.slowest_days ?? "?",
                n: timing.answered,
              })}
            </p>
          </>
        )}
        {/* Stated, not folded in: an application nobody has answered is not a
            slow reply, and counting it would make this number drift worse every
            day nothing happens. */}
        <p className="text-xs text-ink-muted">
          {t("timingWaiting", { n: timing.still_waiting })}
          {timing.undated > 0 && t("timingUndated", { n: timing.undated })}
          {/* Dropped, not clamped to 0: an answer dated before the send means one
              of the two timestamps is wrong, and a 0-day reply would read as the
              fastest one in the corpus. */}
          {timing.inconsistent > 0 && t("timingInconsistent", { n: timing.inconsistent })}
        </p>
        {timing.thin && timing.median_days !== null && (
          <p className="flex items-start gap-1.5 text-xs text-ink-muted">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            {timing.answered === 1
              ? t("timingThinOne")
              : t("timingThin", { n: timing.answered })}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function RepeatsCard({ data }: { data: OutcomeAnalytics }) {
  const t = useT("dashboard");
  const { rows, total_groups, shown, min_postings } = data.repeats;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Repeat size={15} /> {t("repeatsTitle")}
        </CardTitle>
        {total_groups > shown && (
          <span className="text-xs text-ink-muted">
            {t("repeatsShown", { shown, total: total_groups })}
          </span>
        )}
      </CardHeader>
      <CardBody className="space-y-3">
        {rows.length === 0 ? (
          <p className="text-sm text-ink-muted">
            {t("repeatsEmpty", { min: min_postings })}
          </p>
        ) : (
          <>
            <ul className="space-y-2">
              {rows.map((r) => (
                <li key={`${r.company}/${r.title}`} className="text-sm">
                  <span className="font-medium">{r.title}</span>
                  <span className="text-ink-muted"> · {r.company}</span>
                  <div className="text-xs text-ink-muted">
                    {t("repeatsPostings", { n: r.postings })}
                    {/* null, not 0 — an unknown spread is not a same-day spread. */}
                    {r.span_days !== null
                      ? t("repeatsSpan", { n: r.span_days })
                      : t("repeatsNoDates")}
                    {r.undated_postings > 0 && t("repeatsUndated", { n: r.undated_postings })}
                  </div>
                </li>
              ))}
            </ul>
            {/* The wording is deliberate. Two openings with the same title at one
                company are ordinary hiring; this evidence cannot tell that apart
                from an ad nobody ever fills, so it reports and does not judge. */}
            <p className="text-xs text-ink-muted">{t("repeatsFootnote")}</p>
          </>
        )}
      </CardBody>
    </Card>
  );
}
