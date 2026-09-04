import type {
  CrawlRequest,
  CrawlSetupInfo,
  Application,
  ApplicationEvent,
  InboxSettings,
  InboxSuggestion,
  ApplySettings,
  BackupStatus,
  OutcomeType,
  CvCompileResult,
  CvDocument,
  CvDocumentResponse,
  CvTemplate,
  CvTex,
  CvVersion,
  CvVersionDetail,
  CvVersionDiff,
  FitReport,
  JdIntake,
  Job,
  JobDetail,
  JobInput,
  JobsQuery,
  ReviewData,
  RunRecord,
  Settings,
  LlmStats,
  MarketReport,
  OutcomeAnalytics,
  Page,
  PageQuery,
  Stats,
  Task,
} from "@/types";

/* Relative by default, so the bundle works at whatever host serves it — the
   FastAPI process in deployment, the Vite dev server (which proxies /api) in
   development. Hardcoding 127.0.0.1 made the build wrong everywhere except the
   machine that produced it. Override only to point a dev bundle at a backend on
   another host. */
const BASE = (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "");

/* Baked into the bundle at build time by Vite, and therefore readable by anyone
   who can load the page. It is not what keeps strangers out — Tailscale is.
   See jobpilot/api/security.py. */
const TOKEN = import.meta.env.VITE_API_TOKEN ?? "changeme";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: { "X-API-Token": TOKEN, "Content-Type": "application/json", ...opts.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (null as T) : ((await res.json()) as T);
}

function qs(params: Record<string, unknown>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

const jobPath = (id: string) => `/jobs/${id.split("/").map(encodeURIComponent).join("/")}`;
// "master" or a job id — job ids contain ':' and must survive as one segment.
const cvPath = (scope: string) => `/cv/${encodeURIComponent(scope)}`;

export const api = {
  stats: () => req<Stats>("/stats"),
  /* Which source is worth crawling again (PLAN.md §9.1 slot 20). Its own
     request rather than folded into /stats: it scans the whole event log, and
     most dashboard polls never render it. */
  outcomeAnalytics: () => req<OutcomeAnalytics>("/stats/outcomes"),
  market: () => req<MarketReport>("/analytics/market"),
  llmStats: (live = false) => req<LlmStats>(`/stats/llm${live ? "?live=true" : ""}`),
  jobs: (query: JobsQuery = {}) => req<Page<Job>>(`/jobs${qs(query as Record<string, unknown>)}`),
  job: (id: string) => req<JobDetail>(jobPath(id)),
  /* Manual entry — the way in for postings no crawler may fetch, LinkedIn above
     all (its robots.txt disallows automated access to job pages). */
  createJob: (body: JobInput) =>
    req<JobDetail>("/jobs", { method: "POST", body: JSON.stringify(body) }),
  patchJob: (id: string, patch: Partial<JobInput>) =>
    req<JobDetail>(jobPath(id), { method: "PATCH", body: JSON.stringify(patch) }),
  shortlist: (id: string) => req<JobDetail>(`${jobPath(id)}/shortlist`, { method: "POST" }),
  skip: (id: string) => req<JobDetail>(`${jobPath(id)}/skip`, { method: "POST" }),

  /* Read a pasted posting into form fields. Saves nothing — the answer goes
     into the Add-job form for the user to correct, and `createJob` is still
     what creates the row. Not queued (unlike tailor/apply): one model call with
     someone waiting at a form, and the queue has a single worker that a running
     crawl would park this behind for minutes. */
  readJd: (text: string, url = "") =>
    req<JdIntake>("/jobs/intake", { method: "POST", body: JSON.stringify({ text, url }) }),
  /* Score a saved job against the Master CV. Advisory: it never edits the CV
     and never feeds the tailor, so it is safe to run on anything, at any stage.
     The result is stored on the job and comes back on `job()` afterwards. */
  assessFit: (id: string) => req<FitReport>(`${jobPath(id)}/fit`, { method: "POST" }),

  /* CV Studio (Phase 4.5) */
  cv: (scope: string) => req<CvDocumentResponse>(cvPath(scope)),
  // Whatever templates ship in the image — a fixed, tiny set, so no paging.
  cvTemplates: () => req<{ templates: CvTemplate[] }>("/cv/templates"),
  /* Change the Master CV from a sentence. Deliberately not named `editCv` —
     that already means "re-tailor this job's CV with a reviewer note", and the
     two do very different things to different documents. Queued like tailoring,
     so follow the task with `useTask`; a new version appends when it lands. */
  editMasterCv: (instruction: string) =>
    req<Task>("/cv/master/edit", {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),
  saveCv: (scope: string, document: CvDocument) =>
    req<CvDocumentResponse>(cvPath(scope), { method: "PUT", body: JSON.stringify(document) }),
  compileCv: (scope: string) => req<CvCompileResult>(`${cvPath(scope)}/compile`, { method: "POST" }),
  cvVersions: (scope: string, page: PageQuery = {}) =>
    req<Page<CvVersion>>(`${cvPath(scope)}/versions${qs(page as Record<string, unknown>)}`),
  cvVersion: (scope: string, version: number) =>
    req<CvVersionDetail>(`${cvPath(scope)}/versions/${version}`),
  cvDiff: (scope: string, base: number, target: number) =>
    req<CvVersionDiff>(`${cvPath(scope)}/diff?base=${base}&target=${target}`),
  rollbackCv: (scope: string, version: number) =>
    req<CvDocumentResponse>(`${cvPath(scope)}/rollback/${version}`, { method: "POST" }),

  /* Raw LaTeX. `saveCvTex` makes the build follow hand-written .tex; `resetCvTex`
     hands it back to the structured document. Both append a version. */
  cvTex: (scope: string) => req<CvTex>(`${cvPath(scope)}/tex`),
  saveCvTex: (scope: string, files: Record<string, string>) =>
    req<CvTex>(`${cvPath(scope)}/tex`, { method: "PUT", body: JSON.stringify({ files }) }),
  resetCvTex: (scope: string) => req<CvTex>(`${cvPath(scope)}/tex`, { method: "DELETE" }),

  /** Fetch the compiled PDF as an object URL (the <iframe> can't send the token). */
  cvPdfUrl: async (scope: string): Promise<string> => {
    const res = await fetch(`${BASE}${cvPath(scope)}/pdf`, { headers: { "X-API-Token": TOKEN } });
    if (!res.ok) throw new ApiError(res.status, "PDF not available");
    return URL.createObjectURL(await res.blob());
  },

  /* Tailor + CV Review (Phase 5). Both run on the queue: the response is a
     task, and what it produced arrives via `review()` once it finishes.
     Follow it with `useTask` — the WebSocket pushes every step. */
  tailor: (id: string) => req<Task>(`${jobPath(id)}/tailor`, { method: "POST" }),
  editCv: (id: string, instruction: string) =>
    req<Task>(`${jobPath(id)}/edit`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),
  review: (id: string) => req<ReviewData>(`${jobPath(id)}/review`),
  approve: (id: string) => req<JobDetail>(`${jobPath(id)}/approve`, { method: "POST" }),
  reject: (id: string) => req<JobDetail>(`${jobPath(id)}/reject`, { method: "POST" }),

  /* Apply (Phase 6). Also queued. `task.result.result` says what actually
     happened — a finished task can still mean "nothing was sent" (dry run) or
     "your turn" (portal), and neither is a success. */
  applyJob: (id: string, coverLetter?: boolean) =>
    req<Task>(`${jobPath(id)}/apply`, {
      method: "POST",
      body: JSON.stringify({ cover_letter: coverLetter ?? null }),
    }),
  confirmSubmit: (id: string) => req<JobDetail>(`${jobPath(id)}/confirm-submit`, { method: "POST" }),
  reportFailure: (id: string, reason: string) =>
    req<JobDetail>(`${jobPath(id)}/report-failure`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  applications: (result?: string, page: PageQuery = {}) =>
    req<Page<Application>>(`/applications${qs({ result, ...page })}`),
  applySettings: () => req<ApplySettings>("/applications/settings"),
  /** Applications whose next follow-up has come due. Read-only: nothing is sent. */
  followups: (page: PageQuery = {}) =>
    req<Page<Application>>(`/applications/followups${qs(page as Record<string, unknown>)}`),
  markFollowedUp: (id: number) =>
    req<Application>(`/applications/${id}/followed-up`, { method: "POST" }),
  stopFollowups: (id: number) =>
    req<Application>(`/applications/${id}/stop-followups`, { method: "POST" }),

  /* Outcome tracking (Phase 18). Recording one also ends the follow-up cadence
     server-side — the board just refetches. */
  recordOutcome: (
    id: number,
    body: { event_type: OutcomeType; occurred_at?: string; label?: string; notes?: string },
  ) => req<Application>(`/applications/${id}/outcome`, { method: "POST", body: JSON.stringify(body) }),
  applicationEvents: (id: number) => req<ApplicationEvent[]>(`/applications/${id}/events`),
  /** Undo a mis-click. The row stays; the stage rewinds. */
  retractEvent: (id: number, eventId: number) =>
    req<Application>(`/applications/${id}/events/${eventId}`, { method: "DELETE" }),

  /* Inbox sync (Phase 19). Reading the mailbox and classifying what matched
     can't answer inside a request, so it returns a task like crawling does. */
  syncInbox: () => req<Task>("/inbox/sync", { method: "POST" }),
  inboxSettings: () => req<InboxSettings>("/inbox/settings"),
  inboxSuggestions: (page: PageQuery = {}) =>
    req<Page<InboxSuggestion>>(`/inbox/suggestions${qs(page as Record<string, unknown>)}`),
  acceptSuggestion: (id: number) =>
    req<Application>(`/inbox/suggestions/${id}/accept`, { method: "POST" }),
  dismissSuggestion: (id: number) =>
    req<InboxSuggestion>(`/inbox/suggestions/${id}/dismiss`, { method: "POST" }),

  /* Orchestration (Phase 8). Crawling can't answer inside a request, so it
     returns a task and progress arrives over the WebSocket. */
  startCrawl: (body: CrawlRequest = {}) =>
    req<Task>("/crawl", { method: "POST", body: JSON.stringify(body) }),
  crawlSetup: () => req<CrawlSetupInfo>("/crawl/setup"),
  tasks: (kind?: string, page: PageQuery = {}) => req<Page<Task>>(`/tasks${qs({ kind, ...page })}`),
  task: (id: string) => req<Task>(`/tasks/${id}`),
  runs: (kind?: string, page: PageQuery = {}) =>
    req<Page<RunRecord>>(`/runs${qs({ kind, ...page })}`),
  /* Backups (deploy/). Listing is cheap; making one is not, so it returns a
     task like crawling does — a dump plus an upload outlives a request. */
  backups: () => req<BackupStatus>("/backups"),
  startBackup: () => req<Task>("/backups", { method: "POST" }),

  settings: () => req<Settings>("/settings"),
  saveSettings: (patch: Partial<Settings>) =>
    req<Settings>("/settings", { method: "PUT", body: JSON.stringify(patch) }),

  tailoredPdfUrl: async (id: string): Promise<string> => {
    const res = await fetch(`${BASE}${jobPath(id)}/cv`, { headers: { "X-API-Token": TOKEN } });
    if (!res.ok) throw new ApiError(res.status, "PDF not available");
    return URL.createObjectURL(await res.blob());
  },
};

/** Where the realtime socket lives.
 *
 * Derived from `window.location` rather than from BASE so the scheme follows
 * the page: behind Tailscale the dashboard is served over https, and a `ws://`
 * socket on an `https://` page is blocked by the browser as mixed content.
 * BASE is only consulted when it names an absolute host (dev pointing at a
 * remote backend). */
export function wsUrl(): string {
  if (/^https?:\/\//.test(BASE)) return `${BASE.replace(/^http/, "ws")}/ws`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${BASE}/ws`;
}

/** First frame on a new socket. The token travels in the body, not the query
 *  string, so it stays out of access logs and browser history. */
export function wsAuthFrame(): string {
  return JSON.stringify({ type: "auth", token: TOKEN });
}
