import { useRef, useState } from "react";
import { AlertTriangle, Ban, Check, CircleDashed, Minus, Target } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useT } from "@/i18n";
import { useFormat, matchPercent } from "@/lib/format";
import { STATUS, MUTED } from "@/components/charts/palette";
import { Badge, Button, Card, CardBody } from "@/components/ui";
import type { FitReport, JobDetail, Requirement } from "@/types";

/**
 * How well the Master CV answers this posting — and what is off about the
 * posting itself.
 *
 * The card is careful about one thing above all: this is a model's opinion,
 * and it is an opinion about the reader's career. So the verdict word is always
 * paired with a sentence, the score always carries the formula behind it in a
 * tooltip, and `advisory` sits at the bottom saying in as many words that
 * nothing here reaches the CV. A one-word judgement with no argument attached
 * is exactly the shape people over-trust.
 *
 * Colour follows the reserved state scale, never the categorical palette: HAVE
 * / PARTIAL / MISSING is an ordinal state, and each swatch is shown with an icon
 * and a word beside it because `warning` and `serious` sit below 3:1 on the
 * light surface by design.
 */

// `as const` rather than an annotation, so the label keys stay literal types and
// `t()` still type-checks them against the namespace. Widening them to `string`
// is how a typo'd key gets to render as the key itself at runtime.
const VERDICT = {
  strong: { color: STATUS.good, label: "verdictStrong", hint: "verdictStrongHint" },
  fair: { color: STATUS.warning, label: "verdictFair", hint: "verdictFairHint" },
  weak: { color: STATUS.serious, label: "verdictWeak", hint: "verdictWeakHint" },
} as const satisfies Record<FitReport["verdict"], { color: string; label: string; hint: string }>;

const REQ_STATUS = {
  HAVE: { color: STATUS.good, icon: Check, label: "statusHave" },
  PARTIAL: { color: STATUS.warning, icon: CircleDashed, label: "statusPartial" },
  MISSING: { color: MUTED, icon: Minus, label: "statusMissing" },
} as const;

//: How many requirements to show before folding the rest away. A posting with
//: thirty bullet points would otherwise push the JD off the screen entirely.
const PREVIEW = 6;

export function FitCard({ job, onAssessed }: { job: JobDetail; onAssessed: () => void }) {
  const t = useT("fit");
  const fmt = useFormat();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  // A ref, not state: two clicks in the same tick both read `busy === false`
  // because React has not re-rendered between them, and the second one spends a
  // second API call. Same reason OutcomeTracker guards with a ref.
  const running = useRef(false);

  const fit = job.fit;
  const hasJd = job.description_md.trim().length > 0;

  async function assess() {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setError(null);
    try {
      await api.assessFit(job.id);
      onAssessed();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("failed"));
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  const verdict = fit ? VERDICT[fit.verdict] : null;
  const shown = fit && !expanded ? fit.requirements.slice(0, PREVIEW) : (fit?.requirements ?? []);
  // Counted over the *scored* requirements only. `soft` carries weight 0 (a CV
  // cannot evidence "high growth drive"), so counting it here would put "2
  // covered · 4 missing" next to "100%" on the same card — two different rules
  // for one number, which is the contradiction the derived score exists to
  // prevent. The soft ones are still listed below, and tallied separately.
  const scored = fit?.requirements.filter((r) => r.kind !== "soft") ?? [];
  const counts = {
    HAVE: scored.filter((r) => r.status === "HAVE").length,
    PARTIAL: scored.filter((r) => r.status === "PARTIAL").length,
    MISSING: scored.filter((r) => r.status === "MISSING").length,
    soft: (fit?.requirements.length ?? 0) - scored.length,
  };

  return (
    <Card>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="inline-flex items-center gap-2 font-display text-sm font-semibold">
              <Target size={15} className="text-ink-muted" /> {t("title")}
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">
              {fit && fit.assessed_at
                ? t("assessedAt", { when: fmt.relativeTime(fit.assessed_at) })
                : t("intro")}
            </p>
          </div>
          <Button
            size="sm"
            variant={fit ? "outline" : "primary"}
            onClick={assess}
            disabled={busy || !hasJd}
          >
            {busy ? t("busy") : fit ? t("reassess") : t("assess")}
          </Button>
        </div>

        {!hasJd && <p className="text-xs text-ink-muted">{t("needsJd")}</p>}
        {error && <p className="text-xs text-critical">{error}</p>}

        {fit && verdict && (
          <>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-4">
              <span
                className="inline-flex items-center gap-2 text-sm font-semibold"
                style={{ color: verdict.color }}
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: verdict.color }}
                />
                {t(verdict.label)}
              </span>
              <span className="text-xs text-ink-muted">{t(verdict.hint)}</span>
              <span
                className="ml-auto font-mono text-xs tabular-nums text-ink-muted"
                title={t("scoreHint")}
              >
                {t("score", { pct: matchPercent(fit.match_score) })}
              </span>
            </div>

            <p className="text-sm leading-relaxed text-ink">{fit.summary}</p>

            {fit.dealbreakers.length > 0 && (
              <Section
                icon={<Ban size={14} style={{ color: STATUS.critical }} />}
                title={t("dealbreakers")}
                hint={t("dealbreakersHint")}
                items={fit.dealbreakers}
                color={STATUS.critical}
              />
            )}

            {fit.concerns.length > 0 && (
              <Section
                icon={<AlertTriangle size={14} style={{ color: STATUS.serious }} />}
                title={t("concerns")}
                hint={t("concernsHint")}
                items={fit.concerns}
                color={STATUS.serious}
              />
            )}

            <div className="border-t pt-4">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {t("requirements")}
                </h3>
                <span className="text-xs text-ink-muted">
                  {t("covered", { n: counts.HAVE })} · {t("partial", { n: counts.PARTIAL })} ·{" "}
                  {t("missing", { n: counts.MISSING })}
                  {counts.soft > 0 && <> · {t("softNotScored", { n: counts.soft })}</>}
                </span>
              </div>

              {fit.requirements.length === 0 ? (
                <p className="mt-2 text-xs text-ink-muted">{t("noRequirements")}</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {shown.map((req, i) => (
                    <RequirementRow key={`${req.text}-${i}`} req={req} />
                  ))}
                </ul>
              )}

              {fit.requirements.length > PREVIEW && (
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="mt-3 text-xs font-medium text-accent hover:underline"
                >
                  {expanded ? t("showLess") : t("showAll", { n: fit.requirements.length })}
                </button>
              )}
            </div>

            <p className="border-t pt-3 text-xs leading-relaxed text-ink-muted">{t("advisory")}</p>
          </>
        )}
      </CardBody>
    </Card>
  );
}

function RequirementRow({ req }: { req: Requirement }) {
  const t = useT("fit");
  const state = REQ_STATUS[req.status] ?? REQ_STATUS.MISSING;
  const Icon = state.icon;
  const kind =
    req.kind === "must_have" ? t("kindMust") : req.kind === "nice_to_have" ? t("kindNice") : t("kindSoft");

  return (
    <li className="flex items-start gap-2.5 text-sm">
      <Icon size={15} className="mt-0.5 shrink-0" style={{ color: state.color }} />
      <div className="min-w-0">
        {/* The requirement text is the posting's own words — never translated. */}
        <span className={req.status === "MISSING" ? "text-ink-muted" : "text-ink"}>{req.text}</span>
        <span className="ml-2 text-[11px] text-ink-muted">
          {kind} · {t(state.label)}
        </span>
        {req.evidence && (
          <div className="mt-0.5 font-mono text-[11px] text-ink-muted">{req.evidence}</div>
        )}
      </div>
    </li>
  );
}

function Section({
  icon,
  title,
  hint,
  items,
  color,
}: {
  icon: React.ReactNode;
  title: string;
  hint: string;
  items: string[];
  color: string;
}) {
  return (
    <div className="rounded-lg border p-3" style={{ borderColor: `${color}40` }}>
      <h3 className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink">
        {icon} {title}
      </h3>
      <p className="mt-0.5 text-[11px] text-ink-muted">{hint}</p>
      <ul className="mt-2 space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm text-ink">
            <Badge className="mt-0.5 h-fit shrink-0 border-ink/10 text-ink-muted">{i + 1}</Badge>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
