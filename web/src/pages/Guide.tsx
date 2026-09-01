import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Globe,
  Mail,
  Shield,
  User,
} from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useT } from "@/i18n";
import { STATUS_ACTOR, FUNNEL_STEPS, useStatuses } from "@/lib/statuses";
import { StatusPill } from "@/components/StatusPill";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { JobStatus } from "@/types";

/**
 * Guide — what the nine statuses mean and how a job travels between them.
 *
 * Written against live counts rather than as a static wall of text: the point
 * of reading this page is usually "why is nothing happening?", and the answer
 * is almost always a number sitting in a column that is waiting on you.
 */
export function Guide({ version }: { version: number }) {
  const t = useT("guide");
  const statuses = useStatuses();
  const { data: stats } = useApi(() => api.stats(), [version]);
  const { data: apply } = useApi(() => api.applySettings(), [version]);
  const count = (s: JobStatus) => stats?.by_status?.[s] ?? 0;

  const waiting = (["DISCOVERED", "SHORTLISTED", "REVIEW", "APPROVED"] as JobStatus[])
    .map((s) => ({ status: s, n: count(s) }))
    .filter((x) => x.n > 0);

  return (
    <div className="animate-fade-up space-y-5">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="mt-0.5 text-sm text-ink-muted">{t("subtitle")}</p>
      </div>

      {waiting.length > 0 && (
        <Card className="flex flex-wrap items-center gap-x-3 gap-y-2 border-accent/40 bg-accent/8 px-4 py-3 text-sm">
          <User size={15} className="shrink-0 text-accent" />
          <span className="font-medium">{t("waitingOnYou")}</span>
          {waiting.map(({ status, n }) => (
            <Link key={status} to={`/jobs?status=${status}`} className="hover:opacity-80">
              <StatusPill status={status} /> <span className="tabular-nums">×{n}</span>
            </Link>
          ))}
        </Card>
      )}

      {/* The funnel, in order */}
      <Card>
        <CardHeader>
          <CardTitle>{t("funnelTitle")}</CardTitle>
          <span className="text-[11px] text-ink-muted">{t("funnelHint")}</span>
        </CardHeader>
        <CardBody className="pt-4">
          <ol className="flex flex-col">
            {FUNNEL_STEPS.map((status, i) => (
              <Step
                key={status}
                status={status}
                n={count(status)}
                last={i === FUNNEL_STEPS.length - 1}
              />
            ))}
          </ol>

          <div className="mt-5 border-t pt-4">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-ink-muted">
              {t("exits")}
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              {(["SKIPPED", "FAILED"] as JobStatus[]).map((status) => (
                <div key={status} className="rounded-lg border p-3">
                  <div className="flex items-center gap-2">
                    <StatusPill status={status} />
                    <span className="font-mono text-[11px] tabular-nums text-ink-muted">
                      {count(status)}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink/90">
                    {statuses.info(status).meaning}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* The two decisions that actually cost something */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("shortlistTitle")}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2.5 pt-3 text-sm leading-relaxed text-ink/90">
            <p>{t("shortlistP1")}</p>
            <p>
              <span className="font-medium">{t("shortlistLead")}</span> {t("shortlistP2")}
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Shield size={15} className="mr-1.5 inline text-accent" />
              {t("agentTitle")}
            </CardTitle>
          </CardHeader>
          <CardBody className="space-y-2.5 pt-3 text-sm leading-relaxed text-ink/90">
            {/* The emphasis sits on the whole first sentence rather than on the
                words "by index" mid-clause: a bold span inside a sentence would
                force the two languages to share English word order. */}
            <p>
              <span className="font-medium">{t("agentLead")}</span> {t("agentP1")}
            </p>
            <p>{t("agentP2")}</p>
          </CardBody>
        </Card>
      </div>

      {/* Apply channels — the part with outside-world consequences */}
      <Card>
        <CardHeader>
          <CardTitle>{t("channelsTitle")}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3 pt-3">
          <Channel
            icon={Mail}
            name="email"
            tone={apply?.email_enabled && !apply?.email_dry_run ? "live" : "held"}
            status={
              apply
                ? apply.email_blocker
                  ? // The blocker sentence is composed by the backend and shown
                    // as-is; only the "Held:" framing is ours to translate.
                    t("emailHeld", { reason: apply.email_blocker })
                  : t("emailLive")
                : "…"
            }
          >
            {t("emailLead")}{" "}
            <code className="rounded bg-surface-2 px-1 text-[12px]">enabled</code>,{" "}
            <code className="rounded bg-surface-2 px-1 text-[12px]">dry_run</code>,{" "}
            <code className="rounded bg-surface-2 px-1 text-[12px]">test_recipient</code>{" "}
            {t("emailGates")} <StatusPill status="APPROVED" className="align-middle" />.
          </Channel>

          <Channel icon={Globe} name="portal" tone="held" status={t("portalStatus")}>
            {t("portalBody")} <span className="font-medium">{t("portalConfirm")}</span>.
          </Channel>

          <Channel icon={ArrowRight} name="external" tone="held" status={t("externalStatus")}>
            {t("externalBody")}
          </Channel>
        </CardBody>
      </Card>

      {/* LinkedIn caveat — the one that surprises people */}
      <Card className="border-accent/30">
        <CardBody className="flex items-start gap-3 py-4 text-sm leading-relaxed">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-accent" />
          <div className="space-y-2">
            <p>
              <span className="font-medium">{t("linkedinLead")}</span> {t("linkedinBody")}
            </p>
            <p className="text-ink-muted">{t("linkedinHint")}</p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

type Actor = (typeof STATUS_ACTOR)[JobStatus];

const ACTOR_ICON: Record<Actor, typeof User> = { you: User, agent: Bot, done: CheckCircle2 };
// The three actor names are shared with the rest of the app, so they live in
// the `labels` namespace rather than being spelled out again here.
const ACTOR_KEY = { you: "actor_you", agent: "actor_agent", done: "actor_done" } as const;

function Step({ status, n, last }: { status: JobStatus; n: number; last: boolean }) {
  const tLabel = useT("labels");
  const info = useStatuses().info(status);
  const actor = STATUS_ACTOR[status];
  const Icon = ACTOR_ICON[actor];
  return (
    <li className="flex gap-3">
      {/* Rail: the dot marks the step, the line carries you to the next one. */}
      <div className="flex flex-col items-center">
        {/* Filled = your move, hollow = the agent's. Both must read clearly,
            or the rail looks broken where the agent is working. */}
        <span
          className={cn(
            "mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border-2",
            actor === "you" ? "border-accent bg-accent" : "border-ink-muted/60 bg-surface",
          )}
        />
        {!last && <span className="my-1 w-px flex-1 bg-ink-muted/30" />}
      </div>

      <div className={cn("min-w-0 flex-1", last ? "pb-0" : "pb-5")}>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={status} />
          <span className="font-mono text-[11px] tabular-nums text-ink-muted">{n}</span>
          <span
            className={cn(
              "inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide",
              actor === "you" ? "text-accent" : "text-ink-muted",
            )}
          >
            <Icon size={12} /> {tLabel(ACTOR_KEY[actor])}
          </span>
        </div>
        <p className="mt-1.5 text-sm leading-relaxed text-ink/90">{info.meaning}</p>
        <p className="mt-0.5 text-sm leading-relaxed text-ink-muted">{info.next}</p>
      </div>
    </li>
  );
}

function Channel({
  icon: Icon,
  name,
  status,
  tone,
  children,
}: {
  icon: typeof Mail;
  name: string;
  status: string;
  tone: "live" | "held";
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Icon size={15} className={tone === "live" ? "text-good" : "text-ink-muted"} />
        <span className="font-mono text-sm font-medium">{name}</span>
        <span
          className={cn(
            "rounded-md border px-1.5 py-0.5 text-[11px]",
            tone === "live"
              ? "border-good/40 bg-good/10 text-good"
              : "border-ink/15 text-ink-muted",
          )}
        >
          {status}
        </span>
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-ink/90">{children}</p>
    </div>
  );
}
