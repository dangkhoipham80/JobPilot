import { useRef, useState } from "react";
import { AlertTriangle, Loader2, RotateCcw } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { Button, Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useFormat } from "@/lib/format";
import { useT } from "@/i18n";
import { sourceLabel } from "@/lib/labels";
import type { CrawlRequest, RecentCrawl } from "@/types";

/**
 * Crawl again — the last few distinct setups, one click to repeat each exactly.
 *
 * "Exactly" is the backend's job: `GET /crawl/recent` hands back what
 * `POST /crawl` takes, so this sends the item back unchanged rather than
 * rebuilding a request from what the row displays. `sources: null` stays "every
 * enabled source", `limit: null` stays the configured default.
 */
export function RecentCrawls({
  version,
  busy,
  blocked,
  onCrawl,
}: {
  version: number;
  busy: boolean;
  blocked: boolean;
  onCrawl: (body: CrawlRequest) => Promise<void>;
}) {
  const t = useT("runs");
  const fmt = useFormat();
  const { data: recent } = useApi(() => api.recentCrawls(3), [version]);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<number | null>(null);
  // The guard is a ref, not the state above: two clicks in one tick both read
  // `starting === null` before a re-render (web/src/CLAUDE.md). The state only
  // drives the spinner.
  const inFlight = useRef(false);

  async function again(item: RecentCrawl) {
    if (inFlight.current) return;
    inFlight.current = true;
    setError(null);
    setStarting(item.run_id);
    try {
      await onCrawl({
        query: item.query,
        sources: item.sources ?? undefined,
        limit: item.limit ?? undefined,
        places: item.places ?? undefined,
        work_modes: item.work_modes ?? undefined,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("crawlFailed"));
    } finally {
      inFlight.current = false;
      setStarting(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("recentTitle")}</CardTitle>
        <span className="text-[11px] text-ink-muted">{t("recentHint")}</span>
      </CardHeader>
      <CardBody className="pt-3">
        {!recent?.length ? (
          <p className="text-sm text-ink-muted">{t("recentEmpty")}</p>
        ) : (
          <ul className="flex flex-col divide-y">
            {recent.map((item) => (
              <li key={item.run_id} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap gap-1.5">
                    {item.queries.map((q) => (
                      <span
                        key={q}
                        className="rounded-full border border-accent/40 bg-accent/5 px-2 py-0.5 text-xs"
                      >
                        {q}
                      </span>
                    ))}
                  </div>
                  <p className="mt-1 text-[11px] text-ink-muted">
                    {item.sources ? item.sources.map(sourceLabel).join(", ") : t("allSources")}
                    {" · "}
                    {item.limit ? t("perSite", { count: item.limit }) : t("limitDefaultShort")}
                    {item.inserted != null && ` · ${t("foundNew", { count: item.inserted })}`}
                    {item.started_at && ` · ${fmt.relativeTime(item.started_at)}`}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => again(item)}
                  disabled={busy || blocked || starting !== null}
                >
                  {starting === item.run_id ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <RotateCcw size={14} />
                  )}
                  {t("recrawl")}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {error && (
          <p className="mt-2 flex items-start gap-2 rounded-lg border border-critical/40 bg-critical/5 px-3 py-2 text-sm">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-critical" />
            {error}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
