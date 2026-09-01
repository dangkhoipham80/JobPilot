import { ns } from "../ns";

/**
 * Copy for the runs surface: the crawl setup card, the live queue and the
 * persisted run history.
 *
 * Left English in both languages on purpose: `crawl`, `run`, `task`, `queue`,
 * `source` as a chart/table term, `rate limit`, `guardrail`, `JD`. Vietnamese
 * developers say all of these in English, and the run history sits next to a
 * terminal where the same words come out of the CLI.
 */
export const runs = ns({
  en: {
    /* Page header --------------------------------------------------------- */
    title: "Runs",
    subtitle: "What the agent is doing now, and everything it has done.",

    /* Crawl setup card ---------------------------------------------------- */
    setupTitle: "Crawl setup",
    setupScope: "applies to this run only",

    sources: "Sources",
    noSourceReady: "No source is ready to crawl. Turn one on in",
    notReady: "On in Settings but not implemented yet: {names} — they'd crawl nothing.",
    off: "Off in Settings: {names}",

    searchFor: "Search for",
    /** The default from Settings, shown greyed in the field. */
    queryFromSettings: "{query} (from Settings)",
    /**
     * A two-word example, not the word "keywords": the query becomes a URL slug
     * at each board, so "java spring boot backend" returns zero jobs on TopCV
     * while "java spring" works. Showing a short query is the shortest way to
     * say so.
     */
    queryPlaceholder: "e.g. java spring — short beats specific",
    fromCv: "From your CV — click to add",
    noSuggestions: "No suggestions yet — fill in your skills and tech stack in",
    noSuggestionsEnd: "and they'll show up here.",

    jobsPerSite: "Jobs per site",
    limitDefault: "Default ({count})",
    limitSlow: "(slow)",

    crawlNow: "Crawl now",
    crawlBlocked:
      "A crawl is already running. One at a time — a second would race the same sites and trip their rate limits.",
    crawlFailed: "Could not start the crawl",

    /* Queue --------------------------------------------------------------- */
    queue: "Queue",
    queueCount: "{count} recent",
    queueEmpty: "Nothing queued. Hit “Crawl now” to look for jobs.",
    tasksNoun: "tasks",

    /** Result line of a finished tailor task: "v3 · match 82% · 2 pages". */
    tailorResult: "v{version} · match {match}% · {pages}",
    onePage: "1 page",
    nPages: "{count} pages",

    /** How an apply dispatch ended — the task finished either way. */
    outcomeSuccess: "success",
    outcomeDryRun: "dry run",
    outcomeAwaitingUser: "awaiting you",
    outcomeFailed: "failed",

    /* Per-site crawl table ------------------------------------------------ */
    colSource: "source",
    colNew: "new",
    colUpdated: "updated",
    colDup: "dup",
    colKept: "kept",
    colKeptWhy: "kept despite matching another board, because that board's copy had no JD",
    colFresh: "fresh",

    /* History ------------------------------------------------------------- */
    history: "History",
    historyCount: "{count} runs",
    historyEmpty: "No runs recorded yet.",
    runsNoun: "runs",
    oneJob: "1 job",
    nJobs: "{count} jobs",
    /** Inside the one-line stats summary: "itviec: failed". */
    siteFailed: "failed",
  },
  vi: {
    title: "Lượt chạy",
    subtitle: "Agent đang làm gì, và mọi thứ nó đã chạy.",

    setupTitle: "Cấu hình crawl",
    setupScope: "chỉ áp dụng cho run này",

    sources: "Nguồn",
    noSourceReady: "Chưa có nguồn nào sẵn sàng để crawl. Bật một cái trong",
    notReady: "Đang bật trong Cài đặt nhưng chưa code xong: {names} — crawl sẽ không ra gì.",
    off: "Đang tắt trong Cài đặt: {names}",

    searchFor: "Tìm gì",
    queryFromSettings: "{query} (lấy từ Cài đặt)",
    queryPlaceholder: "vd: java spring — ngắn ăn đứt chi tiết",
    fromCv: "Lấy từ CV của bạn — bấm để thêm",
    noSuggestions: "Chưa có gợi ý — điền skill và tech stack trong",
    noSuggestionsEnd: "rồi chúng sẽ hiện ở đây.",

    jobsPerSite: "Số job mỗi site",
    limitDefault: "Mặc định ({count})",
    limitSlow: "(chậm)",

    crawlNow: "Crawl ngay",
    crawlBlocked:
      "Đang có một crawl chạy rồi. Mỗi lần một cái thôi — chạy song song là hai bên đụng cùng site và dính rate limit.",
    crawlFailed: "Không khởi động được crawl",

    queue: "Queue",
    queueCount: "{count} gần đây",
    queueEmpty: "Queue đang trống. Bấm “Crawl ngay” để đi tìm job.",
    tasksNoun: "task",

    tailorResult: "v{version} · khớp {match}% · {pages}",
    onePage: "1 trang",
    nPages: "{count} trang",

    outcomeSuccess: "thành công",
    outcomeDryRun: "chạy thử",
    outcomeAwaitingUser: "chờ bạn",
    outcomeFailed: "lỗi",

    colSource: "nguồn",
    colNew: "mới",
    colUpdated: "cập nhật",
    colDup: "trùng",
    colKept: "giữ lại",
    colKeptWhy: "vẫn giữ dù trùng tin của board khác, vì bản bên đó không có JD",
    colFresh: "mới đăng",

    history: "Lịch sử",
    historyCount: "{count} run",
    historyEmpty: "Chưa ghi nhận run nào.",
    runsNoun: "run",
    oneJob: "1 job",
    nJobs: "{count} job",
    siteFailed: "lỗi",
  },
});
