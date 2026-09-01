import { ns } from "../ns";

/**
 * CV Review: the tailored PDF, the structural diff, the gap report.
 *
 * Two things in this namespace are deliberately *not* softened in Vietnamese.
 * `missingNote` and `editHint` are the user-facing face of SKILL.md §0 — they
 * exist to say plainly that a requirement was left off the CV because claiming
 * it would be a lie. A vaguer, politer Vietnamese phrasing would quietly turn
 * the guardrail into marketing copy, which is the exact failure the guardrail
 * is for.
 *
 * The diff *content* (`section.title`, `section.notes`, `plan.changes`) is CV
 * text and agent output arriving from the API — never routed through here. The
 * note strings in particular come from `tailor/diff.py` (`TAILOR_LABELS` vs
 * `VERSION_LABELS`); translating them client-side would fork that shared
 * machinery into a second, drifting copy.
 */
export const review = ns({
  en: {
    // Page chrome
    backToJob: "Back to job",
    loadJobFailed: "Couldn't load this job.",
    requestFailed: "Request failed",
    applicationsBoard: "Applications board →",

    // Header actions
    openInStudio: "Open in CV Studio",
    tailor: "Tailor",
    retailor: "Re-tailor",
    skip: "Skip",
    /** Submitting an application — not `common.apply` ("apply a change"). */
    applyJob: "Apply",
    approve: "Approve",
    /** Version line: "v3 · edit round 2". */
    editRound: "edit round {round}",

    // PDF pane
    tailoredCv: "Tailored CV",
    pdfUnavailable: "PDF not available",
    pageCountOne: "{count} page",
    pageCountMany: "{count} pages",
    pagesFit: "Fits on one page",
    pagesOver: "A CV should fit on one page — hide a section",

    // Empty state
    notTailoredBody:
      "Not tailored yet. Tailoring reorders and trims your Master CV for this posting — it never adds a skill you don't have. Takes about a minute: a Claude call plus a LaTeX build. It runs in the background, so you can go and do something else.",
    tailorForJob: "Tailor for this job",
    tailoring: "Tailoring…",

    // Ask-for-a-change box
    askForChange: "Ask for a change",
    roundN: "round {round}",
    editPlaceholder: "e.g. shorten the summary, put Food Forum last, lead with Docker",
    editHint:
      "The agent re-plans within the same rules — it will refuse anything that would claim experience you don't have.",
    retailoring: "Re-tailoring…",
    send: "Send",

    // Diff panel
    whatChanged: "What changed",
    sectionsChanged: "{changed} of {total} sections",
    sectionOrder: "Section order",
    unchangedList: "Unchanged: {list}",
    status_rewritten: "Rewritten",
    status_trimmed: "Trimmed",
    status_expanded: "Added",
    status_hidden: "Hidden",
    status_reordered: "Reordered",
    status_unchanged: "Unchanged",

    // Gap report
    requirements: "Requirements",
    gapCountOne: "{count} gap",
    gapCountMany: "{count} gaps",
    noGaps: "no gaps",
    noRequirements: "No requirements were extracted from this posting.",
    must: "must",
    req_HAVE: "in your CV",
    req_PARTIAL: "related experience",
    req_MISSING: "not in your CV",
    missingNote:
      "These were deliberately left off the CV — claiming them would be untrue. Decide whether to learn them, mention willingness to learn in the cover letter, or skip this job.",
  },
  vi: {
    backToJob: "Quay lại job",
    loadJobFailed: "Không tải được job này.",
    requestFailed: "Request thất bại",
    applicationsBoard: "Bảng đơn ứng tuyển →",

    openInStudio: "Mở trong CV Studio",
    tailor: "Tailor",
    retailor: "Tailor lại",
    skip: "Bỏ qua",
    applyJob: "Nộp đơn",
    approve: "Duyệt",
    editRound: "vòng sửa {round}",

    tailoredCv: "CV đã tailor",
    pdfUnavailable: "Chưa có PDF",
    pageCountOne: "{count} trang",
    pageCountMany: "{count} trang",
    pagesFit: "Gọn trong 1 trang",
    pagesOver: "CV nên gọn trong 1 trang — ẩn bớt một section đi",

    notTailoredBody:
      "Chưa tailor. Tailor sẽ sắp xếp lại và rút gọn Master CV cho đúng tin này — không bao giờ thêm skill bạn không có. Mất khoảng một phút: một lần gọi Claude cộng một lần build LaTeX. Nó chạy nền, bạn cứ làm việc khác.",
    tailorForJob: "Tailor cho job này",
    tailoring: "Đang tailor…",

    askForChange: "Yêu cầu sửa",
    roundN: "vòng {round}",
    editPlaceholder: "vd: rút gọn phần summary, đẩy Food Forum xuống cuối, ưu tiên Docker",
    editHint:
      "Agent lập kế hoạch lại trong đúng bộ luật cũ — nó sẽ từ chối mọi yêu cầu khiến CV nhận kinh nghiệm bạn không có.",
    retailoring: "Đang tailor lại…",
    send: "Gửi",

    whatChanged: "Đã đổi những gì",
    sectionsChanged: "{changed}/{total} section",
    sectionOrder: "Thứ tự section",
    unchangedList: "Giữ nguyên: {list}",
    status_rewritten: "Viết lại",
    status_trimmed: "Rút gọn",
    status_expanded: "Thêm mới",
    status_hidden: "Đã ẩn",
    status_reordered: "Đổi thứ tự",
    status_unchanged: "Giữ nguyên",

    requirements: "Yêu cầu của JD",
    gapCountOne: "{count} gap",
    gapCountMany: "{count} gap",
    noGaps: "không có gap",
    noRequirements: "Không trích được yêu cầu nào từ tin này.",
    must: "bắt buộc",
    req_HAVE: "có trong CV",
    req_PARTIAL: "có kinh nghiệm liên quan",
    req_MISSING: "không có trong CV",
    missingNote:
      "Những mục này cố ý bị bỏ khỏi CV — nhận là có thì thành khai man. Bạn tự quyết: học thêm, ghi trong cover letter là sẵn sàng học, hoặc bỏ job này.",
  },
});
