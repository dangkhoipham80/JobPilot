import { useEffect, useState } from "react";
import { AlertTriangle, ClipboardCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useFormat } from "@/lib/format";
import { useLabels } from "@/lib/labels";
import { useI18n, useT } from "@/i18n";
import { cn } from "@/lib/utils";
import { Button, Card, CardBody, CardHeader, CardTitle, Select } from "@/components/ui";
import type { CritiqueReport, CvCritique } from "@/types";

/** The presets the server knows; used before the first answer brings `roles`. */
const ROLES = ["backend", "fullstack", "frontend", "mobile", "ai", "devops", "data", "game"];

type Tone = "good" | "warn" | "low" | "bad" | "accent";

// Only tokens tailwind.config.ts defines: `good`, `accent` (the app's amber,
// doubling as "needs attention"), `critical`, `live`. A class naming a token
// that does not exist compiles to nothing, and the chip silently goes grey.
const TONE: Record<Tone, string> = {
  good: "border-good/30 bg-good/10 text-good",
  warn: "border-accent/40 bg-accent/10 text-accent",
  low: "border-border bg-surface-2 text-ink-muted",
  bad: "border-critical/30 bg-critical/10 text-critical",
  accent: "border-live/30 bg-live/10 text-live",
};

const VERDICT_TONE: Record<string, Tone> = {
  ok: "good",
  keep: "good",
  strong: "good",
  improve: "warn",
  possible: "warn",
  optional: "warn",
  trim: "low",
  skip: "low",
  cut: "bad",
  stretch: "bad",
  learn: "accent",
};

function Chip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded border px-1.5 py-0.5 text-[11px] font-medium",
        TONE[tone],
      )}
    >
      {children}
    </span>
  );
}

/** "Lumen -- Lesson Platform (5 members, `Java`)" without the CV's inline markup. */
const plain = (s: string) => s.replace(/[`*]/g, "");

function Heading({ children }: { children: React.ReactNode }) {
  return <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">{children}</h4>;
}

/**
 * Advisory review of the Master CV against the crawled ads for a target role.
 *
 * Two kinds of content, kept visibly apart: the market block is counted from
 * the crawl (every number here comes from `critique.market`), the verdicts are
 * a model's opinion. Nothing on this panel can change the CV — acting on it is
 * the user's edit, through the editor below.
 */
export function CritiquePanel({ dirty }: { dirty: boolean }) {
  const t = useT("critique");
  const { lang } = useI18n();
  const fmt = useFormat();
  const latest = useApi(() => api.latestCritique(), []);
  const [critique, setCritique] = useState<CvCritique | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The stored review arrives once; after that the panel owns what it shows.
  useEffect(() => {
    if (latest.data && critique === null) {
      setCritique(latest.data);
      if (role === null) setRole(latest.data.role);
    }
  }, [latest.data, critique, role]);

  const roles = critique?.roles ?? ROLES;
  const selected = role ?? "backend";

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setCritique(await api.critiqueCv(selected, lang));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="inline-flex items-center gap-1.5">
            <ClipboardCheck size={14} className="text-accent" /> {t("title")}
          </span>
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-4 pt-3">
        <p className="text-sm text-ink-muted">{t("intro")}</p>

        <div className="flex flex-wrap items-end gap-2">
          <label className="flex min-w-40 flex-col gap-1 text-xs text-ink-muted">
            {t("roleLabel")}
            <Select value={selected} onChange={(e) => setRole(e.target.value)} disabled={busy}>
              <option value="">{t("roleAny")}</option>
              {roles.map((r) => (
                <option key={r} value={r}>
                  {t(`role_${r}` as Parameters<typeof t>[0])}
                </option>
              ))}
            </Select>
          </label>
          <Button onClick={run} disabled={busy || dirty}>
            {critique ? t("rerun") : t("run")}
          </Button>
        </div>
        {dirty && <p className="text-xs text-accent">{t("dirty")}</p>}
        {busy && <p className="text-sm text-ink-muted">{t("busy")}</p>}
        {error && (
          <p className="flex items-start gap-1.5 text-sm text-critical">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {error}
          </p>
        )}

        {critique && <Result critique={critique} when={fmt.relativeTime(critique.created_at)} />}
      </CardBody>
    </Card>
  );
}

function Result({ critique, when }: { critique: CvCritique; when: string }) {
  const t = useT("critique");
  const { report, market } = critique;
  const stale = critique.current_version !== critique.cv_version;

  return (
    <div className="space-y-5">
      <div className="space-y-1 text-xs text-ink-muted">
        <p>{t("madeAt", { version: critique.cv_version, when })}</p>
        {stale && (
          <p className="text-accent">
            {t("stale", { current: critique.current_version, version: critique.cv_version })}
          </p>
        )}
        <p>{t("corpus", { jobs: market.jobs, total: market.total_jobs })}</p>
        {market.jobs < market.min_sample && <p className="text-accent">{t("smallSample")}</p>}
      </div>

      <section className="rounded-lg border border-border bg-surface/40 p-3">
        <p className="text-xs text-ink-muted">{t("readsAs")}</p>
        <p className="font-semibold">{report.headline}</p>
        <p className="mt-1 text-sm">{report.summary}</p>
      </section>

      {report.priorities.length > 0 && (
        <section>
          <Heading>{t("priorities")}</Heading>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {report.priorities.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ol>
        </section>
      )}

      {report.role_fits.length > 0 && (
        <section>
          <Heading>{t("roles")}</Heading>
          <ul className="space-y-2">
            {report.role_fits.map((r) => (
              <li key={r.role} className="text-sm">
                <div className="flex items-center gap-2">
                  <Chip tone={VERDICT_TONE[r.verdict]}>{t(`fit_${r.verdict}`)}</Chip>
                  <span className="font-medium">{r.role}</span>
                </div>
                <p className="mt-0.5 text-ink-muted">{r.reason}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.strengths.length > 0 && (
        <section>
          <Heading>{t("strengths")}</Heading>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {report.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      <Sections report={report} />
      <Entries report={report} />
      <Market critique={critique} />

      <p className="text-xs text-ink-muted">{t("advisory")}</p>
      {!!report.dropped && <p className="text-xs text-ink-muted">{t("dropped", { n: report.dropped })}</p>}
    </div>
  );
}

function Sections({ report }: { report: CritiqueReport }) {
  const t = useT("critique");
  if (report.sections.length === 0) return null;
  return (
    <section>
      <Heading>{t("sections")}</Heading>
      <ul className="space-y-2.5">
        {report.sections.map((s) => (
          <li key={s.key} className="text-sm">
            <div className="flex items-center gap-2">
              <Chip tone={VERDICT_TONE[s.verdict]}>{t(`v_${s.verdict}`)}</Chip>
              <span className="font-medium">{s.title}</span>
            </div>
            <p className="mt-0.5 text-ink-muted">{s.reason}</p>
            {s.suggestions.length > 0 && (
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {s.suggestions.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Entries({ report }: { report: CritiqueReport }) {
  const t = useT("critique");
  if (report.entries.length === 0) return null;
  const groups = [
    { label: t("groupImprove"), items: report.entries.filter((e) => e.verdict === "improve"), open: true },
    {
      label: t("groupTrim"),
      items: report.entries.filter((e) => e.verdict === "trim" || e.verdict === "cut"),
      open: true,
    },
    { label: t("groupKeep"), items: report.entries.filter((e) => e.verdict === "keep"), open: false },
  ].filter((g) => g.items.length > 0);

  return (
    <section>
      <Heading>{t("entries")}</Heading>
      <div className="space-y-2">
        {groups.map((g) => (
          <details key={g.label} open={g.open} className="rounded-lg border border-border">
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
              {g.label} <span className="text-ink-muted">({g.items.length})</span>
            </summary>
            <ul className="space-y-2.5 border-t border-border px-3 py-2.5">
              {g.items.map((e) => (
                <li key={`${e.section_key}-${e.entry_index}`} className="text-sm">
                  <div className="flex items-start gap-2">
                    <Chip tone={VERDICT_TONE[e.verdict]}>{t(`v_${e.verdict}`)}</Chip>
                    <span className="min-w-0 font-medium">{plain(e.title)}</span>
                  </div>
                  <p className="mt-0.5 text-ink-muted">{e.reason}</p>
                  {e.suggestion && <p className="mt-0.5">→ {e.suggestion}</p>}
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}

function Market({ critique }: { critique: CvCritique }) {
  const t = useT("critique");
  const labels = useLabels();
  const { market, report } = critique;
  const asked = [...market.cv_skills].sort((a, b) => b.count - a.count);

  return (
    <section className="space-y-3">
      <Heading>{t("market")}</Heading>
      <div>
        <p className="mb-1.5 text-xs text-ink-muted">
          {t("marketHint", { covered: market.skills.covered, jobs: market.jobs })}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {market.skills.rows.map((r) => (
            <span
              key={r.key}
              title={r.on_cv ? t("onCv") : t("notOnCv")}
              className={cn(
                "rounded border px-1.5 py-0.5 text-xs",
                r.on_cv ? TONE.good : "border-border text-ink-muted",
              )}
            >
              {r.key} <span className="font-mono opacity-70">{r.count}</span>
            </span>
          ))}
        </div>
      </div>

      {report.skills.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium">{t("gaps")}</p>
          <ul className="space-y-1.5">
            {report.skills.map((s) => (
              <li key={s.skill} className="flex items-start gap-2 text-sm">
                <Chip tone={VERDICT_TONE[s.advice]}>{t(`a_${s.advice}`)}</Chip>
                <span>
                  <span className="font-medium">{s.skill}</span>{" "}
                  <span className="text-ink-muted">— {s.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {asked.length > 0 && (
        <div>
          <p className="text-xs font-medium">{t("cvSkills")}</p>
          <p className="mb-1.5 text-xs text-ink-muted">{t("cvSkillsHint")}</p>
          <div className="flex flex-wrap gap-1.5">
            {asked.map((s) => (
              <span
                key={s.name}
                className={cn(
                  "rounded border px-1.5 py-0.5 text-xs",
                  s.count > 0 ? "border-border" : "border-dashed border-border text-ink-muted",
                )}
              >
                {s.name}{" "}
                <span className="font-mono opacity-70">{s.count > 0 ? s.count : t("noDemand")}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {market.levels.rows.length > 0 && (
        <div>
          <p className="text-xs font-medium">{t("levels")}</p>
          <p className="mb-1.5 text-xs text-ink-muted">
            {t("levelsHint", { covered: market.levels.covered, jobs: market.jobs })}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {market.levels.rows.map((r) => (
              <span key={r.key} className="rounded border border-border px-1.5 py-0.5 text-xs">
                {labels.levelLabel(r.key)} <span className="font-mono opacity-70">{r.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
