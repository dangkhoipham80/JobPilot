import { ns } from "../ns";

/**
 * Copy for the jobs surface: the list, one job's detail page, the description
 * editor, the by-hand add form, and the match/quality badges that appear in all
 * of them.
 *
 * What is deliberately *not* here: the job title, the company name and the
 * description body. Those come from the crawler and are shown verbatim in both
 * languages — translating a posting would misquote the employer, and the tailor
 * downstream matches against the original words.
 *
 * "Tailor", "crawl", "JD", "CV" and "external" stay English in the Vietnamese
 * copy too. They are the words this project's own CLI, logs and job ads use;
 * inventing Vietnamese equivalents would make the UI harder to line up with
 * everything around it, not easier to read.
 */
export const jobs = ns({
  en: {
    /* List page ---------------------------------------------------------- */
    title: "Jobs",
    /** Everything the filters matched, not just this page. */
    matching: "{count} matching",
    orderCrawled: "newest crawl day first, best match within the day, skipped ones last",
    orderMatch: "best match first, skipped ones last",
    orderPosted: "newest postings first, skipped ones last",

    // Banner shown when the list is narrowed to one crawl run. Split around the
    // bold run number so both languages can put it where their grammar wants.
    runFilterPrefix: "Showing only what",
    runFilterCrawl: "crawl #{id}",
    runFilterSuffix: "discovered.",
    showAll: "Show all",

    /* Filter bar --------------------------------------------------------- */
    searchPlaceholder: "Search title or company",
    allSources: "All sources",
    allLevels: "All levels",
    allStatuses: "All statuses",
    windowTitle: "When it was crawled",
    windowAny: "Any time",
    window24h: "Last 24h",
    window7d: "Last 7 days",
    window30d: "Last 30 days",
    // Bands are half-open on the API side (50% is in "50–74%", 75% is not),
    // so the four of them add up to the whole list.
    matchTitle: "Match score band",
    matchAny: "Any match",
    match75: "Match 75%+",
    match50: "Match 50–74%",
    match25: "Match 25–49%",
    match0: "Match under 25%",
    sortTitle: "Sort order",
    sortCrawled: "Sort: crawl day, then match",
    sortMatch: "Sort: best match",
    sortPosted: "Sort: newest posting",
    freshOnly: "Fresh",
    allCopies: "Older listings",
    allCopiesHint:
      "Also show earlier listings of postings their board has re-listed. By default only the newest is shown, plus any older copy you already acted on.",
    reposted: "listed ×{n}",
    repostedHint: "This board has listed the same posting {n} more time(s) before; this is the newest.",
    olderCopy: "older listing",
    olderCopyLead: "This is an older listing — the board has re-listed this posting since.",
    openNewest: "Open the newest listing →",
    copiesTitle: "Listed {n} times",
    copiesHint: "The same posting under different ids on its board. The newest is the one to apply through.",
    newestCopy: "newest",
    copySeen: "first seen {first} · last seen {last}",
    clear: "Clear",

    /* Table -------------------------------------------------------------- */
    colRole: "Role",
    colSource: "Source",
    colMatch: "Match",
    colStatus: "Status",
    colPosted: "Posted",
    colCrawled: "Crawled",
    colActions: "Actions",
    /** Pager readout: "1–25 of 312 jobs". */
    jobsNoun: "jobs",

    shortlist: "Shortlist",
    skip: "Skip",
    openOriginal: "Open original posting",
    onlyFromCrawl: "Only jobs from crawl #{id}",
    addedByHand: "Added by hand",

    loadFailed: "Couldn't load jobs.",
    emptyFiltered: "No jobs match these filters.",
    emptyFilteredHint: "Try clearing a filter.",
    empty: "No jobs yet.",
    /** Followed by the literal CLI command, which is never translated. */
    emptyHint: "Run a crawl:",

    /* Detail page -------------------------------------------------------- */
    back: "Back to jobs",
    detailLoadFailed: "Couldn't load this job.",
    /** "<job id> · posted 3h ago" */
    posted: "posted",
    reviewCv: "Review CV",
    tailorCv: "Tailor CV",
    original: "Original",

    /* Description card --------------------------------------------------- */
    descriptionTitle: "Job description",
    /** `channel` is a backend value (email / portal / external), left as-is. */
    appliesVia: "applies via {channel}",
    noJdLinkedIn:
      "This job came from a LinkedIn alert, which announces the posting but not its text — and JobPilot won't fetch it (robots.txt).",
    noJdPlain: "No description yet.",
    noJdAdvice:
      "Tailoring without one produces a generic CV — open the posting, copy the description, and paste it here first.",
    descriptionPlaceholder: "Paste the full job description…",
    saveFailed: "Could not save",
    // The markers themselves (`##`, `-`, `**bold**`) are markup, not copy.
    mdHeading: "heading",
    mdBullet: "bullet",
    mdBold: "bold",

    /* Add a job by hand -------------------------------------------------- */
    addJob: "Add job",
    addJobTitle: "Add a job by hand",
    addJobIntro:
      "For postings JobPilot can't crawl — LinkedIn's robots.txt forbids it, and a post in a Facebook or Zalo group is nobody's to crawl. Paste the description, or upload a screenshot of it; without one the tailor has nothing to work from.",
    afterSaveFailed: "The next step failed",
    savedAnyway: "the job itself was saved and is in Jobs.",
    tailorJdOpen: "Paste a job description…",
    tailorJdIntro:
      "Paste a posting (or a screenshot of one). It is saved as a job, shortlisted, and your Master CV is tailored to it — you review the result before anything is sent.",
    tailorJdSubmit: "Save & tailor my CV",
    tailorJdNext: "Opens the CV Review page while the tailor runs — about a minute.",
    foundOn: "Found on",
    foundElsewhere: "Somewhere else",
    readFile: "From an image / PDF",
    readFileBusy: "Reading the file…",
    readFileFailed: "Could not read the file",
    readFileBlocked:
      "The description box holds text you typed or edited. Clear it first — a file reading replaces what is in the box.",
    readFileTranscribed:
      "The AI typed this text out of your file. Read it against the original before saving — a misread number becomes a requirement nobody set.",
    readFileLayer:
      "This is the PDF's own text, copied as is — no AI wrote it. Words that sit inside a picture in the PDF are not in it, and columns may have come out interleaved.",
    readFileOriginal: "Original:",
    readFilePage: "page {n}",
    readFileUnreadable: "The AI noted what it could not read:",
    fieldTitle: "Job title *",
    fieldCompany: "Company *",
    fieldLocation: "Location",
    fieldSalary: "Salary",
    addJobJdPlaceholder: "Paste the full job description here — or paste a screenshot of it…",
    addJobChannel: "Applies as external — you submit it yourself.",
    addJobFailed: "Could not add the job",

    /* Have a model read the paste --------------------------------------- */
    readJd: "Let AI fill this in",
    readJdBusy: "Reading the posting…",
    readJdHint:
      "Paste the posting first, then let AI pull out the title, company, pay and skills. Check what it filled in — a blank means the posting didn't say.",
    readJdFilled: "Filled in from the posting. Correct anything that's wrong before saving.",
    readJdFailed: "Could not read the posting",
    readJdEmpty: "Paste the job description first.",
    readJdApplyEmail: "The posting says to apply to {email}. Use it as the apply target?",
    readJdUseEmail: "Use it",
    readJdFound: "Read from the posting: {summary}",

    /* The posting's body, bucketed ------------------------------------- */
    viewStructured: "Structured",
    viewRaw: "Original",
    secRole: "The role",
    secResponsibilities: "Responsibilities",
    secMustHave: "Required",
    secNiceToHave: "A plus",
    secSoftSkills: "Soft skills",
    secOutputs: "Expected output",
    secBenefits: "Benefits",
    secHowToApply: "How to apply",

    /* Pay shape + work arrangement -------------------------------------- */
    payFixed: "fixed",
    payUpTo: "up to",
    payFrom: "from",
    payRange: "range",
    modeOnsite: "On-site",
    modeHybrid: "Hybrid",
    modeRemote: "Remote",

    /* Match meter + quality flags ---------------------------------------- */
    match: "Match {pct}%",
    mentions: "Mentions: {list}",
    doesntMention: "Doesn't mention: {list}",
    flagNoJd: "no JD",
    flagNoJdWhy: "No description — paste one in before tailoring.",
    flagThinJd: "thin JD",
    flagThinJdWhy: "Very short description; there may not be enough here to tailor against.",
    flagStale: "old",
    flagStaleWhy: "Posted a while ago; the role may already be filled.",
    flagUndated: "undated",
    flagUndatedWhy: "The source didn't publish a date, so freshness is unknown.",

    /* Fresh beacon ------------------------------------------------------- */
    freshTitle: "Posted within 48h",
    freshBadge: "fresh",
  },
  vi: {
    title: "Việc làm",
    matching: "{count} tin khớp",
    orderCrawled:
      "ngày crawl mới nhất trước, trong ngày thì độ khớp cao trước, tin đã bỏ qua xuống cuối",
    orderMatch: "độ khớp cao nhất trước, tin đã bỏ qua xuống cuối",
    orderPosted: "tin đăng mới nhất trước, tin đã bỏ qua xuống cuối",

    runFilterPrefix: "Chỉ hiện những tin mà",
    runFilterCrawl: "crawl #{id}",
    runFilterSuffix: "tìm được.",
    showAll: "Hiện tất cả",

    searchPlaceholder: "Tìm theo tiêu đề hoặc công ty",
    allSources: "Tất cả nguồn",
    allLevels: "Tất cả level",
    allStatuses: "Tất cả trạng thái",
    windowTitle: "Crawl lúc nào",
    windowAny: "Mọi lúc",
    window24h: "24h qua",
    window7d: "7 ngày qua",
    window30d: "30 ngày qua",
    matchTitle: "Khoảng độ khớp",
    matchAny: "Mọi độ khớp",
    match75: "Khớp từ 75%",
    match50: "Khớp 50–74%",
    match25: "Khớp 25–49%",
    match0: "Khớp dưới 25%",
    sortTitle: "Thứ tự sắp xếp",
    sortCrawled: "Xếp: ngày crawl → độ khớp",
    sortMatch: "Xếp: độ khớp cao nhất",
    sortPosted: "Xếp: tin đăng mới nhất",
    // Not "fresher" — that is a seniority level in this same UI.
    freshOnly: "Tin mới",
    allCopies: "Bản đăng cũ",
    allCopiesHint:
      "Hiện cả các lần đăng trước của tin mà trang tuyển dụng đã đăng lại. Mặc định chỉ hiện bản mới nhất, cùng bản cũ nào bạn đã thao tác.",
    reposted: "đăng lại ×{n}",
    repostedHint: "Trang này đã đăng đúng tin này thêm {n} lần trước đó; đây là bản mới nhất.",
    olderCopy: "bản đăng cũ",
    olderCopyLead: "Đây là bản đăng cũ — trang tuyển dụng đã đăng lại tin này sau đó.",
    openNewest: "Mở bản đăng mới nhất →",
    copiesTitle: "Tin này đã đăng {n} lần",
    copiesHint: "Cùng một tin với các mã khác nhau trên trang tuyển dụng. Nên nộp qua bản mới nhất.",
    newestCopy: "mới nhất",
    copySeen: "thấy lần đầu {first} · lần cuối {last}",
    clear: "Xoá lọc",

    colRole: "Vị trí",
    colSource: "Nguồn",
    colMatch: "Độ khớp",
    colStatus: "Trạng thái",
    colPosted: "Đăng",
    colCrawled: "Crawl",
    colActions: "Thao tác",
    jobsNoun: "tin",

    shortlist: "Chọn",
    skip: "Bỏ qua",
    openOriginal: "Mở tin gốc",
    onlyFromCrawl: "Chỉ tin từ crawl #{id}",
    addedByHand: "Tự thêm bằng tay",

    loadFailed: "Không tải được danh sách job.",
    emptyFiltered: "Không có job nào khớp bộ lọc.",
    emptyFilteredHint: "Thử bỏ bớt một filter.",
    empty: "Chưa có job nào.",
    emptyHint: "Chạy một lượt crawl:",

    back: "Về danh sách job",
    detailLoadFailed: "Không tải được tin này.",
    posted: "đăng",
    reviewCv: "Xem lại CV",
    tailorCv: "Tailor CV",
    original: "Tin gốc",

    descriptionTitle: "Mô tả công việc",
    appliesVia: "nộp qua {channel}",
    noJdLinkedIn:
      "Tin này đến từ LinkedIn Job Alert — email chỉ báo có tin chứ không kèm nội dung, mà JobPilot thì không tự fetch (robots.txt chặn).",
    noJdPlain: "Chưa có mô tả.",
    noJdAdvice:
      "Tailor mà không có JD thì chỉ ra một bản CV chung chung — mở tin gốc, copy phần mô tả, dán vào đây trước đã.",
    descriptionPlaceholder: "Dán toàn bộ mô tả công việc…",
    saveFailed: "Không lưu được",
    mdHeading: "tiêu đề",
    mdBullet: "gạch đầu dòng",
    mdBold: "in đậm",

    addJob: "Thêm job",
    addJobTitle: "Thêm job bằng tay",
    addJobIntro:
      "Dành cho tin JobPilot không crawl được — robots.txt của LinkedIn chặn, còn bài đăng trong group Facebook hay Zalo thì không ai được crawl. Dán mô tả, hoặc tải ảnh chụp tin lên; thiếu mô tả thì tailor chẳng có gì để làm.",
    afterSaveFailed: "Bước tiếp theo bị lỗi",
    savedAnyway: "job thì đã được lưu, nằm trong Việc làm.",
    tailorJdOpen: "Dán một JD…",
    tailorJdIntro:
      "Dán một tin tuyển dụng (hoặc ảnh chụp tin). Tin được lưu thành job, đưa vào shortlist, rồi Master CV được tailor theo nó — bạn duyệt kết quả trước khi bất cứ thứ gì được gửi đi.",
    tailorJdSubmit: "Lưu & tailor CV",
    tailorJdNext: "Mở trang CV Review trong lúc tailor chạy — khoảng một phút.",
    foundOn: "Tìm thấy ở",
    foundElsewhere: "Nơi khác",
    readFile: "Từ ảnh / PDF",
    readFileBusy: "Đang đọc file…",
    readFileFailed: "Không đọc được file",
    readFileBlocked:
      "Ô mô tả đang có chữ bạn gõ hoặc đã sửa. Xoá đi trước đã — bản đọc từ file sẽ thay toàn bộ nội dung trong ô.",
    readFileTranscribed:
      "AI đã chép phần chữ này từ file của bạn. Hãy so với bản gốc trước khi lưu — đọc nhầm một con số là thành một yêu cầu không ai đặt ra.",
    readFileLayer:
      "Đây là phần chữ của chính file PDF, lấy nguyên văn — không có AI nào viết. Chữ nằm trong ảnh của PDF thì không có ở đây, và các cột có thể bị xen vào nhau.",
    readFileOriginal: "Bản gốc:",
    readFilePage: "trang {n}",
    readFileUnreadable: "AI ghi lại những chỗ nó không đọc được:",
    fieldTitle: "Tiêu đề công việc *",
    fieldCompany: "Công ty *",
    fieldLocation: "Địa điểm",
    fieldSalary: "Lương",
    addJobJdPlaceholder: "Dán toàn bộ mô tả công việc vào đây — hoặc dán ảnh chụp tin…",
    addJobChannel: "Nộp theo kênh external — bạn tự nộp.",
    addJobFailed: "Không thêm được job",

    readJd: "Để AI điền giúp",
    readJdBusy: "Đang đọc tin…",
    readJdHint:
      "Dán tin tuyển dụng trước, rồi để AI rút ra tiêu đề, công ty, lương và skill. Xem lại phần nó điền — ô trống nghĩa là tin không nói.",
    readJdFilled: "Đã điền từ tin tuyển dụng. Sửa lại chỗ nào sai trước khi lưu.",
    readJdFailed: "Không đọc được tin",
    readJdEmpty: "Dán mô tả công việc trước đã.",
    readJdApplyEmail: "Tin ghi nộp về {email}. Dùng làm địa chỉ nộp?",
    readJdUseEmail: "Dùng",
    readJdFound: "Đọc được từ tin: {summary}",

    viewStructured: "Có cấu trúc",
    viewRaw: "Nguyên văn",
    secRole: "Vai trò",
    secResponsibilities: "Nhiệm vụ",
    secMustHave: "Yêu cầu bắt buộc",
    secNiceToHave: "Ưu tiên",
    secSoftSkills: "Kỹ năng mềm",
    secOutputs: "Kết quả mong đợi",
    secBenefits: "Quyền lợi",
    secHowToApply: "Cách ứng tuyển",

    payFixed: "cố định",
    payUpTo: "tối đa",
    payFrom: "từ",
    payRange: "khoảng",
    modeOnsite: "Tại văn phòng",
    modeHybrid: "Hybrid",
    modeRemote: "Từ xa",

    match: "Khớp {pct}%",
    mentions: "Có nhắc: {list}",
    doesntMention: "Không nhắc: {list}",
    flagNoJd: "thiếu JD",
    flagNoJdWhy: "Chưa có mô tả — dán JD vào trước khi tailor.",
    flagThinJd: "JD sơ sài",
    flagThinJdWhy: "Mô tả quá ngắn, có thể không đủ dữ kiện để tailor.",
    flagStale: "cũ",
    flagStaleWhy: "Đăng đã lâu, vị trí có thể đã tuyển xong.",
    flagUndated: "không rõ ngày",
    flagUndatedWhy: "Nguồn không đăng ngày, nên không biết tin mới hay cũ.",

    freshTitle: "Đăng trong 48h qua",
    freshBadge: "mới",
  },
});
