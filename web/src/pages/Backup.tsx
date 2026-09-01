import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Cloud,
  CloudOff,
  Database,
  FileJson,
  HardDrive,
  Loader2,
  Play,
  ShieldCheck,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { isActive, useTask } from "@/hooks/useTask";
import { Button, Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/components/ui";
import { TaskProgress } from "@/components/TaskProgress";
import { useT } from "@/i18n";
import { useFormat } from "@/lib/format";
import type { BackupFile } from "@/types";

/**
 * Why the banner holds a key instead of a sentence: two of the three failures
 * are our own copy and must follow the language switch, while `task.error` is a
 * backend log line that must not be translated. Keeping both shapes in one
 * state lets the render decide which is which.
 */
type Failure = { key: "alreadyRunning" | "startFailed" | "taskFailed" } | { raw: string };

/**
 * Backup (deploy/). Shows what exists, runs a new one, and — the part people
 * skip — shows how to restore it.
 *
 * There is no delete button on purpose. The only deletion here is the retention
 * pass inside the backup job, which is bounded; a button that removes backups is
 * a button that removes the thing kept for the day everything else broke, and
 * this page opens on a phone.
 */
export function Backup({ version }: { version: number }) {
  const t = useT("backup");
  const fmt = useFormat();
  const { data, loading, error, refetch } = useApi(() => api.backups(), [version]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [failed, setFailed] = useState<Failure | null>(null);
  // useRef, not state: two clicks in one tick both read a stale `false` and
  // queue two backups racing on the same directory (web/src/CLAUDE.md).
  const busy = useRef(false);

  const task = useTask(taskId, version);

  // The list only changes once the task lands, so refetch then rather than
  // polling the directory alongside it.
  const landed = useRef<string | null>(null);
  useEffect(() => {
    if (!task || isActive(task) || landed.current === task.id) return;
    landed.current = task.id;
    busy.current = false;
    if (task.status === "failed")
      setFailed(task.error ? { raw: task.error } : { key: "taskFailed" });
    else refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task]);

  const start = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setFailed(null);
    try {
      setTaskId((await api.startBackup()).id);
    } catch (e) {
      busy.current = false;
      // 409 means one is already running — not an error worth a red banner.
      setFailed({
        key: e instanceof ApiError && e.status === 409 ? "alreadyRunning" : "startFailed",
      });
    }
  }, []);

  if (loading && !data) return <Skeleton className="h-64 rounded-card" />;
  if (error)
    return (
      <Card className="p-6 text-sm">
        <span className="font-medium text-critical">{t("dirUnreadable")}</span> {error}
      </Card>
    );
  if (!data) return null;

  const dumps = data.items.filter((f) => f.kind === "database");
  const running = Boolean(task && isActive(task));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex items-center justify-between gap-4">
          <CardTitle>{t("title")}</CardTitle>
          <Button onClick={start} disabled={running}>
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? t("backingUp") : t("backUpNow")}
          </Button>
        </CardHeader>
        <CardBody className="space-y-4">
          {running && task && <TaskProgress task={task} />}
          {failed && (
            <p className="flex items-start gap-2 rounded-lg border border-critical/40 bg-critical/8 px-3 py-2 text-xs text-critical">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{"raw" in failed ? failed.raw : t(failed.key)}</span>
            </p>
          )}

          <Health dumps={dumps.length} newest={dumps[0]} remote={data.remote} />

          <div className="grid gap-3 sm:grid-cols-3">
            <Stat
              label={t("statBackups")}
              value={t("filesCount", { count: data.items.length })}
              icon={HardDrive}
            />
            <Stat label={t("statSize")} value={humanSize(data.total_bytes)} icon={Database} />
            <Stat
              label={t("statRemote")}
              value={data.remote || t("remoteNone")}
              icon={data.remote ? Cloud : CloudOff}
              warn={!data.remote}
            />
          </div>

          {/* The retention numbers used to be mono spans inside the sentence.
              They are interpolated now: splitting one sentence into five JSX
              fragments to keep a font is how a translation ends up with the
              clauses in English word order. */}
          <p className="text-xs text-ink-muted">
            {t("retentionLocal", { days: data.keep_days, last: data.keep_last })}
            {data.remote && ` ${t("retentionRemote", { days: data.remote_keep_days })}`}{" "}
            {t("directoryLabel")} <code className="font-mono">{data.directory}</code>
          </p>
        </CardBody>
      </Card>

      {data.restore_hint && (
        <Card>
          <CardHeader>
            <CardTitle>{t("restoreTitle")}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            <p className="text-xs text-ink-muted">{t("restoreBody")}</p>
            <pre className="overflow-x-auto rounded-lg border bg-surface-2 px-3 py-2 font-mono text-[11px]">
              {data.restore_hint}
            </pre>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("runsTitle")}</CardTitle>
        </CardHeader>
        <CardBody>
          {data.runs.length === 0 ? (
            <p className="text-sm text-ink-muted">{t("runsEmpty")}</p>
          ) : (
            <ul className="divide-y text-sm">
              {data.runs.map((r) => (
                <li key={r.id} className="flex items-center gap-3 py-2">
                  {r.ok ? (
                    <ShieldCheck size={14} className="shrink-0 text-good" />
                  ) : (
                    <AlertTriangle size={14} className="shrink-0 text-critical" />
                  )}
                  <span className="shrink-0 text-xs text-ink-muted">
                    {fmt.clockTime(r.started_at)}
                  </span>
                  <span className="truncate text-xs">
                    {r.ok ? (
                      <>
                        {r.mirrored_to
                          ? t("runUploaded", { remote: r.mirrored_to })
                          : t("runLocalOnly")}
                        {r.pruned > 0 && ` · ${t("runPruned", { count: r.pruned })}`}
                      </>
                    ) : (
                      // `r.error` is the backend's own message — a log line, not copy.
                      <span className="text-critical">{r.error ?? t("runFailed")}</span>
                    )}
                  </span>
                  <span className="ml-auto shrink-0 text-xs text-ink-muted">
                    {duration(r.started_at, r.finished_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("filesTitle")}</CardTitle>
        </CardHeader>
        <CardBody>
          {data.items.length === 0 ? (
            <p className="text-sm text-ink-muted">{t("filesEmpty")}</p>
          ) : (
            <ul className="divide-y text-sm">
              {data.items.map((f) => (
                <li key={f.name} className="flex items-center gap-3 py-2">
                  {f.kind === "database" ? (
                    <Database size={14} className="shrink-0 text-ink-muted" />
                  ) : (
                    <FileJson size={14} className="shrink-0 text-ink-muted" />
                  )}
                  <span className="truncate font-mono text-xs">{f.name}</span>
                  <span className="ml-auto shrink-0 text-xs text-ink-muted">
                    {humanSize(f.size)}
                  </span>
                  <span className="w-36 shrink-0 text-right text-xs text-ink-muted">
                    {/* The filename is stamped in local time and this field is
                        UTC; formatting through the locale keeps one instant
                        from reading as two different clock times side by side. */}
                    {fmt.clockTime(f.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

/** The one line worth reading: is there a recent backup, and is a copy off this machine. */
function Health({
  dumps,
  newest,
  remote,
}: {
  dumps: number;
  newest?: BackupFile;
  remote: string;
}) {
  // Hooks before the early returns, not after — `newest` is data-dependent.
  const t = useT("backup");
  const fmt = useFormat();

  if (!newest)
    return (
      <Banner tone="critical" icon={AlertTriangle}>
        {t("healthNone")}
      </Banner>
    );

  const ageHours = (Date.now() - new Date(newest.created_at).getTime()) / 3_600_000;
  // 48h, not 24: the nightly job can be missed once by a laptop that was shut,
  // and StartWhenAvailable catches it up. Two misses is a pattern.
  if (ageHours > 48)
    return (
      <Banner tone="critical" icon={AlertTriangle}>
        {t("healthStale", { days: Math.floor(ageHours / 24) })}
      </Banner>
    );
  if (!remote)
    return (
      <Banner tone="warn" icon={CloudOff}>
        {t("healthNoRemote", {
          // Vietnamese has no plural inflection, so only English needs the fork.
          files: dumps === 1 ? t("dumpCountOne") : t("dumpCount", { count: dumps }),
        })}
      </Banner>
    );
  return (
    <Banner tone="good" icon={ShieldCheck}>
      {t("healthOk", { when: fmt.relativeTime(newest.created_at), remote })}
    </Banner>
  );
}

function Banner({
  tone,
  icon: Icon,
  children,
}: {
  tone: "good" | "warn" | "critical";
  icon: typeof AlertTriangle;
  children: React.ReactNode;
}) {
  const cls = {
    good: "border-good/30 bg-good/5 text-ink-muted",
    warn: "border-accent/40 bg-accent/8 text-ink-muted",
    critical: "border-critical/40 bg-critical/8 text-critical",
  }[tone];
  return (
    <p className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${cls}`}>
      <Icon size={14} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
  warn,
}: {
  label: string;
  value: string;
  icon: typeof Database;
  warn?: boolean;
}) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-ink-muted">
        <Icon size={12} />
        {label}
      </div>
      <div className={`mt-0.5 truncate text-sm font-medium ${warn ? "text-ink-muted" : ""}`}>
        {value}
      </div>
    </div>
  );
}

/** How long a run took. A backup that suddenly takes ten times as long is
 *  usually the upload struggling, and that is worth being able to see. */
function duration(from: string | null, to: string | null): string {
  if (!from || !to) return "";
  const ms = new Date(to).getTime() - new Date(from).getTime();
  if (ms < 1000) return "<1s";
  return ms < 60_000 ? `${Math.round(ms / 1000)}s` : `${Math.round(ms / 60_000)}m`;
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
