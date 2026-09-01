import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Check,
  ExternalLink,
  FileText,
  FileWarning,
  Loader2,
  Mail,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useClampPage, usePaging } from "@/hooks/usePaging";
import { FollowUps } from "@/components/FollowUps";
import { OutcomeTracker } from "@/components/OutcomeTracker";
import { InboxReplies } from "@/components/InboxReplies";
import { isActive, useTask } from "@/hooks/useTask";
import { useFormat } from "@/lib/format";
import { useT } from "@/i18n";
import { TaskProgress } from "@/components/TaskProgress";
import { CompactPager, PageSizeSelect, Pagination } from "@/components/Pagination";
import { Badge, Button, Card, CardBody, Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Application, ApplyChannel, ApplySettings } from "@/types";

/**
 * Applications board (PLAN.md §5.6). Columns are what happened, not where the
 * job is in the funnel — "Prepared" exists precisely so a dry run is never read
 * as a send. The gate banner up top says which of the three email safeties are
 * currently open.
 */

// Titles and hints are dictionary keys, resolved at render so they follow the
// language switch — a module-scope string would freeze at first evaluation.
const COLUMNS = [
  {
    key: "dry_run",
    titleKey: "colPrepared",
    hintKey: "colPreparedHint",
    accent: "border-t-ink-muted/40",
  },
  {
    key: "awaiting_user",
    titleKey: "colYourTurn",
    hintKey: "colYourTurnHint",
    accent: "border-t-accent",
  },
  {
    key: "success",
    titleKey: "colSubmitted",
    hintKey: "colSubmittedHint",
    accent: "border-t-good",
  },
  {
    key: "failed",
    titleKey: "colFailed",
    hintKey: "colFailedHint",
    accent: "border-t-critical",
  },
] as const;

/** Channel badges: `email` and `portal` read the same in both languages — that
 *  is what people call them — but `external` needs saying. */
const CHANNEL_KEY = {
  email: "channelEmail",
  portal: "channelPortal",
  external: "channelExternal",
} as const satisfies Record<ApplyChannel, string>;

export function Applications({ version }: { version: number }) {
  const t = useT("applications");
  // Each column owns its own query now, so "reload the board" is a counter the
  // columns depend on rather than one refetch the parent can call. Same shape
  // as the global `version` in App.tsx, one level down.
  const [boardVersion, reloadBoard] = useReducer((n: number) => n + 1, 0);

  // One page size across all four columns. A dropdown inside a quarter-width
  // column, four times over, is more chrome than board.
  const boardPaging = usePaging("applications");

  // A one-row probe, purely for `total`. Whether the board is empty *at all*
  // is a different question from whether one column is, and only the first
  // earns the "approve a CV, then hit Apply" hint.
  const board = useApi(() => api.applications(undefined, { limit: 1 }), [version, boardVersion]);
  const { loading, error } = board;

  const settings = useApi(() => api.applySettings(), []);

  const followupPaging = usePaging("followups");
  const followups = useApi(
    () => api.followups({ limit: followupPaging.size, offset: followupPaging.offset }),
    [version, boardVersion, followupPaging.size, followupPaging.offset],
  );
  useClampPage(followups.data?.total, followupPaging);

  const suggestionPaging = usePaging("inbox-suggestions");
  const suggestions = useApi(
    () => api.inboxSuggestions({ limit: suggestionPaging.size, offset: suggestionPaging.offset }),
    [version, boardVersion, suggestionPaging.size, suggestionPaging.offset],
  );
  useClampPage(suggestions.data?.total, suggestionPaging);

  const inboxSettings = useApi(() => api.inboxSettings(), []);
  const [busy, setBusy] = useState<number | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const task = useTask(taskId, version);

  /** Confirm and report-failure: plain state changes, done when the call returns. */
  const act = useCallback(
    async (app: Application, fn: () => Promise<unknown>) => {
      setBusy(app.id);
      setActionError(null);
      try {
        await fn();
        reloadBoard();
      } catch (e) {
        setActionError(e instanceof ApiError ? e.message : t("requestFailed"));
      } finally {
        setBusy(null);
      }
    },
    [reloadBoard, t],
  );

  /** Re-dispatching is queued, so the card stays busy until the task lands. */
  const retry = useCallback(
    async (app: Application) => {
      setBusy(app.id);
      setActionError(null);
      try {
        setTaskId((await api.applyJob(app.job_id)).id);
      } catch (e) {
        setBusy(null);
        setActionError(e instanceof ApiError ? e.message : t("requestFailed"));
      }
    },
    [t],
  );

  const landed = useRef<string | null>(null);
  useEffect(() => {
    if (!task || isActive(task) || landed.current === task.id) return;
    landed.current = task.id;
    setBusy(null);
    reloadBoard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task]);

  return (
    <div className="animate-fade-up space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-ink-muted">{t("subtitle")}</p>
      </div>

      {settings.data && <GateBanner settings={settings.data} />}
      {task && <TaskProgress task={task} />}
      {actionError && (
        <Card className="flex items-start gap-2 border-critical/40 bg-critical/5 p-3 text-sm">
          <AlertTriangle size={15} className="mt-0.5 shrink-0 text-critical" />
          <span>{actionError}</span>
        </Card>
      )}

      {/* Replies first: what an employer said outranks a reminder to chase
          one, and accepting a suggestion often removes a follow-up below. */}
      <InboxReplies
        items={suggestions.data?.items ?? []}
        settings={inboxSettings.data ?? null}
        onChange={reloadBoard}
        pager={
          <Pagination
            page={suggestionPaging.page}
            size={suggestionPaging.size}
            total={suggestions.data?.total ?? 0}
            onPage={suggestionPaging.setPage}
            onSize={suggestionPaging.setSize}
            noun={t("nounReplies")}
          />
        }
      />

      <FollowUps
        items={followups.data?.items ?? []}
        total={followups.data?.total}
        onChange={reloadBoard}
        pager={
          <Pagination
            page={followupPaging.page}
            size={followupPaging.size}
            total={followups.data?.total ?? 0}
            onPage={followupPaging.setPage}
            onSize={followupPaging.setSize}
            noun={t("nounFollowups")}
          />
        }
      />

      {error ? (
        <Card className="p-6 text-sm">
          <span className="font-medium text-critical">{t("loadFailed")}</span> {error}
        </Card>
      ) : loading && !board.data ? (
        <div className="grid gap-3 lg:grid-cols-4">
          {COLUMNS.map((c) => (
            <Skeleton key={c.key} className="h-48 rounded-card" />
          ))}
        </div>
      ) : board.data?.total === 0 ? (
        <Card>
          <CardBody className="py-16 text-center text-sm text-ink-muted">{t("empty")}</CardBody>
        </Card>
      ) : (
        <>
          <div className="flex justify-end">
            <PageSizeSelect
              size={boardPaging.size}
              onSize={boardPaging.setSize}
              label={t("cardsPerColumn")}
            />
          </div>
          <div className="grid gap-3 lg:grid-cols-4">
            {COLUMNS.map((col) => (
              <BoardColumn
                key={col.key}
                col={col}
                size={boardPaging.size}
                reloadKey={`${version}:${boardVersion}`}
                busy={busy}
                onConfirm={(app) => act(app, () => api.confirmSubmit(app.job_id))}
                onFail={(app) => {
                  const reason = window.prompt(t("failPrompt")) ?? "";
                  if (reason.trim()) act(app, () => api.reportFailure(app.job_id, reason));
                }}
                onRetry={retry}
                onOutcome={reloadBoard}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * One column of the board, with its own window onto its own stage.
 *
 * The board used to fetch every application and split them up in the browser,
 * which meant the page size was shared across all four stages: a hundred
 * rejections would push the two offers out of the response entirely, and the
 * "Offers" column would sit there empty looking like a fact about your job
 * hunt. Per-column queries make the count in each header the real total for
 * that stage rather than however many of it survived a shared window.
 */
function BoardColumn({
  col,
  size,
  reloadKey,
  busy,
  onConfirm,
  onFail,
  onRetry,
  onOutcome,
}: {
  col: (typeof COLUMNS)[number];
  size: number;
  reloadKey: string;
  busy: number | null;
  onConfirm: (app: Application) => void;
  onFail: (app: Application) => void;
  onRetry: (app: Application) => void;
  onOutcome: () => void;
}) {
  const t = useT("applications");
  const [page, setPage] = useState(0);

  // The size lives in the parent (one picker for all four columns) but the page
  // lives here, so the parent's setSize cannot reset it — and page 2 of 10-row
  // pages is nowhere in 25-row pages. Without this, widening the board from 10
  // to 25 while on page 2 shows rows 26–50: real rows, wrong window, and
  // nothing on screen says so. `useClampPage` does not catch it either, because
  // the page is still inside the (now shorter) range.
  useEffect(() => setPage(0), [size]);

  const { data } = useApi(
    () => api.applications(col.key, { limit: size, offset: page * size }),
    [col.key, size, page, reloadKey],
  );
  useClampPage(data?.total, { page, size, setPage });

  const items = data?.items ?? [];
  return (
    <section className="flex flex-col gap-2">
      <header className={cn("rounded-t-card border-t-2 px-1 pt-2", col.accent)}>
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-sm font-semibold">{t(col.titleKey)}</h2>
          <span className="font-mono text-[11px] text-ink-muted">{data?.total ?? "\u2013"}</span>
        </div>
        <p className="text-[11px] leading-tight text-ink-muted">{t(col.hintKey)}</p>
      </header>
      <div className="flex flex-col gap-2">
        {items.map((app) => (
          <ApplicationCard
            key={app.id}
            app={app}
            busy={busy === app.id}
            onConfirm={() => onConfirm(app)}
            onFail={() => onFail(app)}
            onRetry={() => onRetry(app)}
            onOutcome={onOutcome}
          />
        ))}
      </div>
      <CompactPager page={page} size={size} total={data?.total ?? 0} onPage={setPage} />
    </section>
  );
}

function GateBanner({ settings }: { settings: ApplySettings }) {
  const t = useT("applications");
  const sending = settings.email_enabled && !settings.email_dry_run;
  const redirected = sending && !!settings.email_test_recipient;

  return (
    <Card
      className={cn(
        "border-l-2",
        sending && !redirected ? "border-l-critical" : "border-l-good",
      )}
    >
      <CardBody className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-sm">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <ShieldCheck size={15} className={sending && !redirected ? "text-critical" : "text-good"} />
          {t("gateTitle")}
        </span>
        {!settings.email_enabled ? (
          // `email_blocker` is the backend's own sentence about why the gate is
          // shut; only the frame around it is ours to translate.
          <span className="text-ink-muted">
            {t("gateOff", { reason: settings.email_blocker || t("gateOffReason") })}
          </span>
        ) : settings.email_dry_run ? (
          <span className="text-ink-muted">{t("gateDryRun")}</span>
        ) : redirected ? (
          <span className="text-ink-muted">
            {t("gateRedirectedPre")}{" "}
            <span className="font-mono text-ink">{settings.email_test_recipient}</span>{" "}
            {t("gateRedirectedPost")}
          </span>
        ) : (
          <span className="font-medium text-critical">
            {t("gateLive", { from: settings.email_from })}
          </span>
        )}
        <span className="ml-auto text-xs text-ink-muted">{t("gateConfig")}</span>
      </CardBody>
    </Card>
  );
}

function ApplicationCard({
  app,
  busy,
  onConfirm,
  onFail,
  onRetry,
  onOutcome,
}: {
  app: Application;
  busy: boolean;
  onConfirm: () => void;
  onFail: () => void;
  onRetry: () => void;
  onOutcome: () => void;
}) {
  const t = useT("applications");
  const tc = useT("common");
  const fmt = useFormat();
  const email = app.meta.email;
  const handoff = app.meta.handoff;
  const letter = app.meta.letter;

  return (
    <Card className="p-3">
      <Link
        to={`/jobs/${encodeURIComponent(app.job_id)}/review`}
        className="block font-medium leading-tight hover:text-accent"
      >
        {app.job_title}
      </Link>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
        <span>{app.company}</span>
        {app.channel && (
          <Badge className="border-ink/10 text-ink-muted">
            {app.channel === "email" ? <Mail size={10} /> : <ExternalLink size={10} />}
            {t(CHANNEL_KEY[app.channel])}
          </Badge>
        )}
        <span>{fmt.relativeTime(app.submitted_at ?? app.created_at)}</span>
      </div>

      {/* Only when there is an address to show: an empty arrow reads as a
          broken card rather than as "this row predates the field". */}
      {email?.to && (
        <p className="mt-2 rounded-md border bg-surface-2/60 px-2 py-1 text-[11px] leading-relaxed text-ink-muted">
          {email.redirected ? (
            <>
              → <span className="font-mono text-ink">{email.to}</span>{" "}
              <span className="opacity-70">
                {t("testRedirect", { to: email.intended_to ?? "" })}
              </span>
            </>
          ) : (
            <>
              → <span className="font-mono text-ink">{email.to}</span>
            </>
          )}
          {/* Optional chaining because `meta` is JSONB written by whichever
              version of the dispatcher ran. One row missing a key should not
              blank the entire board, which is what an unguarded read does. */}
          {email.attachments?.length ? <> · {email.attachments.join(", ")}</> : null}
        </p>
      )}

      {/* A letter with no PDF is not a failed application, so this is a note,
          not an error — but it says why, because an unexplained missing file
          reads as "nothing was written". */}
      {letter?.pdf_error && (
        <p className="mt-2 rounded-md border bg-surface-2/60 px-2 py-1 text-[11px] leading-relaxed text-ink-muted">
          <FileWarning size={11} className="mr-1 inline align-[-2px]" />
          {t("letterPdfFailed")}{" "}
          {/* The LaTeX tail is a build log, not copy — it stays as emitted. */}
          <span className="opacity-70">{letter.pdf_error.slice(-120)}</span>
        </p>
      )}

      {app.error_msg && (
        <p className="mt-2 rounded-md border border-critical/30 bg-critical/5 px-2 py-1 text-[11px] leading-relaxed text-critical">
          {app.error_msg}
        </p>
      )}

      {handoff && (
        <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">{handoff.note}</p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {app.result === "awaiting_user" && (
          <>
            {app.apply_target && (
              <a
                href={app.apply_target}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[12px] font-medium text-ink-muted hover:bg-surface-2 hover:text-ink"
              >
                <ExternalLink size={12} /> {t("openForm")}
              </a>
            )}
            <Button size="sm" className="h-7 px-2 text-[12px]" onClick={onConfirm} disabled={busy}>
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}{" "}
              {t("iSentIt")}
            </Button>
            <Button
              size="sm"
              variant="danger"
              className="h-7 px-2 text-[12px]"
              onClick={onFail}
              disabled={busy}
            >
              <X size={12} /> {t("markFailed")}
            </Button>
          </>
        )}
        {(app.result === "failed" || app.result === "dry_run") && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 px-2 text-[12px]"
            onClick={onRetry}
            disabled={busy}
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {app.result === "dry_run" ? t("runAgain") : tc("retry")}
          </Button>
        )}
        <a
          href={`/jobs/${encodeURIComponent(app.job_id)}/review`}
          className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[12px] text-ink-muted hover:bg-surface-2 hover:text-ink"
        >
          <FileText size={12} /> CV
        </a>
      </div>

      {/* Only applications that really went out can carry an outcome — the API
          refuses the rest with a 409, and showing the prompt on a dry run would
          be inviting a click that can't work. */}
      {(app.result === "success" || app.result === "awaiting_user") && (
        <OutcomeTracker app={app} onChange={onOutcome} />
      )}
    </Card>
  );
}
