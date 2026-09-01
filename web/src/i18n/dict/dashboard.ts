import { ns } from "../ns";

/**
 * Copy for the dashboard surface: the deck itself, the funnel, the outcome
 * scorecard and the three charts it hangs on.
 *
 * The chart components (`ByDayChart`, `BySourceChart`, `SourceDonut`) read from
 * here too even though the donut is drawn on `/market`: their copy is two empty
 * states and a tooltip noun, and splitting four strings across two namespaces
 * costs more than it explains. What stays out is anything the backend wrote —
 * `split.note` is an English sentence composed by `jobpilot/analytics`, so it is
 * printed as-is rather than mirrored here where the two would drift.
 *
 * Source names, `email`/`portal` channels and the seniority ladder are not
 * translated: those are proper nouns and raw keys, and the Vietnamese market
 * advertises "Senior Backend" in English anyway (see `i18n/CLAUDE.md`).
 */
export const dashboard = ns({
  en: {
    title: "Control deck",
    subtitle: "Your pipeline, from discovery to runway.",

    // Top row of tiles
    crawled: "Crawled",
    crawledNote: "jobs in store",
    fresh: "Fresh",
    freshNote: "posted < 48h",
    shortlisted: "Shortlisted",
    shortlistedNote: "picked to tailor",
    applied: "Applied",
    appliedNote: "submitted",
    /** Not "success" — it only measures whether the dispatch left the machine. */
    sentOk: "Sent OK",
    sentOkIdle: "nothing dispatched yet",
    sentOkNote: "{sent}/{decided} left the machine",

    // What came back (Phase 18)
    outcomesTitle: "After you apply",
    outcomesMeta: "{n} real applications · dry runs excluded",
    outcomesMetaOne: "1 real application · dry runs excluded",
    answered: "Answered",
    interviews: "Interviews",
    offers: "Offers",
    nothingSent: "nothing sent yet",
    gotReply: "{n}/{of} got a human reply",
    gotInterview: "{n}/{of} reached an interview",
    tooFewToRate: "{n} of {of} — too few to rate",
    noInterviewsYet: "no interviews yet",
    fromInterviews: "from {n} interviews",
    fromInterviewsOne: "from 1 interview",

    // Cards
    funnelTitle: "Approach funnel",
    bySourceTitle: "By source",
    byDayTitle: "Crawled per day",
    byDayMeta: "last 14 days",

    // Funnel exits
    diverted: "Diverted",
    skippedCount: "{n} skipped",
    failedCount: "{n} failed",

    // Scorecard (PLAN.md §9.1 slot 20)
    dimSource: "Source",
    dimChannel: "Channel",
    dimLevel: "Level",
    scorecardTitle: "Where the answers come from",
    scorecardMeta:
      "{n} real applications · dry runs excluded · rates need {min}+ per row",
    scorecardMetaOne:
      "1 real application · dry runs excluded · rates need {min}+ per row",
    colSent: "Sent",
    colAnswered: "Answered",
    colInterviews: "Interviews",
    colOffers: "Offers",
    colReplyRate: "Reply rate",
    /** The honest cell: the sample is stated instead of a fake 0%. */
    needsSample: "n={n} · needs {min}",

    timingTitle: "How long an answer takes",
    timingEmpty: "Nobody has answered yet, so there is nothing to time.",
    timingUnit: "days, typically",
    timingRange: "fastest {fast}d · slowest {slow}d · from {n} answered",
    timingWaiting: "{n} still waiting — not counted above",
    timingUndated: " · {n} with no send date",
    timingInconsistent: " · {n} answered before the send date",
    timingThin: "Only {n} answers — read this as a hint, not a typical wait.",
    timingThinOne: "Only 1 answer — read this as a hint, not a typical wait.",

    repeatsTitle: "Ads that keep coming back",
    repeatsShown: "{shown} of {total}",
    repeatsEmpty: "No company has posted the same title {min}+ times.",
    repeatsPostings: "{n} postings",
    repeatsSpan: " over {n} days",
    repeatsNoDates: " · dates unknown",
    repeatsUndated: " · {n} undated",
    repeatsFootnote:
      "A repeat can mean steady hiring or a posting nobody fills — worth a look, not a verdict.",

    // Charts
    noCrawlHistory: "No crawl history yet.",
    noJobsYet: "No jobs yet.",
    nothingCrawled: "Nothing crawled yet.",
    /** Tooltip nouns: the number is printed right before them. */
    tipCrawled: "crawled",
    tipJobs: "jobs",
    tipJobsShare: "jobs · {pct}%",
    postings: "postings",
    otherSources: "Other ({n})",

    // Backend down
    backendDown: "Couldn't reach the backend.",
    backendHint: "Start it with",
  },
  vi: {
    title: "Bảng điều khiển",
    subtitle: "Toàn bộ pipeline, từ lúc crawl ra job tới lúc nộp đơn.",

    crawled: "Đã crawl",
    crawledNote: "job trong kho",
    fresh: "Mới",
    freshNote: "đăng < 48h",
    shortlisted: "Đã chọn",
    shortlistedNote: "chờ tailor",
    applied: "Đã nộp",
    appliedNote: "đã gửi đi",
    sentOk: "Gửi được",
    sentOkIdle: "chưa gửi đơn nào",
    sentOkNote: "{sent}/{decided} đi trót lọt",

    outcomesTitle: "Sau khi nộp đơn",
    outcomesMeta: "{n} đơn thật · không tính dry run",
    outcomesMetaOne: "1 đơn thật · không tính dry run",
    answered: "Có hồi âm",
    interviews: "Phỏng vấn",
    offers: "Offer",
    nothingSent: "chưa gửi đơn nào",
    gotReply: "{n}/{of} có người trả lời",
    gotInterview: "{n}/{of} vào tới vòng phỏng vấn",
    tooFewToRate: "{n}/{of} — quá ít để tính tỉ lệ",
    noInterviewsYet: "chưa có phỏng vấn nào",
    fromInterviews: "từ {n} lượt phỏng vấn",
    fromInterviewsOne: "từ 1 lượt phỏng vấn",

    funnelTitle: "Phễu tiếp cận",
    bySourceTitle: "Theo nguồn",
    byDayTitle: "Crawl theo ngày",
    byDayMeta: "14 ngày gần nhất",

    diverted: "Rẽ ngang",
    skippedCount: "{n} bỏ qua",
    failedCount: "{n} lỗi",

    dimSource: "Nguồn",
    dimChannel: "Kênh",
    dimLevel: "Cấp bậc",
    scorecardTitle: "Hồi âm đến từ đâu",
    scorecardMeta:
      "{n} đơn thật · không tính dry run · mỗi dòng cần {min}+ đơn mới tính tỉ lệ",
    scorecardMetaOne:
      "1 đơn thật · không tính dry run · mỗi dòng cần {min}+ đơn mới tính tỉ lệ",
    colSent: "Đã gửi",
    colAnswered: "Hồi âm",
    colInterviews: "Phỏng vấn",
    colOffers: "Offer",
    colReplyRate: "Tỉ lệ hồi âm",
    needsSample: "n={n} · cần {min}",

    timingTitle: "Bao lâu thì có hồi âm",
    timingEmpty: "Chưa ai trả lời nên chưa có gì để đo.",
    timingUnit: "ngày, tính trung vị",
    timingRange: "nhanh nhất {fast} ngày · chậm nhất {slow} ngày · từ {n} hồi âm",
    timingWaiting: "{n} đơn vẫn đang chờ — không tính ở trên",
    timingUndated: " · {n} không rõ ngày gửi",
    timingInconsistent: " · {n} có hồi âm trước cả ngày gửi",
    timingThin: "Mới {n} hồi âm — coi như tham khảo, chưa phải mức chờ điển hình.",
    timingThinOne: "Mới 1 hồi âm — coi như tham khảo, chưa phải mức chờ điển hình.",

    repeatsTitle: "Tin đăng đi đăng lại",
    repeatsShown: "{shown} trên {total}",
    repeatsEmpty: "Chưa công ty nào đăng cùng một vị trí {min}+ lần.",
    repeatsPostings: "{n} lần đăng",
    repeatsSpan: " trong {n} ngày",
    repeatsNoDates: " · không rõ ngày",
    repeatsUndated: " · {n} tin không có ngày",
    repeatsFootnote:
      "Đăng lại có thể là tuyển đều tay, cũng có thể là vị trí không ai trụ được — đáng ngó, chưa đủ để kết luận.",

    noCrawlHistory: "Chưa có lịch sử crawl.",
    noJobsYet: "Chưa có job nào.",
    nothingCrawled: "Chưa crawl được gì.",
    tipCrawled: "job đã crawl",
    tipJobs: "job",
    tipJobsShare: "job · {pct}%",
    postings: "tin đăng",
    otherSources: "Khác ({n})",

    backendDown: "Không kết nối được backend.",
    backendHint: "Chạy nó bằng lệnh",
  },
});
