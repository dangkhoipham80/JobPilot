import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarOff,
  CheckCircle2,
  Clock,
  FileQuestion,
  FileWarning,
  type LucideIcon,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui";
import { TooltipBox, axisColor, gridColor } from "@/components/charts/ChartFrame";
import { SourceDonut } from "@/components/charts/SourceDonut";
import { MUTED, STATUS, categorical, ordinalRamp } from "@/components/charts/palette";
import { useT } from "@/i18n";
import { useFormat } from "@/lib/format";
import { skillLabel, useLabels } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Facet, FacetRow } from "@/types";

/** The one hue every magnitude chart on this page uses. Skills, cities and the
 *  two histograms all answer "how many jobs", so they are one measure and wear
 *  one colour; the page reads as a system instead of a sampler. Identity only
 *  gets its own hues where identity is the point — the source ring. */
const MEASURE = () => categorical()[0];

/** Posting quality is *state*, not identity, so it wears the reserved status
 *  scale — and, as that scale requires, never colour alone: each row carries an
 *  icon and a spelled-out label. `undated` is deliberately the neutral grey:
 *  a posting with no date is one we don't know about, not one that's gone off. */
const QUALITY_TONE: Record<string, { color: string; icon: LucideIcon }> = {
  clean: { color: STATUS.good, icon: CheckCircle2 },
  stale: { color: STATUS.warning, icon: Clock },
  thin_jd: { color: STATUS.serious, icon: FileWarning },
  no_jd: { color: STATUS.critical, icon: FileQuestion },
  undated: { color: MUTED, icon: CalendarOff },
};

/** Section ids paired with their dictionary key. `as const` is load-bearing:
 *  it keeps `s.key` a union of literal keys, so a typo here is a compile error
 *  in `t(s.key)` rather than a nav item that renders its own key name. */
const SECTIONS = [
  { id: "overview", key: "navOverview" },
  { id: "skills", key: "navSkills" },
  { id: "salary", key: "navSalary" },
  { id: "cities", key: "navCities" },
  { id: "levels", key: "navLevels" },
  { id: "match", key: "navMatch" },
  { id: "quality", key: "navQuality" },
  { id: "sources", key: "navSources" },
  { id: "calendar", key: "navCalendar" },
] as const;

/**
 * How much of the corpus a chart actually saw.
 *
 * Printed as "23 of 73 jobs", never as a bare percentage: the percentage is the
 * thing that makes a sparse facet look authoritative. LinkedIn is the largest
 * source here and carries no skills, no salary and no tags, so most facets are
 * describing a minority of the market and have to say so.
 */
function Coverage({ facet }: { facet: Facet }) {
  const t = useT("market");
  return (
    <span className="text-xs font-normal text-muted-foreground">
      {t("coverage", { covered: facet.covered, total: facet.total })}
    </span>
  );
}

/** The analytics layer's own sentence about why a facet is thin. It is a
 *  backend value like `task.progress`, so it renders in whatever language the
 *  API emitted rather than going through the dictionary. */
function Note({ facet }: { facet: Facet }) {
  if (!facet.note) return null;
  return (
    <p className="mt-3 flex items-start gap-1.5 text-sm text-amber-700 dark:text-amber-500">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      {facet.note}
    </p>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-24 place-items-center text-sm text-muted-foreground">{children}</div>
  );
}

/**
 * Horizontal bars, directly labelled — the right form when the labels are long
 * words and the measure is a simple count.
 *
 * `color` is per *row*, and passing it is a claim: that the rows are an ordered
 * scale (seniority) or a set of states (quality flags), where hue carries
 * something the bar length doesn't. Left off — the default — every bar is the
 * one measure colour. Cycling hues down a nominal ranking would colour by
 * *rank*, spending the identity channel to re-say what the bars already show
 * and repainting itself the moment the order changes.
 */
function FacetBars({
  facet,
  label = (k: string) => k,
  color,
}: {
  facet: Facet;
  label?: (key: string) => string;
  color?: (key: string, index: number, total: number) => string;
}) {
  // Above the early return: hooks cannot be conditional on the row count.
  const t = useT("market");
  const source = facet.rows.filter((r) => r.key !== "_summary");
  const rows = source.map((r) => ({ ...r, label: label(r.key) }));
  if (!rows.length) return <Empty>{t("emptyRows")}</Empty>;
  const measure = MEASURE();
  return (
    <ResponsiveContainer width="100%" height={Math.max(rows.length * 28, 88)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 40, top: 4, bottom: 4 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          width={140}
          tick={{ fontSize: 12, fill: axisColor() }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={false}
          content={({ payload }) =>
            payload?.length ? (
              <TooltipBox
                label={String(payload[0].payload.label)}
                rows={[{ key: t("tipJobs"), value: String(payload[0].payload.count) }]}
              />
            ) : null
          }
        />
        <Bar dataKey="count" radius={[0, 3, 3, 0]} maxBarSize={12} isAnimationActive={false}>
          {rows.map((r, i) => (
            <Cell key={r.key} fill={color ? color(r.key, i, rows.length) : measure} />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            className="fill-muted-foreground"
            fontSize={12}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Quality flags: the bars plus the icon-and-word key the status scale is only
 *  allowed to be used with. */
function QualityChart({ facet }: { facet: Facet }) {
  const labels = useLabels();
  const rows = facet.rows.filter((r) => r.key !== "_summary");
  return (
    <>
      <FacetBars
        facet={facet}
        label={labels.qualityLabel}
        color={(key) => QUALITY_TONE[key]?.color ?? MUTED}
      />
      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
        {rows.map((r) => {
          const tone = QUALITY_TONE[r.key];
          const Icon = tone?.icon ?? AlertTriangle;
          return (
            <li key={r.key} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Icon className="h-3.5 w-3.5" style={{ color: tone?.color ?? MUTED }} />
              {labels.qualityLabel(r.key)}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** Vertical bars for an ordered distribution (a histogram), where the x axis
 *  carries meaning and reordering it would destroy that. The bands are already
 *  in order along the axis, so the bars are one measure in one colour — a ramp
 *  here would encode the x position a second time, in hue. */
function FacetHistogram({ facet }: { facet: Facet }) {
  const t = useT("market");
  const rows = facet.rows.filter((r) => r.key !== "_summary");
  if (!rows.length || rows.every((r) => !r.count)) return <Empty>{t("emptyRows")}</Empty>;
  return (
    <ResponsiveContainer width="100%" height={190}>
      <BarChart data={rows} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
        <CartesianGrid vertical={false} stroke={gridColor()} strokeDasharray="0" />
        <XAxis
          dataKey="key"
          tick={{ fontSize: 11, fill: axisColor() }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fontSize: 11, fill: axisColor() }}
          axisLine={false}
          tickLine={false}
          width={28}
        />
        <Tooltip
          cursor={false}
          content={({ payload, label }) =>
            payload?.length ? (
              <TooltipBox
                label={String(label)}
                rows={[{ key: t("tipJobs"), value: String(payload[0].value) }]}
              />
            ) : null
          }
        />
        <Bar
          dataKey="count"
          fill={MEASURE()}
          radius={[3, 3, 0, 0]}
          maxBarSize={40}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Whole dollars with a thousands separator. The conversion is an estimate off
 *  a rate with a check-date on it, so the tenth of a dollar `$1574.8` was
 *  showing was precision the number does not have. */
const usd = (n: number | undefined) =>
  n === undefined ? "—" : `$${Math.round(n).toLocaleString("en-US")}`;

/**
 * Postings per day, as a time series.
 *
 * A column chart of dates was the wrong form twice over: it treated a
 * continuous axis as a row of independent categories, and — sharing both its
 * shape and its hue with the source chart above it — it read as the *same
 * chart drawn twice*. An area over a date axis says "over time" at a glance,
 * which is the one thing this facet is for.
 */
function PostingTrend({ facet }: { facet: Facet }) {
  const t = useT("market");
  const fmt = useFormat();
  // Axis ticks want the short form; the tooltip is the one place worth spending
  // the room on a year, since a corpus can span a new year's boundary and
  // "Jan 3" alone would then be ambiguous against "Dec 30". Built here, at the
  // top of a component, so the recharts callbacks below only close over it —
  // `useFormat` is a hook and must not be called inside a formatter.
  const fullDay = (iso: string) => {
    const day = fmt.shortDay(iso);
    // `shortDay` echoes its input back when the date does not parse; appending
    // a "year" sliced off a non-date would manufacture nonsense.
    if (day === iso || !/^\d{4}-/.test(iso)) return day;
    return t("dayWithYear", { day, year: iso.slice(0, 4) });
  };
  const rows = facet.rows.filter((r) => r.key !== "_summary");
  // No all-zero early return, deliberately — unlike the histogram. A flat line
  // across thirty days means nobody posted for a month, which is a fact about
  // the market and belongs on the chart. An empty histogram means the bands
  // have nothing to divide, which is not.
  if (!rows.length) return <Empty>{t("emptyDates")}</Empty>;
  const measure = MEASURE();
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={rows} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
        <defs>
          <linearGradient id="postingFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={measure} stopOpacity={0.28} />
            <stop offset="100%" stopColor={measure} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={gridColor()} strokeDasharray="0" />
        <XAxis
          dataKey="key"
          tickFormatter={(v) => fmt.shortDay(String(v))}
          // Let recharts drop ticks rather than overlap them: 26 dates in a
          // card this wide collided into a grey smear.
          minTickGap={28}
          tick={{ fontSize: 11, fill: axisColor() }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fontSize: 11, fill: axisColor() }}
          axisLine={false}
          tickLine={false}
          width={28}
        />
        <Tooltip
          cursor={{ stroke: gridColor(), strokeWidth: 1 }}
          content={({ payload, label }) =>
            payload?.length ? (
              <TooltipBox
                label={fullDay(String(label))}
                rows={[{ key: t("tipPosted"), value: String(payload[0].value), color: measure }]}
              />
            ) : null
          }
        />
        <Area
          // Linear, not monotone: a spline through integer daily counts invents
          // peaks on days nobody posted and rounds off the days they did.
          type="linear"
          dataKey="count"
          stroke={measure}
          strokeWidth={2}
          fill="url(#postingFill)"
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--viz-surface, #fff)" }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function Section({
  id,
  title,
  facet,
  children,
}: {
  id: string;
  title: string;
  facet?: Facet;
  children: React.ReactNode;
}) {
  return (
    <Card id={id} className="scroll-mt-20">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {facet && <Coverage facet={facet} />}
      </CardHeader>
      <CardBody>
        {children}
        {facet && <Note facet={facet} />}
      </CardBody>
    </Card>
  );
}

/**
 * Market (Phase 21) — what the crawled corpus looks like.
 *
 * Every chart here is drawn from `jobs.payload`, so it describes **the ads this
 * crawler happened to collect**, not the Vietnamese job market. The coverage
 * line on each card is what keeps that distinction visible: a skills ranking
 * built from 18 of 73 jobs is a real finding about 18 jobs and a fiction about
 * the market, and only the denominator tells them apart.
 */
export function Market({ version }: { version: number }) {
  const t = useT("market");
  const labels = useLabels();
  const { data, loading, error } = useApi(() => api.market(), [version]);
  const [active, setActive] = useState("overview");

  // Follow the scroll, not just the clicks. Highlighting only on click leaves
  // "Skills" lit while you are reading "Salary", which makes the nav actively
  // misleading on a page this tall — worse than having no highlight at all.
  useEffect(() => {
    if (!data) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActive(visible.target.id);
      },
      // Top third of the viewport: a section counts as "the one you're reading"
      // when its heading is near the top, not when it first peeks into view.
      { rootMargin: "-80px 0px -66% 0px" },
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [data]);

  const salarySummary = useMemo(
    () => data?.salary.rows.find((r: FacetRow) => r.key === "_summary"),
    [data],
  );

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <Card>
        <CardBody className="py-6 text-sm text-red-600 dark:text-red-400">
          {t("loadFailed", { error: error ?? "" })}
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="flex gap-6">
      {/* Section nav. Deliberately inside the page rather than a second global
          sidebar — Layout already owns one, and adding another there would
          reshape every page to serve this one. */}
      <nav className="sticky top-20 hidden h-fit w-40 shrink-0 lg:block">
        <p className="px-3 pb-2 text-xs uppercase tracking-wide text-muted-foreground">
          {t("sections")}
        </p>
        <ul className="space-y-0.5">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                onClick={() => setActive(s.id)}
                className={cn(
                  "block rounded-lg px-3 py-1.5 text-sm transition-colors",
                  active === s.id
                    ? "bg-ink/10 font-medium text-foreground"
                    : "text-muted-foreground hover:bg-ink/5 hover:text-foreground",
                )}
              >
                {t(s.key)}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="min-w-0 flex-1 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("intro", { count: data.total_jobs })}
          </p>
        </div>

        <div id="overview" className="grid gap-4 scroll-mt-20 sm:grid-cols-3">
          <Card>
            <CardBody className="py-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {t("statPostings")}
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{data.total_jobs}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("statSources", { count: data.sources.rows.length })}
              </p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="py-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {t("statMedian")}
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {usd(salarySummary?.median_usd_month)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {salarySummary
                  ? t("statMedianFrom", { count: data.salary.covered })
                  : t("statMedianNone")}
              </p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="py-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {t("statClean")}
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {data.quality.rows.find((r) => r.key === "clean")?.count ?? 0}
                <span className="text-base font-normal text-muted-foreground">
                  /{data.total_jobs}
                </span>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{t("statCleanHint")}</p>
            </CardBody>
          </Card>
        </div>

        <Section id="skills" title={t("skillsTitle")} facet={data.skills}>
          {/* Skill names are proper nouns out of the corpus (`PostgreSQL`,
              `CI/CD`), so `skillLabel` stays a plain, language-free function. */}
          <FacetBars facet={data.skills} label={skillLabel} />
          <p className="mt-3 text-xs text-muted-foreground">{t("skillsNote")}</p>
        </Section>

        <Section id="salary" title={t("salaryTitle")} facet={data.salary}>
          {/* Under the sample floor the bands are a single bar in an empty
              grid — the "one-bar bar chart" that should have been a number.
              Show the number, and say what it is drawn from. */}
          {data.salary.covered >= data.min_sample ? (
            <FacetHistogram facet={data.salary} />
          ) : salarySummary ? (
            <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2 py-2">
              <div>
                <p className="text-2xl font-semibold">{usd(salarySummary.median_usd_month)}</p>
                <p className="text-xs text-muted-foreground">{t("salaryMedian")}</p>
              </div>
              <div className="text-sm text-muted-foreground">
                {t("salaryThin", { covered: data.salary.covered, total: data.salary.total })}
              </div>
            </div>
          ) : (
            <Empty>{t("emptySalary")}</Empty>
          )}
          {salarySummary && (
            <p className="mt-3 text-xs text-muted-foreground">
              {t("salaryRange", {
                min: usd(salarySummary.min_usd_month),
                max: usd(salarySummary.max_usd_month),
                rate: salarySummary.fx_rate?.toLocaleString() ?? "—",
                date: salarySummary.fx_checked_on ?? "—",
              })}
            </p>
          )}
        </Section>

        {/* No `label` prop: city names come from the corpus and are proper
            nouns, so the raw key is already the right display string. */}
        <Section id="cities" title={t("citiesTitle")} facet={data.cities}>
          <FacetBars facet={data.cities} />
        </Section>

        <Section id="levels" title={t("levelsTitle")} facet={data.levels}>
          {/* The one bar chart here whose rows are an ordered scale, so the one
              that earns a ramp: junior → senior darkens. */}
          <FacetBars
            facet={data.levels}
            label={labels.levelLabel}
            color={(_key, i, total) => ordinalRamp(total)[i]}
          />
          <p className="mt-3 text-xs text-muted-foreground">{t("levelsNote")}</p>
        </Section>

        <Section id="match" title={t("matchTitle")} facet={data.match_scores}>
          <FacetHistogram facet={data.match_scores} />
          <p className="mt-3 text-xs text-muted-foreground">
            {t("matchNoteBefore")}
            <code>crawl.stacks</code>
            {t("matchNoteAfter")}
          </p>
        </Section>

        <Section id="quality" title={t("qualityTitle")} facet={data.quality}>
          <QualityChart facet={data.quality} />
          <p className="mt-3 text-xs text-muted-foreground">{t("qualityNote")}</p>
        </Section>

        <Section id="sources" title={t("sourcesTitle")} facet={data.sources}>
          <SourceDonut rows={data.sources.rows} total={data.total_jobs} />
          <p className="mt-4 text-xs text-muted-foreground">{t("sourcesNote")}</p>
        </Section>

        <Section id="calendar" title={t("calendarTitle")} facet={data.calendar}>
          <PostingTrend facet={data.calendar} />
          <p className="mt-3 text-xs text-muted-foreground">
            {t("calendarNoteBefore")}
            <em>{t("calendarNoteEm")}</em>
            {t("calendarNoteAfter")}
          </p>
        </Section>
      </div>
    </div>
  );
}
