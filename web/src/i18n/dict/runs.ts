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
    queryPlaceholder: "e.g. java, spring boot — commas separate searches",
    queryHint:
      "Commas separate searches: each keyword is its own search on every site, so keep each one short.",
    keywordCount: "{count} keywords → {count} searches per site",
    tooManyKeywords: "At most {max} keywords per crawl.",

    /* Recent setups ------------------------------------------------------- */
    recentTitle: "Crawl again",
    recentHint: "your last distinct setups — same sources, keywords and depth",
    recentEmpty: "Nothing to repeat yet — the setups of your crawls will show up here.",
    recrawl: "Crawl again",
    allSources: "all sources",
    limitDefaultShort: "default depth",
    perSite: "{count}/keyword/site",
    foundNew: "+{count} new",
    fromCv: "From your CV — click to add",
    noSuggestions: "No suggestions yet — fill in your skills and tech stack in",
    noSuggestionsEnd: "and they'll show up here.",

    jobsPerSite: "Jobs per site",
    limitDefault: "Default ({count})",
    limitSlow: "(slow)",

    crawlNow: "Crawl now",
    placesTitle: "Where to work",
    place_0: "Ho Chi Minh City",
    place_1: "Ha Noi",
    place_2: "Da Nang",
    place_3: "Anywhere in Vietnam",
    place_4: "Remote",
    placeOther: "Another place, e.g. Singapore",
    placeAdd: "Add",
    placesHint:
      "Boards that can be searched by city are asked for these; afterwards a posting that names another place is left out. One that names no place is kept.",
    placesNone: "Anywhere.",
    placesNoneCity: "Anywhere — the Vietnamese boards stay held to {city} (Settings).",
    modesTitle: "How to work",
    mode_onsite: "On-site",
    mode_hybrid: "Hybrid",
    mode_remote: "Remote",
    modesHint:
      "A posting that states another work mode is left out. Most postings don't say — those are kept.",
    modesNone: "Any work mode.",
    saveWhereHow: "Also save where and how as the default for scheduled crawls",
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
    colRejected: "rejected",
    colRejectedWhy: "postings the database refused to store — see persist_failed in the crawl log",

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
    queryPlaceholder: "vd: java, spring boot — dấu phẩy tách các lượt tìm",
    queryHint:
      "Dấu phẩy tách các lượt tìm: mỗi từ khoá là một lượt tìm riêng trên mọi site, nên giữ từng từ thật ngắn.",
    keywordCount: "{count} từ khoá → {count} lượt tìm mỗi site",
    tooManyKeywords: "Tối đa {max} từ khoá mỗi lần crawl.",

    recentTitle: "Crawl lại",
    recentHint: "các cấu hình gần nhất — cùng nguồn, từ khoá và độ sâu",
    recentEmpty: "Chưa có gì để chạy lại — cấu hình các lượt crawl của bạn sẽ hiện ở đây.",
    recrawl: "Crawl lại",
    allSources: "mọi nguồn",
    limitDefaultShort: "độ sâu mặc định",
    perSite: "{count}/từ khoá/site",
    foundNew: "+{count} mới",
    fromCv: "Lấy từ CV của bạn — bấm để thêm",
    noSuggestions: "Chưa có gợi ý — điền skill và tech stack trong",
    noSuggestionsEnd: "rồi chúng sẽ hiện ở đây.",

    jobsPerSite: "Số job mỗi site",
    limitDefault: "Mặc định ({count})",
    limitSlow: "(chậm)",

    crawlNow: "Crawl ngay",
    placesTitle: "Nơi làm việc",
    place_0: "TP. Hồ Chí Minh",
    place_1: "Hà Nội",
    place_2: "Đà Nẵng",
    place_3: "Toàn Việt Nam",
    place_4: "Remote",
    placeOther: "Nơi khác, vd. Singapore",
    placeAdd: "Thêm",
    placesHint:
      "Trang nào tìm được theo thành phố thì hỏi đúng nơi này; sau đó tin ghi nơi khác bị lọc. Tin không ghi nơi làm thì vẫn giữ.",
    placesNone: "Ở đâu cũng được.",
    placesNoneCity: "Ở đâu cũng được — riêng ITviec/TopCV/VietnamWorks vẫn giới hạn ở {city} (Cài đặt).",
    modesTitle: "Hình thức làm việc",
    mode_onsite: "Tại văn phòng",
    mode_hybrid: "Hybrid",
    mode_remote: "Remote",
    modesHint:
      "Tin ghi rõ hình thức khác sẽ bị lọc. Phần lớn tin không ghi — những tin đó vẫn giữ.",
    modesNone: "Hình thức nào cũng được.",
    saveWhereHow: "Lưu nơi làm và hình thức này làm mặc định cho các lượt crawl tự động",
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
    colRejected: "bị từ chối",
    colRejectedWhy: "tin mà database từ chối lưu — xem persist_failed trong log crawl",

    history: "Lịch sử",
    historyCount: "{count} run",
    historyEmpty: "Chưa ghi nhận run nào.",
    runsNoun: "run",
    oneJob: "1 job",
    nJobs: "{count} job",
    siteFailed: "lỗi",
  },
});
