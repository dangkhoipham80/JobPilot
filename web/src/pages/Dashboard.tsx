import { Flame, Layers, MessageSquare, Send, Sparkles, Target } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { StatCard } from "@/components/StatCard";
import { SourceScorecard } from "@/components/SourceScorecard";
import { ApproachFunnel } from "@/components/ApproachFunnel";
import { BySourceChart } from "@/components/charts/BySourceChart";
import { ByDayChart } from "@/components/charts/ByDayChart";
import { Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui";
import { useT } from "@/i18n";
import type { Stats } from "@/types";

export function Dashboard({ version }: { version: number }) {
  const t = useT("dashboard");
  const { data: stats, loading, error } = useApi(() => api.stats(), [version]);
  // Its own request: a failure here must not blank the funnel, and the deck is
  // useful without it.
  const { data: analytics } = useApi(() => api.outcomeAnalytics(), [version]);

  if (error) return <ErrorState message={error} />;
  if (loading || !stats) return <DashboardSkeleton />;

  const s = stats.by_status;
  const decided = s.SUBMITTED + s.FAILED;
  const successRate = decided > 0 ? Math.round((s.SUBMITTED / decided) * 100) : null;

  return (
    <div className="animate-fade-up space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("subtitle")}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label={t("crawled")}
          value={stats.total}
          icon={<Layers size={16} />}
          note={t("crawledNote")}
        />
        <StatCard
          label={t("fresh")}
          value={stats.fresh}
          accent
          icon={<Flame size={16} />}
          note={t("freshNote")}
        />
        <StatCard
          label={t("shortlisted")}
          value={s.SHORTLISTED}
          icon={<Sparkles size={16} />}
          note={t("shortlistedNote")}
        />
        <StatCard
          label={t("applied")}
          value={s.SUBMITTED}
          icon={<Send size={16} />}
          note={t("appliedNote")}
        />
        {/* Not "success" — this only measures whether the dispatch itself went
            through. Once real outcomes sit in the row below, a tile reading
            "Success 100% · landed" above an application that was rejected is a
            straight contradiction. */}
        <StatCard
          label={t("sentOk")}
          value={successRate === null ? "—" : `${successRate}%`}
          icon={<Target size={16} />}
          note={
            decided === 0
              ? t("sentOkIdle")
              : t("sentOkNote", { sent: s.SUBMITTED, decided })
          }
        />
      </div>

      <OutcomeRow outcomes={stats.outcomes} />

      {/* Which board earned those answers (PLAN.md §9.1 slot 20). The outcome
          tables need something to have been sent — an empty scorecard would be
          four cards of "nothing yet" above a funnel that already says so — but
          repeat postings come from the crawl corpus alone, so a user with 80
          crawled jobs and no applications still gets that card. */}
      {analytics && (analytics.total_sent > 0 || analytics.repeats.total_groups > 0) && (
        <SourceScorecard data={analytics} />
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>{t("funnelTitle")}</CardTitle>
          </CardHeader>
          <CardBody>
            <ApproachFunnel stats={stats} />
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("bySourceTitle")}</CardTitle>
          </CardHeader>
          <CardBody>
            <BySourceChart data={stats.by_source} />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("byDayTitle")}</CardTitle>
          <span className="text-xs text-ink-muted">{t("byDayMeta")}</span>
        </CardHeader>
        <CardBody>
          <ByDayChart data={stats.by_day} />
        </CardBody>
      </Card>
    </div>
  );
}

/**
 * What happened after the applications went out (Phase 18).
 *
 * Rates come from `reached`, not from the board's current column: an
 * application that interviewed and was then rejected shows as "rejected"
 * today, and counting interviews that way would report the ones *stuck* in
 * interviews instead of the ones that got one.
 *
 * A rate over a handful of applications is noise wearing a percent sign, so
 * under ten the tile shows the count and says so instead.
 */
function OutcomeRow({ outcomes }: { outcomes: Stats["outcomes"] }) {
  const t = useT("dashboard");
  const { total_real, answered, reached } = outcomes;
  const enough = total_real >= 10;
  const pct = (v: number | null) => (v === null || !enough ? "—" : `${Math.round(v * 100)}%`);

  // `phrase` is the whole sentence, not a suffix glued onto "{n}/{of}":
  // Vietnamese does not put the count in the same place English does.
  const note = (n: number, phrase: "gotReply" | "gotInterview") =>
    total_real === 0
      ? t("nothingSent")
      : enough
        ? t(phrase, { n, of: total_real })
        : t("tooFewToRate", { n, of: total_real });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("outcomesTitle")}</CardTitle>
        <span className="text-xs text-ink-muted">
          {total_real === 1 ? t("outcomesMetaOne") : t("outcomesMeta", { n: total_real })}
        </span>
      </CardHeader>
      <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          label={t("answered")}
          value={pct(outcomes.reply_rate)}
          icon={<MessageSquare size={16} />}
          note={note(answered, "gotReply")}
        />
        <StatCard
          label={t("interviews")}
          value={pct(outcomes.interview_rate)}
          icon={<Sparkles size={16} />}
          note={note(reached.interview, "gotInterview")}
        />
        <StatCard
          label={t("offers")}
          value={reached.offer}
          accent={reached.offer > 0}
          icon={<Target size={16} />}
          note={
            reached.interview === 0
              ? t("noInterviewsYet")
              : reached.interview === 1
                ? t("fromInterviewsOne")
                : t("fromInterviews", { n: reached.interview })
          }
        />
      </CardBody>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-9 w-52" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-card" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <Skeleton className="h-64 rounded-card lg:col-span-3" />
        <Skeleton className="h-64 rounded-card lg:col-span-2" />
      </div>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  const t = useT("dashboard");
  return (
    <Card>
      <CardBody className="space-y-1">
        <p className="font-medium text-critical">{t("backendDown")}</p>
        {/* The backend's own message, in whatever language it was raised in. */}
        <p className="text-sm text-ink-muted">{message}</p>
        <p className="text-sm text-ink-muted">
          {t("backendHint")}{" "}
          <code className="font-mono text-ink">python -m jobpilot.cli serve</code>.
        </p>
      </CardBody>
    </Card>
  );
}
