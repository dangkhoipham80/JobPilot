import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ExternalLink, Loader2, Play, Sparkles, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Select } from "@/components/ui";
import { SourceIcon } from "@/components/SourceIcon";
import { useT } from "@/i18n";
import { sourceHome, sourceLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

/** Keywords per crawl; mirrors `MAX_QUERIES` in `crawler/pipeline.py`. */
export const MAX_KEYWORDS = 8;

/**
 * `"java, spring boot; JAVA"` -> `["java", "spring boot"]` — the same split the
 * backend applies (`pipeline.split_queries`): commas, semicolons and newlines
 * separate searches, spaces stay inside one, duplicates go case-insensitively.
 */
export function splitKeywords(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of text.split(/[,;\n]/)) {
    const q = part.split(/\s+/).filter(Boolean).join(" ");
    if (q && !seen.has(q.toLowerCase())) {
      seen.add(q.toLowerCase());
      out.push(q);
    }
  }
  return out;
}

/**
 * Crawl setup — decide the scope, then run it.
 *
 * A crawl takes minutes and is rate-limited per site, so "Crawl now" with no
 * say in what it does is an expensive way to find out you searched for the
 * wrong thing. Everything chosen here scopes one run: the sources you may crawl
 * at all still live in Settings, and nothing here is written back.
 *
 * The keyword suggestions come from your Master CV rather than a canned list,
 * so a suggested search is one you can actually back up.
 */
export function CrawlSetup({
  version,
  busy,
  blocked,
  onCrawl,
}: {
  version: number;
  busy: boolean;
  /** A crawl is already running — one at a time, or they race the same sites. */
  blocked: boolean;
  onCrawl: (body: { query?: string; sources?: string[]; limit?: number }) => Promise<void>;
}) {
  const t = useT("runs");
  const nav = useT("nav");
  const { data: setup } = useApi(() => api.crawlSetup(), [version]);

  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState<number | "">("");
  const [picked, setPicked] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Only sources that are both switched on *and* actually implemented can be
  // picked. Offering the rest would produce a crawl that does nothing.
  const runnable = useMemo(
    () => (setup?.sources ?? []).filter((s) => s.enabled && s.ready).map((s) => s.key),
    [setup],
  );
  const off = (setup?.sources ?? []).filter((s) => !s.enabled);
  const notReady = (setup?.sources ?? []).filter((s) => s.enabled && !s.ready);

  // Default to everything enabled, but only once settings have arrived —
  // otherwise the first render would "select" an empty set.
  useEffect(() => {
    if (picked === null && runnable.length) setPicked(runnable);
  }, [runnable, picked]);

  const selected = picked ?? [];
  const suggestions = [...(setup?.roles ?? []), ...(setup?.tech ?? [])];
  const keywords = splitKeywords(query);
  const tooMany = keywords.length > MAX_KEYWORDS;

  function toggleSource(key: string) {
    setPicked((prev) => {
      const cur = prev ?? runnable;
      return cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key];
    });
  }

  // A suggestion is a keyword of its own, not words glued onto the current
  // one: "java spring boot" is one long search that some boards answer with
  // nothing, while "java, spring boot" is two short ones.
  function toggleWord(term: string) {
    const cur = splitKeywords(query);
    const has = cur.some((k) => k.toLowerCase() === term.toLowerCase());
    const next = has ? cur.filter((k) => k.toLowerCase() !== term.toLowerCase()) : [...cur, term];
    setQuery(next.join(", "));
  }

  async function start() {
    setError(null);
    try {
      await onCrawl({
        query: keywords.length ? keywords.join(", ") : undefined,
        // Sending every source is the same as sending none, and an empty body
        // reads better in the run label ("all sources").
        sources: selected.length && selected.length < runnable.length ? selected : undefined,
        limit: typeof limit === "number" ? limit : undefined,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("crawlFailed"));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("setupTitle")}</CardTitle>
        <span className="text-[11px] text-ink-muted">{t("setupScope")}</span>
      </CardHeader>
      <CardBody className="space-y-4 pt-4">
        {/* Sources */}
        <div>
          <Label>{t("sources")}</Label>
          <div className="flex flex-wrap gap-2">
            {runnable.map((key) => {
              const on = selected.includes(key);
              const home = sourceHome(key);
              return (
                // The chip is a toggle *and* a way out to the board, so the
                // border lives on the wrapper: an <a> nested inside a <button>
                // is invalid HTML, and browsers resolve it by dropping one.
                <span
                  key={key}
                  className={cn(
                    "inline-flex items-center rounded-lg border transition-colors",
                    on ? "border-accent bg-accent/10 text-ink" : "text-ink-muted",
                  )}
                >
                  <button
                    onClick={() => toggleSource(key)}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-l-lg py-1.5 pl-2.5 pr-2 text-sm font-medium transition-colors",
                      !on && "hover:bg-surface-2",
                    )}
                    aria-pressed={on}
                  >
                    {/* Colour still carries the selection — the logo says which
                        board, the tint says whether this run includes it. */}
                    <SourceIcon
                      source={key}
                      className={cn("transition-opacity", !on && "opacity-50 grayscale")}
                    />
                    {sourceLabel(key)}
                  </button>
                  {home && (
                    <a
                      href={home}
                      target="_blank"
                      rel="noreferrer"
                      title={home.replace(/^https?:\/\//, "")}
                      className="rounded-r-lg py-1.5 pl-1 pr-2 text-ink-muted transition-colors hover:text-accent"
                    >
                      <ExternalLink size={12} />
                    </a>
                  )}
                </span>
              );
            })}
            {!runnable.length && (
              <p className="text-sm text-ink-muted">
                {t("noSourceReady")}{" "}
                <Link to="/settings" className="text-accent hover:underline">
                  {nav("settings")}
                </Link>
                .
              </p>
            )}
          </div>
          {notReady.length > 0 && (
            <p className="mt-1.5 flex items-center gap-1.5 text-[11px] text-ink-muted">
              <AlertTriangle size={11} className="text-accent" />
              {t("notReady", { names: notReady.map((s) => sourceLabel(s.key)).join(", ") })}
            </p>
          )}
          {off.length > 0 && (
            <p className="mt-1 text-[11px] text-ink-muted">
              {t("off", { names: off.map((s) => sourceLabel(s.key)).join(", ") })}
            </p>
          )}
        </div>

        {/* Query + CV-derived suggestions */}
        <div>
          <Label>{t("searchFor")}</Label>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              setup?.default_query
                ? t("queryFromSettings", { query: setup.default_query })
                : t("queryPlaceholder")
            }
          />
          <p className="mt-1.5 text-[11px] text-ink-muted">
            {keywords.length > 1 ? t("keywordCount", { count: keywords.length }) : t("queryHint")}
          </p>
          {tooMany && (
            <p className="mt-1 text-[11px] text-critical">
              {t("tooManyKeywords", { max: MAX_KEYWORDS })}
            </p>
          )}
          {suggestions.length > 0 && (
            <>
              <p className="mb-1.5 mt-2.5 flex items-center gap-1.5 text-[11px] text-ink-muted">
                <Sparkles size={12} className="text-accent" />
                {t("fromCv")}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((term) => {
                  const on = keywords.some((k) => k.toLowerCase() === term.toLowerCase());
                  return (
                    <button
                      key={term}
                      onClick={() => toggleWord(term)}
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-xs transition-colors",
                        on
                          ? "border-accent bg-accent/10 text-accent"
                          : "text-ink-muted hover:bg-surface-2 hover:text-ink",
                      )}
                    >
                      {on ? <X size={10} className="mr-0.5 inline" /> : null}
                      {term}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          {setup && suggestions.length === 0 && (
            <p className="mt-2 text-[11px] text-ink-muted">
              {t("noSuggestions")}{" "}
              <Link to="/cv" className="text-accent hover:underline">
                {nav("cv")}
              </Link>{" "}
              {t("noSuggestionsEnd")}
            </p>
          )}
        </div>

        {/* Depth + go */}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label>{t("jobsPerSite")}</Label>
            <Select
              value={String(limit)}
              onChange={(e) => setLimit(e.target.value ? Number(e.target.value) : "")}
              className="w-44"
            >
              <option value="">{t("limitDefault", { count: setup?.jobs_per_site ?? "—" })}</option>
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n} {n >= 50 ? t("limitSlow") : ""}
                </option>
              ))}
            </Select>
          </div>

          <Button
            onClick={start}
            disabled={busy || blocked || !selected.length || tooMany}
            className="ml-auto"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {t("crawlNow")}
          </Button>
        </div>

        {blocked && <p className="text-xs text-ink-muted">{t("crawlBlocked")}</p>}
        {error && (
          <p className="flex items-start gap-2 rounded-lg border border-critical/40 bg-critical/5 px-3 py-2 text-sm">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-critical" />
            {error}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted">{children}</p>
  );
}
