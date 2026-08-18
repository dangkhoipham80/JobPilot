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
import type { BackupFile } from "@/types";

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
  const { data, loading, error, refetch } = useApi(() => api.backups(), [version]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
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
    if (task.status === "failed") setFailed(task.error ?? "backup failed");
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
      setFailed(e instanceof ApiError && e.status === 409 ? "A backup is already running." : "Could not start the backup.");
    }
  }, []);

  if (loading && !data) return <Skeleton className="h-64 rounded-card" />;
  if (error)
    return (
      <Card className="p-6 text-sm">
        <span className="font-medium text-critical">Couldn't read the backup directory.</span> {error}
      </Card>
    );
  if (!data) return null;

  const dumps = data.items.filter((f) => f.kind === "database");
  const running = Boolean(task && isActive(task));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex items-center justify-between gap-4">
          <CardTitle>Backup</CardTitle>
          <Button onClick={start} disabled={running}>
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? "Backing up..." : "Back up now"}
          </Button>
        </CardHeader>
        <CardBody className="space-y-4">
          {running && task && <TaskProgress task={task} />}
          {failed && (
            <p className="flex items-start gap-2 rounded-lg border border-critical/40 bg-critical/8 px-3 py-2 text-xs text-critical">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{failed}</span>
            </p>
          )}

          <Health dumps={dumps.length} newest={dumps[0]} remote={data.remote} />

          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Backups" value={`${data.items.length} files`} icon={HardDrive} />
            <Stat label="Total size" value={humanSize(data.total_bytes)} icon={Database} />
            <Stat
              label="Off this machine"
              value={data.remote || "not configured"}
              icon={data.remote ? Cloud : CloudOff}
              warn={!data.remote}
            />
          </div>

          <p className="text-xs text-ink-muted">
            Kept <span className="font-mono text-ink">{data.keep_days}d</span> here
            {data.remote && (
              <>
                {" "}
                and <span className="font-mono text-ink">{data.remote_keep_days}d</span> on the
                remote — longer on purpose, so a bug in local pruning can't delete the surviving
                copies too
              </>
            )}
            . Directory: <code className="font-mono">{data.directory}</code>
          </p>
        </CardBody>
      </Card>

      {data.restore_hint && (
        <Card>
          <CardHeader>
            <CardTitle>Restore</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            <p className="text-xs text-ink-muted">
              A backup nobody knows how to restore is a backup nobody has. Run this at least once
              against a scratch database, before you need it.
            </p>
            <pre className="overflow-x-auto rounded-lg border bg-surface-2 px-3 py-2 font-mono text-[11px]">
              {data.restore_hint}
            </pre>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Files</CardTitle>
        </CardHeader>
        <CardBody>
          {data.items.length === 0 ? (
            <p className="text-sm text-ink-muted">
              No backups yet. The scheduled job runs nightly; the button above runs one now.
            </p>
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
                    {new Date(f.created_at).toLocaleString()}
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
  if (!newest)
    return (
      <Banner tone="critical" icon={AlertTriangle}>
        No database backup exists yet. Everything lives on this one machine.
      </Banner>
    );

  const ageHours = (Date.now() - new Date(newest.created_at).getTime()) / 3_600_000;
  // 48h, not 24: the nightly job can be missed once by a laptop that was shut,
  // and StartWhenAvailable catches it up. Two misses is a pattern.
  if (ageHours > 48)
    return (
      <Banner tone="critical" icon={AlertTriangle}>
        Newest backup is {Math.floor(ageHours / 24)} days old — the scheduled job may not be
        running.
      </Banner>
    );
  if (!remote)
    return (
      <Banner tone="warn" icon={CloudOff}>
        {dumps} backup{dumps === 1 ? "" : "s"} here, but none off this machine. A backup on the
        same disk as the data doesn't survive losing the machine — which is the case it's for.
      </Banner>
    );
  return (
    <Banner tone="good" icon={ShieldCheck}>
      Backed up {ageHours < 1 ? "just now" : `${Math.floor(ageHours)}h ago`}, with a copy on{" "}
      {remote}.
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

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
