import { ns } from "../ns";

/**
 * Copy for the settings surface.
 *
 * Config keys (`crawl.max_pages`, `apply.email.dry_run`, the source keys) are
 * identifiers written verbatim into `config.local.yaml` — they are rendered
 * straight from the API and never pass through here. Only the human sentence
 * next to a key is translated.
 *
 * The email-gate copy is load-bearing: email is the one channel that can leave
 * the machine without a per-item approval, so the Vietnamese must be exactly as
 * blunt as the English about what is about to be sent and to whom. Same for the
 * "host only" note — that is a security boundary against a stolen token, not a
 * preference, and it must not read as a soft suggestion.
 */
export const settings = ns({
  en: {
    title: "Settings",
    /* Wraps `config.local.yaml`, rendered as inline <code>. */
    subtitleBefore: "Saved to",
    subtitleAfter: ", merged over the commented defaults. Delete that file to reset.",

    loadFailed: "Couldn't load settings.",
    saveFailed: "Save failed",
    saved: "Saved",

    // Crawl
    crawl: "Crawl",
    jobsPerSite: "Jobs per site",
    maxPages: "Max pages per site",
    maxPagesHint: "a ceiling, not a target",
    freshHours: "Fresh window (hours)",
    freshHoursHint: "🔥 flag below this age",
    matchScoreMin: "Min match score",
    stacks: "Stacks",
    stacksHint: "what a good job looks like",
    crawlQueries: "Scheduled keywords",
    crawlQueriesHint: "one search each at 08:30 / 18:30 — keep them short; empty = stacks joined",
    excludeKeywords: "Exclude keywords",
    excludeKeywordsHint: "drop jobs whose title or JD matches",
    commaSeparated: "comma-separated",

    // Sources — `source.key` itself is an identifier and stays verbatim.
    sources: "Sources",
    tier: "tier {tier}",

    // Apply — email
    applyEmail: "Apply — email",
    emailOff: "Email apply is off. Nothing can be sent.",
    emailDryRun: "Dry run: messages are built and shown on the Applications board, never sent.",
    emailTestBefore: "Live, but every message goes to",
    emailTestAfter: "instead of the employer.",
    emailLive:
      "All three gates are open — approved applications will be emailed to real employers from {from}.",
    noFromAddr: "(no from address set)",

    emailEnabled: "Enabled",
    emailEnabledHint: "nothing is sent at all while this is off",
    dryRun: "Dry run",
    dryRunHint: "build and record the message, never send it",
    testRecipient: "Test recipient",
    testRecipientHint: "deliver here instead of employers",
    fromAddr: "From address",
    /* Wraps `.env`, rendered as inline <code>. */
    smtpBefore: "SMTP credentials live in",
    smtpAfter: ", not here.",

    /* Wraps `jobpilot/config.local.yaml`, rendered as inline <code>. */
    lockedBefore:
      "The three gates that decide whether mail actually leaves are deliberately not editable over the network. Change them in",
    lockedAfter:
      "on the host and restart — so a stolen token cannot turn JobPilot into something that writes to employers in your name.",
    hostOnly: "host only",

    // CV
    cv: "CV",
    editMaxRounds: "Max edit rounds",
    editMaxRoundsHint: "how many times you can ask the agent to revise one CV",
  },
  vi: {
    title: "Cài đặt",
    subtitleBefore: "Lưu vào",
    subtitleAfter: ", merge đè lên bản mặc định có sẵn comment. Xoá file đó là về mặc định.",

    loadFailed: "Không tải được cài đặt.",
    saveFailed: "Lưu thất bại",
    saved: "Đã lưu",

    crawl: "Crawl",
    jobsPerSite: "Số job mỗi site",
    maxPages: "Số trang tối đa mỗi site",
    maxPagesHint: "là trần, không phải mục tiêu",
    freshHours: "Cửa sổ tin mới (giờ)",
    freshHoursHint: "mới hơn mốc này thì gắn cờ 🔥",
    matchScoreMin: "Match score tối thiểu",
    stacks: "Stacks",
    stacksHint: "job hợp gu trông như thế nào",
    crawlQueries: "Từ khoá crawl tự động",
    crawlQueriesHint: "mỗi từ một lượt tìm lúc 08:30 / 18:30 — giữ thật ngắn; để trống = ghép từ stacks",
    excludeKeywords: "Từ khoá loại trừ",
    excludeKeywordsHint: "tiêu đề hoặc JD khớp thì bỏ job đó",
    commaSeparated: "ngăn cách bằng dấu phẩy",

    sources: "Nguồn",
    tier: "tier {tier}",

    applyEmail: "Nộp đơn — email",
    emailOff: "Nộp đơn qua email đang tắt. Không có gì gửi đi được.",
    emailDryRun:
      "Dry run: thư vẫn được dựng và hiện trên board Đơn ứng tuyển, nhưng không bao giờ gửi đi.",
    emailTestBefore: "Đang chạy thật, nhưng mọi thư đều gửi tới",
    emailTestAfter: "chứ không tới nhà tuyển dụng.",
    emailLive:
      "Cả ba gate đều đang mở — đơn nào được duyệt sẽ tự động gửi email tới nhà tuyển dụng thật, từ địa chỉ {from}.",
    noFromAddr: "(chưa đặt địa chỉ gửi)",

    emailEnabled: "Bật",
    emailEnabledHint: "còn tắt thì tuyệt đối không có gì được gửi đi",
    dryRun: "Dry run",
    dryRunHint: "dựng thư và ghi lại, không gửi",
    testRecipient: "Người nhận thử",
    testRecipientHint: "gửi về đây thay vì tới nhà tuyển dụng",
    fromAddr: "Địa chỉ gửi",
    smtpBefore: "Thông tin đăng nhập SMTP nằm trong",
    smtpAfter: ", không phải ở đây.",

    lockedBefore:
      "Ba gate quyết định thư có thật sự rời khỏi máy hay không thì cố tình không cho sửa qua mạng. Muốn đổi thì sửa",
    lockedAfter:
      "ngay trên host rồi restart — để một token bị đánh cắp không thể biến JobPilot thành thứ gửi thư cho nhà tuyển dụng nhân danh bạn.",
    hostOnly: "chỉ sửa trên host",

    cv: "CV",
    editMaxRounds: "Số vòng sửa tối đa",
    editMaxRoundsHint: "được nhờ agent sửa lại một CV bao nhiêu lần",
  },
});
