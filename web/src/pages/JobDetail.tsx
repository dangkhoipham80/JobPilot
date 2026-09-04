import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Building2,
  Check,
  ExternalLink,
  Laptop,
  MapPin,
  Sparkles,
  Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import type { JobStatus } from "@/types";
import { useT } from "@/i18n";
import { useFormat } from "@/lib/format";
import { skillLabel, useLabels } from "@/lib/labels";
import { StatusPill } from "@/components/StatusPill";
import { MatchMeter, QualityFlags } from "@/components/MatchMeter";
import { FreshBeacon } from "@/components/FreshBeacon";
import { sourceColor } from "@/components/charts/palette";
import { Badge, Button, Card, CardBody, Skeleton } from "@/components/ui";
import { JobDescription } from "@/components/JobDescription";
import { FitCard } from "@/components/FitCard";

const EARLY = new Set<JobStatus>(["DISCOVERED", "SHORTLISTED", "SKIPPED"]);
// Statuses from which the CV Review page is worth opening (matches
// tailor/service.py TAILORABLE, plus APPROVED so you can re-read what you sent).
const TAILORABLE = new Set<JobStatus>(["SHORTLISTED", "TAILORING", "REVIEW", "APPROVED", "FAILED"]);

export function JobDetail({ version }: { version: number }) {
  const t = useT("jobs");
  const fmt = useFormat();
  const labels = useLabels();
  const { id = "" } = useParams();
  const [pending, setPending] = useState(false);
  const { data: job, loading, error, refetch } = useApi(() => api.job(id), [id, version]);

  async function act(action: "shortlist" | "skip") {
    setPending(true);
    try {
      await api[action](id);
      await refetch();
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="animate-fade-up space-y-4">
      <Link
        to="/jobs"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft size={15} /> {t("back")}
      </Link>

      {error ? (
        <Card className="p-6 text-sm text-ink-muted">
          <span className="font-medium text-critical">{t("detailLoadFailed")}</span> {error}
        </Card>
      ) : loading || !job ? (
        <Skeleton className="h-72 rounded-card" />
      ) : (
        <>
          <Card>
            <CardBody className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    {job.is_fresh && <FreshBeacon withLabel />}
                    <StatusPill status={job.status} />
                  </div>
                  <h1 className="mt-2 font-display text-2xl font-semibold leading-tight tracking-tight">
                    {job.title}
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
                    <span className="inline-flex items-center gap-1.5">
                      <Building2 size={14} /> {job.company}
                    </span>
                    {job.location && (
                      <span className="inline-flex items-center gap-1.5">
                        <MapPin size={14} /> {job.location}
                      </span>
                    )}
                    {job.salary && (
                      <span className="inline-flex items-center gap-1.5">
                        <Wallet size={14} /> {job.salary}
                        {/* "up to" and "from" read very differently from a range
                            and from a fixed figure, and the posting's own label
                            does not always make that obvious at a glance. Shown
                            only when the salary parsed — a shape we could not
                            work out is not a shape worth naming. */}
                        {job.salary_kind && (
                          <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px]">
                            {labels.payKindLabel(job.salary_kind)}
                          </span>
                        )}
                      </span>
                    )}
                    {/* onsite / hybrid / remote. Shown only when the posting
                        said so — an office address is not a statement that the
                        job is on-site, and guessing one here would be a fact
                        the reader has no way to check. */}
                    {job.work_mode && (
                      <span className="inline-flex items-center gap-1.5">
                        <Laptop size={14} /> {labels.workModeLabel(job.work_mode)}
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 font-mono text-xs text-ink-muted">
                    <span
                      className="mr-1 inline-block h-2 w-2 rounded-sm align-middle"
                      style={{ background: sourceColor(job.source) }}
                    />
                    {job.id} · {t("posted")} {fmt.relativeTime(job.posted_at)}
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-3">
                  <MatchMeter score={job.match_score} quality={job.quality} />
                  <QualityFlags quality={job.quality} />
                  <div className="flex items-center gap-1.5">
                    {EARLY.has(job.status) && job.status !== "SHORTLISTED" && (
                      <Button size="sm" onClick={() => act("shortlist")} disabled={pending}>
                        <Check size={14} /> {t("shortlist")}
                      </Button>
                    )}
                    {EARLY.has(job.status) && job.status !== "SKIPPED" && (
                      <Button size="sm" variant="ghost" onClick={() => act("skip")} disabled={pending}>
                        {t("skip")}
                      </Button>
                    )}
                    {TAILORABLE.has(job.status) && (
                      <Link to={`/jobs/${encodeURIComponent(job.id)}/review`}>
                        <Button size="sm" variant={job.status === "REVIEW" ? "primary" : "outline"}>
                          <Sparkles size={14} />
                          {job.status === "REVIEW" ? t("reviewCv") : t("tailorCv")}
                        </Button>
                      </Link>
                    )}
                    {/* Hidden rather than dead when there is no URL. A pasted
                        posting often has none — you had the text, not the link —
                        and an anchor with href="" reloads the current page,
                        which reads as the app losing your place. */}
                    {job.url && (
                      <a
                        href={job.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium text-ink-muted hover:bg-surface-2 hover:text-ink"
                      >
                        <ExternalLink size={14} /> {t("original")}
                      </a>
                    )}
                  </div>
                </div>
              </div>

              {job.skills.length > 0 && (
                <div className="flex flex-wrap gap-1.5 border-t pt-4">
                  {/* A technology name, not copy: `skillLabel` only fixes the
                      casing the crawler stored it in. */}
                  {job.skills.map((skill) => (
                    <Badge key={skill} className="border-ink/10 text-ink-muted">
                      {skillLabel(skill)}
                    </Badge>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          {/* Above the JD, because the point of it is to be read *before* you
              read the whole posting and decide how to spend an hour. */}
          <FitCard job={job} onAssessed={refetch} />

          <JobDescription job={job} onSaved={refetch} />
        </>
      )}
    </div>
  );
}
