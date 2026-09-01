import { ns } from "../ns";

/**
 * The nine job states, described once.
 *
 * `label` is new here. The pill used to render `status.toLowerCase()` straight
 * from the database, which is honest but unreadable to a Vietnamese user, so VI
 * gets a translated pill. The raw state name never disappears — it leads the
 * tooltip in both languages, because `SUBMITTED` is the word that appears in the
 * API, the CLI and `PHASES.md`, and a UI that hides it makes those unsearchable.
 */
export const statuses = ns({
  en: {
    DISCOVERED: "discovered",
    SHORTLISTED: "shortlisted",
    TAILORING: "tailoring",
    REVIEW: "review",
    APPROVED: "approved",
    SUBMITTING: "submitting",
    SUBMITTED: "submitted",
    FAILED: "failed",
    SKIPPED: "skipped",

    DISCOVERED_meaning: "A crawl found this job. Nobody has judged it yet.",
    DISCOVERED_next: "Read the title and company, then Shortlist it or Skip it.",
    SHORTLISTED_meaning: "You decided this one is worth a CV of its own.",
    SHORTLISTED_next:
      "Hit Tailor CV — that's when the agent starts spending time and API budget.",
    TAILORING_meaning:
      "Claude is reworking your master CV against this job description — reordering and trimming what you already have, never inventing anything.",
    TAILORING_next: "Wait. This takes roughly a minute, including the LaTeX build.",
    REVIEW_meaning: "The tailored CV is built and waiting for your eyes.",
    REVIEW_next:
      "Read the diff and the gap report, then Approve — or send an edit instruction and let it try again.",
    APPROVED_meaning: "You signed off on the CV. Nothing has been sent yet.",
    APPROVED_next: "Hit Apply. What happens then depends on the channel (see below).",
    SUBMITTING_meaning: "The dispatcher is sending the application right now.",
    SUBMITTING_next: "Wait — this is the one state that touches the outside world.",
    SUBMITTED_meaning:
      "The application is out: sent by email, or you confirmed you submitted it yourself.",
    SUBMITTED_next: "Nothing. It's in their hands now.",
    FAILED_meaning:
      "Something broke — usually the mail server refusing, or a portal that changed.",
    FAILED_next: "Read the error on the Applications board, fix it, and retry.",
    SKIPPED_meaning:
      "You passed on it. It stays in the database so a re-crawl won't resurface it.",
    SKIPPED_next: "Nothing, unless you change your mind.",
  },
  vi: {
    DISCOVERED: "mới tìm thấy",
    SHORTLISTED: "đã chọn",
    TAILORING: "đang tailor",
    REVIEW: "chờ duyệt",
    APPROVED: "đã duyệt",
    SUBMITTING: "đang gửi",
    SUBMITTED: "đã nộp",
    FAILED: "thất bại",
    SKIPPED: "đã bỏ qua",

    DISCOVERED_meaning: "Một lượt crawl tìm ra tin này. Chưa ai đánh giá nó.",
    DISCOVERED_next: "Đọc tiêu đề và công ty, rồi Chọn vào danh sách hoặc Bỏ qua.",
    SHORTLISTED_meaning: "Bạn thấy tin này đáng để làm riêng một bản CV.",
    SHORTLISTED_next:
      "Bấm Tailor CV — từ lúc đó agent mới bắt đầu tốn thời gian và ngân sách API.",
    TAILORING_meaning:
      "Claude đang chỉnh Master CV của bạn theo mô tả công việc — sắp xếp lại và cắt bớt những gì bạn đã có, tuyệt đối không bịa thêm.",
    TAILORING_next: "Chờ chút. Mất khoảng một phút, tính cả bước build LaTeX.",
    REVIEW_meaning: "Bản CV tailored đã build xong và đang chờ bạn xem.",
    REVIEW_next:
      "Đọc phần diff và báo cáo gap, rồi Duyệt — hoặc gửi một câu lệnh chỉnh sửa để nó làm lại.",
    APPROVED_meaning: "Bạn đã duyệt bản CV. Chưa có gì được gửi đi cả.",
    APPROVED_next: "Bấm Nộp đơn. Chuyện xảy ra sau đó tuỳ vào kênh nộp (xem bên dưới).",
    SUBMITTING_meaning: "Dispatcher đang gửi đơn ứng tuyển ngay lúc này.",
    SUBMITTING_next: "Chờ — đây là trạng thái duy nhất chạm ra thế giới bên ngoài.",
    SUBMITTED_meaning:
      "Đơn đã đi: gửi qua email, hoặc bạn đã xác nhận là tự nộp xong.",
    SUBMITTED_next: "Không cần làm gì. Giờ là chuyện của nhà tuyển dụng.",
    FAILED_meaning:
      "Có gì đó hỏng — thường là máy chủ mail từ chối, hoặc portal đã đổi giao diện.",
    FAILED_next: "Đọc lỗi ở bảng Đơn ứng tuyển, sửa, rồi thử lại.",
    SKIPPED_meaning:
      "Bạn đã bỏ qua tin này. Nó vẫn nằm trong database để lần crawl sau không hiện lại.",
    SKIPPED_next: "Không cần làm gì, trừ khi bạn đổi ý.",
  },
});
