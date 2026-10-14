import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Check, ExternalLink, History, Layers, Search, X } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useClampPage, usePaging } from "@/hooks/usePaging";
import type { Job, JobStatus, JobsQuery } from "@/types";
import { useT } from "@/i18n";
import { titleCase, useFormat } from "@/lib/format";
import { useLabels } from "@/lib/labels";
import { useStatuses } from "@/lib/statuses";
import { StatusPill } from "@/components/StatusPill";
import { MatchMeter, QualityFlags } from "@/components/MatchMeter";
import { FreshBeacon } from "@/components/FreshBeacon";
import { sourceColor } from "@/components/charts/palette";
import { Button, Card, Input, Select, Skeleton } from "@/components/ui";
import { AddJobForm } from "@/components/AddJobForm";
import { Pagination } from "@/components/Pagination";

const EARLY = new Set<JobStatus>(["DISCOVERED", "SHORTLISTED", "SKIPPED"]);

/**
 * Crawl-time windows. `hours: null` means "any time".
 *
 * The visible name is a dictionary key, resolved at render, so the dropdown
 * follows the language switch instead of freezing whatever was current when the
 * module first evaluated.
 */
const WINDOWS = [
  { key: "", label: "windowAny", hours: null },
  { key: "24h", label: "window24h", hours: 24 },
  { key: "7d", label: "window7d", hours: 24 * 7 },
  { key: "30d", label: "window30d", hours: 24 * 30 },
] as const;

/**
 * Match-score bands. Half-open on the API side — `min` <= score < `below` — so
 * a job scoring exactly 50% is in one band, not two, and the four bands add up
 * to the whole list.
 */
const MATCH_BANDS: {
  key: string;
  label: "matchAny" | "match75" | "match50" | "match25" | "match0";
  min?: number;
  below?: number;
}[] = [
  { key: "", label: "matchAny" },
  { key: "75", label: "match75", min: 0.75 },
  { key: "50", label: "match50", min: 0.5, below: 0.75 },
  { key: "25", label: "match25", min: 0.25, below: 0.5 },
  { key: "0", label: "match0", below: 0.25 },
];

/** The three orderings the API offers; `crawled` is its default and ours. */
const ORDERS = [
  { key: "crawled", label: "sortCrawled", summary: "orderCrawled" },
  { key: "match", label: "sortMatch", summary: "orderMatch" },
  { key: "posted", label: "sortPosted", summary: "orderPosted" },
] as const;
type Order = (typeof ORDERS)[number]["key"];

export function Jobs({ version }: { version: number }) {
  const t = useT("jobs");
  const common = useT("common");
  const labels = useLabels();
  const statusInfo = useStatuses();
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [level, setLevel] = useState("");
  const [fresh, setFresh] = useState(false);
  const [allCopies, setAllCopies] = useState(false);
  const [win, setWin] = useState("");
  const [band, setBand] = useState("");
  const [order, setOrder] = useState<Order>("crawled");
  const [pending, setPending] = useState<string | null>(null);

  // `run` and `status` live in the URL, not in state: both are arrived at from
  // somewhere else — the Runs page ("what did this crawl find?") and the Guide
  // ("3 jobs are waiting on you") — and a link has to be able to say which.
  const [params, setParams] = useSearchParams();
  const runId = Number(params.get("run")) || undefined;
  const status = params.get("status") ?? "";

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  // Filter options are whatever is actually in the database, so the list can
  // never drift out of step with the sources and levels really being crawled.
  const { data: stats } = useApi(() => api.stats(), [version]);
  const sources = Object.keys(stats?.by_source ?? {}).sort();
  const levels = Object.keys(stats?.by_level ?? {}).sort();
  // The API seeds by_status with every JobStatus, so this stays complete even
  // for statuses no job currently has. The URL's own status is folded in
  // regardless: while stats is still loading the <select> would otherwise show
  // blank while the filter *is* applied, which reads as a broken link.
  const statuses = Object.keys(stats?.by_status ?? {}) as JobStatus[];
  if (status && !statuses.includes(status as JobStatus)) statuses.unshift(status as JobStatus);

  const paging = usePaging("jobs");
  const { size, offset, page, setPage, reset } = paging;

  const query: JobsQuery = useMemo(() => {
    const hours = WINDOWS.find((w) => w.key === win)?.hours ?? null;
    const matchBand = MATCH_BANDS.find((b) => b.key === band);
    return {
      q: q || undefined,
      source: source || undefined,
      level: level || undefined,
      status: (status || undefined) as JobStatus | undefined,
      fresh: fresh || undefined,
      reposts: allCopies || undefined,
      run_id: runId,
      crawled_after: hours ? new Date(Date.now() - hours * 3600 * 1000).toISOString() : undefined,
      match_min: matchBand?.min,
      match_below: matchBand?.below,
      // Chosen, not inferred. This used to flip to "crawled" whenever a time
      // window or a run filter was on; now that is the default everywhere and
      // the dropdown says which order you are looking at.
      order,
      limit: size,
      offset,
    };
  }, [q, source, level, status, fresh, allCopies, win, band, order, runId, size, offset]);

  // A changed filter means a different list, so page 7 of the old one is not a
  // place in the new one. Without this, narrowing a search from 300 hits to 4
  // lands on an empty table with no clue that the rows are on page 1.
  const filterKey = JSON.stringify([q, source, level, status, fresh, allCopies, win, band, order, runId]);
  useEffect(reset, [filterKey, reset]);

  const { data, loading, error, refetch } = useApi(() => api.jobs(query), [query, version]);
  const jobs = data?.items;
  useClampPage(data?.total, paging);

  async function act(id: string, action: "shortlist" | "skip") {
    setPending(id);
    try {
      await api[action](id);
      await refetch();
    } finally {
      setPending(null);
    }
  }

  const hasFilters = q || source || level || status || fresh || allCopies || win || band || runId;

  return (
    <div className="animate-fade-up space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="mt-0.5 text-sm text-ink-muted">
            {/* Everything the filters matched, not this page. `jobs.length`
                used to be the same number; now it would say "25 matched" for a
                search with 83 hits, and the pager below already reports the
                window. */}
            {data ? t("matching", { count: data.total }) : common("loading")} ·{" "}
            {t(ORDERS.find((o) => o.key === order)?.summary ?? "orderCrawled")}
          </p>
        </div>
        <AddJobForm onCreated={() => refetch()} />
      </div>

      {runId && (
        <Card className="flex items-center gap-2 px-3 py-2 text-sm">
          <History size={14} className="text-accent" />
          <span>
            {t("runFilterPrefix")}{" "}
            <span className="font-medium">{t("runFilterCrawl", { id: runId })}</span>{" "}
            {t("runFilterSuffix")}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => setParams({}, { replace: true })}
          >
            <X size={14} /> {t("showAll")}
          </Button>
        </Card>
      )}

      {/* Filter bar */}
      <Card className="flex flex-wrap items-center gap-2 p-3">
        <div className="relative min-w-[200px] flex-1">
          <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("searchPlaceholder")}
            className="pl-8"
          />
        </div>
        <Select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">{t("allSources")}</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {labels.sourceLabel(s)}
            </option>
          ))}
        </Select>
        <Select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">{t("allLevels")}</option>
          {levels.map((l) => (
            <option key={l} value={l}>
              {labels.levelLabel(l)}
            </option>
          ))}
        </Select>
        <Select value={status} onChange={(e) => setParam("status", e.target.value)}>
          <option value="">{t("allStatuses")}</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {titleCase(statusInfo.info(s).label)}
            </option>
          ))}
        </Select>
        <Select value={win} onChange={(e) => setWin(e.target.value)} title={t("windowTitle")}>
          {WINDOWS.map((w) => (
            <option key={w.key} value={w.key}>
              {t(w.label)}
            </option>
          ))}
        </Select>
        <Select value={band} onChange={(e) => setBand(e.target.value)} title={t("matchTitle")}>
          {MATCH_BANDS.map((b) => (
            <option key={b.key} value={b.key}>
              {t(b.label)}
            </option>
          ))}
        </Select>
        <Select
          value={order}
          onChange={(e) => setOrder(e.target.value as Order)}
          title={t("sortTitle")}
        >
          {ORDERS.map((o) => (
            <option key={o.key} value={o.key}>
              {t(o.label)}
            </option>
          ))}
        </Select>
        <button
          onClick={() => setFresh((f) => !f)}
          className={
            "inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm font-medium transition-colors " +
            (fresh ? "border-accent bg-accent/10 text-accent" : "text-ink-muted hover:bg-surface-2")
          }
        >
          <FreshBeacon /> {t("freshOnly")}
        </button>
        <button
          onClick={() => setAllCopies((v) => !v)}
          title={t("allCopiesHint")}
          className={
            "inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm font-medium transition-colors " +
            (allCopies ? "border-accent bg-accent/10 text-accent" : "text-ink-muted hover:bg-surface-2")
          }
        >
          <Layers size={14} /> {t("allCopies")}
        </button>
        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQ("");
              setSource("");
              setLevel("");
              setFresh(false);
              setAllCopies(false);
              setWin("");
              setBand("");
              setParams({}, { replace: true });
            }}
          >
            <X size={14} /> {t("clear")}
          </Button>
        )}
      </Card>

      {error ? (
        <Card className="p-6 text-sm text-ink-muted">
          <span className="font-medium text-critical">{t("loadFailed")}</span> {error}
        </Card>
      ) : loading || !jobs ? (
        <TableSkeleton />
      ) : jobs.length === 0 ? (
        <EmptyState hasFilters={!!hasFilters} />
      ) : (
        <Card className="overflow-hidden">
          {/* Titles wrap, so the role column has a floor it will not go under;
              below that the table scrolls sideways inside the card rather than
              being clipped by it. */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wide text-ink-muted">
                  <th className="px-4 py-2.5 font-medium">{t("colRole")}</th>
                  <th className="px-2 py-2.5 font-medium">{t("colSource")}</th>
                  <th className="px-2 py-2.5 font-medium">{t("colMatch")}</th>
                  <th className="px-2 py-2.5 font-medium">{t("colStatus")}</th>
                  <th className="px-2 py-2.5 font-medium">{t("colPosted")}</th>
                  <th className="px-2 py-2.5 font-medium">{t("colCrawled")}</th>
                  <th className="px-4 py-2.5 text-right font-medium">{t("colActions")}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <Row key={job.id} job={job} pending={pending === job.id} onAct={act} />
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            className="px-4 pb-3"
            page={page}
            size={size}
            total={data?.total ?? 0}
            onPage={setPage}
            onSize={paging.setSize}
            noun={t("jobsNoun")}
          />
        </Card>
      )}
    </div>
  );
}

function Row({
  job,
  pending,
  onAct,
}: {
  job: Job;
  pending: boolean;
  onAct: (id: string, action: "shortlist" | "skip") => void;
}) {
  const t = useT("jobs");
  const fmt = useFormat();
  const labels = useLabels();
  const isFresh =
    !!job.posted_at && Date.now() - new Date(job.posted_at).getTime() < 48 * 3600 * 1000;
  const skipped = job.status === "SKIPPED";
  return (
    <tr className="border-b last:border-0 hover:bg-surface-2/60">
      {/* A share of the table, not "whatever is left over": as `w-full` this
          column took every spare pixel, so on a wide screen a title sat some
          700px from its own status and actions. Text wraps instead of being
          truncated — "Backend Developer (Java, Sp…" hides the half that tells
          two postings apart — and `overflow-wrap: anywhere` lets a long
          unbroken token wrap too rather than widen the column. */}
      <td className="w-[38%] min-w-[12rem] px-4 py-3">
        <Link to={`/jobs/${encodeURIComponent(job.id)}`} className="group block">
          <div className="flex items-start gap-1.5">
            {/* Pinned to the first line now that the title can run to two. */}
            {isFresh && <FreshBeacon className="mt-1.5 shrink-0" />}
            <span
              className={
                "font-medium [overflow-wrap:anywhere] group-hover:text-accent " +
                // A skipped job has had its decision; its title steps back so
                // the rows still waiting on one are the ones that read first.
                (skipped ? "text-ink-muted" : "text-ink")
              }
            >
              {job.title}
            </span>
            {!!job.reposts && (
              <span
                className="mt-0.5 shrink-0 rounded border border-border px-1.5 text-[11px] text-ink-muted"
                title={t("repostedHint", { n: job.reposts })}
              >
                {t("reposted", { n: job.reposts })}
              </span>
            )}
            {job.latest_id && (
              <span className="mt-0.5 shrink-0 rounded border border-border px-1.5 text-[11px] text-ink-muted">
                {t("olderCopy")}
              </span>
            )}
          </div>
          <div className="text-xs text-ink-muted [overflow-wrap:anywhere]">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
            {job.salary ? ` · ${job.salary}` : ""}
          </div>
        </Link>
      </td>
      <td className="px-2 py-3">
        <span className="inline-flex items-center gap-1.5 text-xs text-ink-muted">
          <span className="h-2 w-2 rounded-sm" style={{ background: sourceColor(job.source) }} />
          {labels.sourceLabel(job.source)}
        </span>
      </td>
      <td className="px-2 py-3">
        <MatchMeter score={job.match_score} quality={job.quality} />
        <QualityFlags quality={job.quality} className="mt-1" />
      </td>
      <td className="px-2 py-3">
        <StatusPill status={job.status} />
      </td>
      <td className="whitespace-nowrap px-2 py-3 font-mono text-xs tabular-nums text-ink-muted">
        {fmt.relativeTime(job.posted_at)}
      </td>
      <td className="whitespace-nowrap px-2 py-3 font-mono text-xs tabular-nums text-ink-muted">
        {job.run_id ? (
          <Link
            to={`/jobs?run=${job.run_id}`}
            className="hover:text-accent"
            title={t("onlyFromCrawl", { id: job.run_id })}
          >
            {fmt.relativeTime(job.crawled_at)}
          </Link>
        ) : (
          <span title={t("addedByHand")}>{fmt.relativeTime(job.crawled_at)}</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1">
          {EARLY.has(job.status) && job.status !== "SHORTLISTED" && (
            <Button size="sm" onClick={() => onAct(job.id, "shortlist")} disabled={pending}>
              <Check size={14} /> {t("shortlist")}
            </Button>
          )}
          {EARLY.has(job.status) && job.status !== "SKIPPED" && (
            <Button size="sm" variant="ghost" onClick={() => onAct(job.id, "skip")} disabled={pending}>
              {t("skip")}
            </Button>
          )}
          <a
            href={job.url}
            target="_blank"
            rel="noreferrer"
            className="grid h-8 w-8 place-items-center rounded-lg text-ink-muted hover:bg-surface-2 hover:text-ink"
            title={t("openOriginal")}
          >
            <ExternalLink size={14} />
          </a>
        </div>
      </td>
    </tr>
  );
}

function TableSkeleton() {
  return (
    <Card className="divide-y p-0">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-4">
          <Skeleton className="h-8 flex-1" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-24" />
        </div>
      ))}
    </Card>
  );
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  const t = useT("jobs");
  return (
    <Card className="grid place-items-center gap-1 py-16 text-center">
      <p className="font-medium text-ink">{hasFilters ? t("emptyFiltered") : t("empty")}</p>
      <p className="text-sm text-ink-muted">
        {hasFilters ? (
          t("emptyFilteredHint")
        ) : (
          // The command is the same in every language — it is what you type.
          <>
            {t("emptyHint")} <code className="font-mono">python -m jobpilot.cli crawl</code>
          </>
        )}
      </p>
    </Card>
  );
}
