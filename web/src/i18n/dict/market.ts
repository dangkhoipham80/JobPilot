import { ns } from "../ns";

/**
 * Copy for the market surface.
 *
 * Three things on this page deliberately stay English in both languages:
 * skill names, city names and source names come straight out of the corpus and
 * are proper nouns (`PostgreSQL`, `Da Nang`, `ITviec`), and the seniority rungs
 * are advertised in English by Vietnamese employers — see `i18n/CLAUDE.md`.
 *
 * The coverage line is the one string on the page that must not be smoothed
 * over in translation: `covered` and `total` are different numbers and the
 * whole point of printing both is that a facet built from 18 of 73 jobs is a
 * fact about 18 jobs. "18 trên 73 tin" keeps the denominator audible;
 * a bare percentage would not.
 *
 * `facet.note` is *not* here on purpose. The analytics layer writes it
 * (`jobpilot/analytics/market.py`), so it is a backend value like `task.progress`
 * and is rendered verbatim.
 */
export const market = ns({
  en: {
    title: "Market",
    /** The page is about the crawled corpus, never about "the market". */
    intro:
      "What the {count} crawled postings look like. These describe the ads JobPilot collected — not the market as a whole. Each card says how many jobs it saw.",
    loadFailed: "Couldn't load market data: {error}",

    // In-page section nav. Keys are matched to section ids in Market.tsx.
    sections: "Sections",
    navOverview: "Overview",
    navSkills: "Skills",
    navSalary: "Salary",
    navCities: "Locations",
    navLevels: "Seniority",
    navMatch: "Match score",
    navQuality: "Posting quality",
    navSources: "Sources",
    navCalendar: "Posting calendar",

    /** "23 of 73 jobs" — never a bare percentage. */
    coverage: "{covered} of {total} jobs",

    emptyRows: "Nothing to show yet.",
    emptyDates: "No posting dates yet.",
    emptySalary: "No posting carried a salary this parser could read.",

    // Tooltip unit words: the value is a count, these name what is counted.
    tipJobs: "jobs",
    tipPosted: "posted",
    /** `useFormat().shortDay` drops the year; the trend tooltip wants it back. */
    dayWithYear: "{day}, {year}",

    statPostings: "Postings",
    statSources: "across {count} source(s)",
    statMedian: "Median pay (est.)",
    statMedianFrom: "per month, from {count} job(s)",
    statMedianNone: "no parsable salary yet",
    statClean: "Clean ads",
    statCleanHint: "no missing-JD or stale flag",

    skillsTitle: "Most requested skills",
    skillsNote:
      "Counted once per job from the canonical form, so “Spring Boot” and “Spring” are one thing. LinkedIn alerts carry no tags at all, which is most of what is missing here.",

    salaryTitle: "Pay distribution",
    salaryMedian: "median / month",
    salaryThin: "from {covered} of {total} postings — not yet a distribution.",
    salaryRange:
      "Range {min}–{max}/month. Converted at {rate} VND/USD (checked {date}) — an estimate, not a quote.",

    citiesTitle: "Where the jobs are",

    levelsTitle: "Seniority mix",
    /** "unknown, not junior" is the load-bearing half of this sentence. */
    levelsNote:
      "Level is inferred from the title and description, so an ad with neither is unknown rather than junior.",

    matchTitle: "Match against your stacks",
    // Split around the <code> element rather than inlining markup in a string:
    // the config key sits mid-sentence in both languages, but not at the same
    // word position, so a prefix/suffix pair is what keeps both readable.
    matchNoteBefore: "Scored at crawl time against ",
    matchNoteAfter:
      ". A corpus bunched to the left means the search queries need work, not that the market does.",

    qualityTitle: "Posting quality",
    qualityNote: "A posting can carry more than one flag, so these add up past the corpus.",

    sourcesTitle: "Where they came from",
    sourcesNote:
      "The denominator behind every other card on this page: a facet LinkedIn can't fill — skills, salary, tags — is missing most of this ring.",

    calendarTitle: "Posted per day",
    // Same prefix/emphasis/suffix split as the match note, for the same reason.
    calendarNoteBefore: "By ",
    calendarNoteEm: "posting date",
    calendarNoteAfter:
      ", not crawl date — the deck's “crawled per day” chart measures your habits, this measures the market's.",
  },
  vi: {
    title: "Thị trường",
    intro:
      "Ảnh chụp {count} tin đã crawl. Đây là những tin JobPilot thu được, không phải toàn bộ thị trường. Mỗi card ghi rõ nó nhìn được bao nhiêu tin.",
    loadFailed: "Không tải được dữ liệu thị trường: {error}",

    sections: "Mục",
    navOverview: "Tổng quan",
    navSkills: "Skill",
    navSalary: "Lương",
    navCities: "Địa điểm",
    navLevels: "Level",
    navMatch: "Điểm khớp",
    navQuality: "Chất lượng tin",
    navSources: "Nguồn",
    navCalendar: "Lịch đăng tin",

    coverage: "{covered} trên {total} tin",

    emptyRows: "Chưa có gì để hiển thị.",
    emptyDates: "Chưa tin nào có ngày đăng.",
    emptySalary: "Chưa tin nào ghi lương ở dạng parser đọc được.",

    tipJobs: "tin",
    tipPosted: "tin đăng",
    dayWithYear: "{day}, {year}",

    statPostings: "Tin tuyển dụng",
    statSources: "từ {count} nguồn",
    statMedian: "Lương trung vị (ước tính)",
    statMedianFrom: "mỗi tháng, từ {count} tin",
    statMedianNone: "chưa đọc được lương từ tin nào",
    statClean: "Tin đầy đủ",
    statCleanHint: "không thiếu mô tả, không phải tin cũ",

    skillsTitle: "Skill được tuyển nhiều nhất",
    skillsNote:
      "Mỗi tin đếm một lần theo dạng chuẩn hoá, nên “Spring Boot” và “Spring” tính là một. Mail alert của LinkedIn không kèm tag nào — đó là phần thiếu nhiều nhất ở đây.",

    salaryTitle: "Phân bố mức lương",
    salaryMedian: "trung vị / tháng",
    salaryThin: "từ {covered} trên {total} tin — chưa đủ để vẽ phân bố.",
    salaryRange:
      "Khoảng {min}–{max}/tháng. Quy đổi theo tỉ giá {rate} VND/USD (lấy ngày {date}) — số ước tính, không phải mức chào.",

    citiesTitle: "Việc nằm ở đâu",

    levelsTitle: "Tỉ lệ theo level",
    levelsNote:
      "Level suy ra từ tiêu đề và mô tả, nên tin không nói gì thì là không rõ, chứ không phải junior.",

    matchTitle: "Độ khớp với stack của bạn",
    matchNoteBefore: "Chấm lúc crawl, đối chiếu với ",
    matchNoteAfter:
      ". Corpus dồn hết về bên trái nghĩa là query tìm kiếm cần sửa, không phải thị trường tệ.",

    qualityTitle: "Chất lượng tin đăng",
    qualityNote: "Một tin có thể dính nhiều cờ, nên cộng lại sẽ vượt quá số tin trong corpus.",

    sourcesTitle: "Tin đến từ đâu",
    sourcesNote:
      "Đây là mẫu số của mọi card khác trên trang: phần nào LinkedIn không có — skill, lương, tag — là thiếu gần hết vòng này.",

    calendarTitle: "Tin đăng mỗi ngày",
    calendarNoteBefore: "Tính theo ",
    calendarNoteEm: "ngày đăng tin",
    calendarNoteAfter:
      ", không phải ngày crawl — chart “crawl mỗi ngày” ở trang Tổng quan đo thói quen của bạn, còn cái này đo thị trường.",
  },
});
