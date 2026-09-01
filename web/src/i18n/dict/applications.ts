import { ns } from "../ns";

/**
 * Copy for the applications surface: the board, the outcome tracker, the inbox
 * suggestions and the follow-up prompts.
 *
 * A lot of this vocabulary stays English in the Vietnamese column on purpose —
 * `email`, `portal`, `dry run`, `reply`, `interview`, `offer`, `follow-up`,
 * `ghost`, `mailbox` are what Vietnamese engineers actually say. The prose
 * around them is what gets translated.
 *
 * Not here, and deliberately: `outcome_hint`, `followup_hint`, `handoff.note`,
 * `settings.blocker`, `round_label`, `error_msg`, and every raw mail subject,
 * sender and quote. Those are backend data, not UI copy.
 */
export const applications = ns({
  en: {
    title: "Applications",
    subtitle: "Every dispatch, including the ones that never left the machine.",
    loadFailed: "Couldn't load applications.",
    empty: "Nothing dispatched yet. Approve a tailored CV, then hit Apply on the job.",
    requestFailed: "Request failed",
    cardsPerColumn: "Cards per column",

    // Board columns — what happened, not where the job is in the funnel.
    colPrepared: "Prepared",
    colPreparedHint: "Built but not sent — dry run is on",
    colYourTurn: "Your turn",
    colYourTurnHint: "Submit it yourself, then confirm",
    colSubmitted: "Submitted",
    colSubmittedHint: "Delivered",
    colFailed: "Failed",
    colFailedHint: "Needs another look",

    // Email gate banner
    gateTitle: "Email channel",
    gateOff: "off — nothing can be sent ({reason})",
    gateOffReason: "apply.email.enabled is false",
    gateDryRun: "dry run — messages are built and recorded, never sent",
    gateRedirectedPre: "live, but redirected to",
    gateRedirectedPost: "instead of employers",
    gateLive: "live — applications really go to employers from {from}",
    gateConfig: "edit config.yaml → apply.email",

    // Application card
    channelEmail: "email",
    channelPortal: "portal",
    channelExternal: "external",
    testRedirect: "(test redirect from {to})",
    letterPdfFailed: "Cover letter sent as text — the PDF didn’t build.",
    openForm: "Open form",
    iSentIt: "I sent it",
    markFailed: "Failed",
    runAgain: "Run again",
    failPrompt: "What went wrong?",

    // Outcome tracker
    outcomeReplied: "They replied",
    outcomeInterview: "Interview",
    outcomeOffer: "Offer",
    outcomeRejected: "Rejected",
    outcomeWithdrawn: "I withdrew",
    outcomeGhosted: "Ghosted",
    outcomeNone: "No outcome recorded — what happened?",
    outcomeAgain: "{label} again",
    retract: "retract",
    retractTitle: "Recorded by mistake — rewind to the previous outcome",

    // Inbox suggestions
    inboxFound: "{count} replies found in your mailbox",
    inboxFoundOne: "{count} reply found in your mailbox",
    inboxEmpty: "No new replies in your mailbox",
    inboxNote: "nothing is recorded until you say so",
    checkMail: "Check mail",
    checkMailTitle: "Read {folder} again",
    recordIt: "Record it",
    notThis: "Not this",
    nounReplies: "replies",
    confidenceThread: "certain — this answers the message we sent",
    confidenceAddress: "the address we applied to",
    confidenceDomain: "same domain we applied to",
    confidenceCompany: "guessed from the sender's domain",

    // Follow-ups
    followupsTitle: "{count} applications worth chasing",
    followupsTitleOne: "{count} application worth chasing",
    followedUp: "I followed up",
    followedUpTitle: "Advance to the next step of the cadence",
    letItGo: "Let it go",
    letItGoTitle: "Stop chasing this one",
    nounFollowups: "follow-ups",
  },
  vi: {
    title: "Đơn ứng tuyển",
    subtitle: "Mọi lần gửi đơn, kể cả những lần chưa từng rời khỏi máy.",
    loadFailed: "Không tải được danh sách đơn.",
    empty: "Chưa gửi đơn nào. Duyệt một CV đã tailor rồi bấm Apply ở tin tuyển dụng.",
    requestFailed: "Request thất bại",
    cardsPerColumn: "Thẻ mỗi cột",

    colPrepared: "Đã chuẩn bị",
    colPreparedHint: "Đã dựng nhưng chưa gửi — dry run đang bật",
    colYourTurn: "Tới lượt bạn",
    colYourTurnHint: "Bạn tự nộp, xong thì xác nhận",
    colSubmitted: "Đã nộp",
    colSubmittedHint: "Đã gửi đi",
    colFailed: "Thất bại",
    colFailedHint: "Cần xem lại",

    gateTitle: "Kênh email",
    gateOff: "đang tắt — không gửi được gì ({reason})",
    gateOffReason: "apply.email.enabled đang là false",
    gateDryRun: "dry run — thư vẫn được dựng và lưu lại, nhưng không gửi đi",
    gateRedirectedPre: "đang chạy thật, nhưng gửi về",
    gateRedirectedPost: "chứ không tới nhà tuyển dụng",
    gateLive: "đang chạy thật — đơn gửi thẳng tới nhà tuyển dụng từ {from}",
    gateConfig: "sửa config.yaml → apply.email",

    channelEmail: "email",
    channelPortal: "portal",
    channelExternal: "link ngoài",
    testRedirect: "(chuyển hướng test, gốc là {to})",
    letterPdfFailed: "Cover letter gửi dạng text — build PDF không được.",
    openForm: "Mở form",
    iSentIt: "Tôi đã nộp",
    markFailed: "Thất bại",
    runAgain: "Chạy lại",
    failPrompt: "Gặp lỗi gì?",

    outcomeReplied: "Đã reply",
    outcomeInterview: "Interview",
    outcomeOffer: "Offer",
    outcomeRejected: "Bị từ chối",
    outcomeWithdrawn: "Tôi rút đơn",
    outcomeGhosted: "Bị ghost",
    outcomeNone: "Chưa ghi kết quả — sau đó thế nào?",
    outcomeAgain: "{label} lần nữa",
    retract: "gỡ",
    retractTitle: "Ghi nhầm — quay lại kết quả trước đó",

    inboxFound: "Thấy {count} reply trong mailbox",
    inboxFoundOne: "Thấy {count} reply trong mailbox",
    inboxEmpty: "Không có reply mới trong mailbox",
    inboxNote: "chưa ghi gì cho tới khi bạn đồng ý",
    checkMail: "Kiểm tra mail",
    checkMailTitle: "Đọc lại {folder}",
    recordIt: "Ghi nhận",
    notThis: "Không phải",
    nounReplies: "reply",
    confidenceThread: "chắc chắn — đây là thư trả lời đúng mail mình gửi",
    confidenceAddress: "đúng địa chỉ mình đã nộp",
    confidenceDomain: "cùng domain với chỗ mình đã nộp",
    confidenceCompany: "đoán từ domain người gửi",

    followupsTitle: "{count} đơn nên follow-up",
    followupsTitleOne: "{count} đơn nên follow-up",
    followedUp: "Đã follow-up",
    followedUpTitle: "Chuyển sang mốc nhắc tiếp theo",
    letItGo: "Bỏ qua",
    letItGoTitle: "Ngừng nhắc đơn này",
    nounFollowups: "follow-up",
  },
});
