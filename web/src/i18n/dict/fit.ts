import { ns } from "../ns";

/**
 * The fit check: does my CV answer this posting, and is the posting itself sound.
 *
 * Its own namespace rather than more keys on `jobs` because the vocabulary is
 * a different one — HAVE/PARTIAL/MISSING, dealbreaker, concern — and it is read
 * on one card. `jobs` is already the largest namespace in the app.
 *
 * Note what the copy is careful about. This is a model's opinion about the user's
 * own career, delivered in a single word, so every string that could read as a
 * verdict on *them* is worded as a verdict on the *match*: "your CV doesn't
 * answer this posting", never "you are not qualified". And `advisory` is not
 * decoration — it is the sentence that stops a "weak" from reading as a rule.
 */
export const fit = ns({
  en: {
    title: "Fit against your CV",
    intro:
      "Have AI read this posting against your Master CV before you spend a tailor round on it.",
    assess: "Check the fit",
    reassess: "Check again",
    busy: "Reading the posting against your CV…",
    failed: "Could not assess this job",
    needsJd: "Paste the job description first — there's nothing to assess yet.",
    assessedAt: "Assessed {when}",
    advisory:
      "Advisory only. Nothing here is written to your CV, and the tailor doesn't read it — it's here so you can decide whether to run one.",

    verdictStrong: "Strong match",
    verdictFair: "Worth a look",
    verdictWeak: "Weak match",
    verdictStrongHint: "Your CV already answers the must-haves.",
    verdictFairHint: "Worth applying, but there are real gaps.",
    verdictWeakHint: "Your CV doesn't answer what this role is asking for.",

    score: "Coverage {pct}%",
    // Deliberately does NOT claim this is comparable to the job's match score.
    // It isn't: the tailor keeps whatever number its model returned, while this
    // one is recomputed from the list below. Inviting the reader to compare two
    // numbers produced by different rules is how a tooltip becomes misinformation.
    scoreHint:
      "Share of the posting's requirements your CV covers, must-haves counted double and soft skills not counted at all. Worked out from the list below, not taken from the model.",

    requirements: "What it asks for",
    covered: "{n} covered",
    partial: "{n} partial",
    missing: "{n} missing",
    // Said out loud rather than hidden: a posting that is mostly personality
    // traits is worth noticing, and the reader deserves to know why four
    // "missing" rows below did not move the percentage above.
    softNotScored: "{n} soft (not scored)",
    statusHave: "On your CV",
    statusPartial: "Close enough",
    statusMissing: "Not on your CV",
    kindMust: "must-have",
    kindNice: "nice to have",
    kindSoft: "soft",
    noRequirements: "The posting doesn't state any requirements clearly.",

    dealbreakers: "Hard blockers",
    dealbreakersHint:
      "Things no rewrite of a CV can fix — a degree, a language, a years floor, an on-site location.",
    concerns: "About the posting",
    concernsHint: "What looks off about the listing itself, not about you.",

    showAll: "Show all {n}",
    showLess: "Show less",
  },
  vi: {
    title: "Độ khớp với CV của bạn",
    intro:
      "Để AI đọc tin này đối chiếu với Master CV trước khi bạn tốn một lượt tailor cho nó.",
    assess: "Chấm độ khớp",
    reassess: "Chấm lại",
    busy: "Đang đối chiếu tin với CV của bạn…",
    failed: "Không chấm được job này",
    needsJd: "Dán mô tả công việc trước đã — chưa có gì để chấm.",
    assessedAt: "Chấm {when}",
    advisory:
      "Chỉ để tham khảo. Không có gì ở đây được ghi vào CV, và tailor cũng không đọc nó — nó ở đây để bạn quyết có nên chạy tailor hay không.",

    verdictStrong: "Khớp tốt",
    verdictFair: "Đáng cân nhắc",
    verdictWeak: "Khớp yếu",
    verdictStrongHint: "CV của bạn đã đáp ứng các yêu cầu bắt buộc.",
    verdictFairHint: "Nộp được, nhưng còn thiếu thật.",
    verdictWeakHint: "CV của bạn chưa đáp ứng được thứ vị trí này cần.",

    score: "Phủ {pct}%",
    scoreHint:
      "Tỉ lệ yêu cầu của tin mà CV bạn đáp ứng, yêu cầu bắt buộc tính gấp đôi, kỹ năng mềm không tính. Tính từ danh sách bên dưới, không lấy số của model.",

    requirements: "Tin yêu cầu gì",
    covered: "{n} có",
    partial: "{n} gần đúng",
    missing: "{n} thiếu",
    softNotScored: "{n} kỹ năng mềm (không tính điểm)",
    statusHave: "Có trong CV",
    statusPartial: "Tạm khớp",
    statusMissing: "Chưa có trong CV",
    kindMust: "bắt buộc",
    kindNice: "ưu tiên",
    kindSoft: "kỹ năng mềm",
    noRequirements: "Tin không nêu rõ yêu cầu nào.",

    dealbreakers: "Rào chặn cứng",
    dealbreakersHint:
      "Thứ viết lại CV không sửa được — bằng cấp, ngôn ngữ, số năm tối thiểu, chỗ làm onsite.",
    concerns: "Về tin tuyển dụng",
    concernsHint: "Chỗ đáng ngờ nằm ở chính tin đăng, không phải ở bạn.",

    showAll: "Xem cả {n}",
    showLess: "Thu gọn",
  },
});
