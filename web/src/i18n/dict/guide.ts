import { ns } from "../ns";

/**
 * Copy for the guide surface.
 *
 * This is the page a new user reads first, so it is long-form prose rather than
 * labels: each paragraph is one key, kept whole. Splitting a paragraph into
 * clauses would force Vietnamese into English word order, and the two claims
 * this page exists to make — the agent never invents anything, nothing leaves
 * the machine without you — are exactly the sentences that must not come out
 * garbled.
 *
 * The nine status descriptions are NOT here: they live in `statuses.ts` and are
 * read through `useStatuses()`, so the funnel and the pills can never drift.
 * `email` / `portal` / `external` are channel keys from the backend and stay
 * verbatim in both languages, as do config keys (`enabled`, `dry_run`) and
 * `robots.txt`.
 */
export const guide = ns({
  en: {
    title: "How this works",
    subtitle:
      "A job moves through nine states. Six are the happy path; two are exits; one means something broke.",

    waitingOnYou: "Waiting on you right now:",

    funnelTitle: "The funnel",
    funnelHint: "top to bottom, one job at a time",
    exits: "Exits",

    shortlistTitle: "Why shortlist at all?",
    shortlistP1:
      "Tailoring costs a Claude call and a LaTeX build — about a minute and real API budget per job. A crawl can turn up dozens overnight, and most of them you can rule out from the title alone.",
    /** Bolded lead sentence of the second paragraph. */
    shortlistLead: "Shortlist is that filter.",
    shortlistP2:
      "You pick the handful worth a CV of their own; the agent only does expensive work on those. Everything else you Skip, and a re-crawl won't push it back in your face.",

    agentTitle: "What the agent cannot do",
    /** The whole point of the card, so it leads and it is bold. */
    agentLead: "It cannot add a skill you don't have.",
    agentP1:
      "The tailor plan addresses your master CV by index — it may reorder, trim or hide what is already there, and the only free text it writes is the summary, which is checked word by word against your CV's vocabulary.",
    agentP2:
      "A gap gets named in one place only: the “happy to learn X” line of the cover letter. Claiming X is not something the format can express.",

    channelsTitle: "What “Apply” does depends on the channel",

    emailLive: "Live — Apply sends the message",
    /** `{reason}` is the backend's own sentence, printed as-is. */
    emailHeld: "Held: {reason}",
    // Split around the three config keys, which are literals in both languages.
    emailLead: "The only channel that sends by itself. Three independent gates guard it —",
    emailGates:
      "— and all three ship closed. While any gate holds, Apply builds the mail and shows it to you without opening a socket, and the job stays",

    portalStatus: "Always your hand on the button",
    portalBody:
      "You get a handoff package: the URL, the tailored PDF, and every field ready to paste. Optionally the browser opens pre-filled — but nothing is ever submitted for you. When you've sent it, hit",
    portalConfirm: "Confirm submitted",

    externalStatus: "LinkedIn lands here",
    externalBody:
      "The posting lives somewhere JobPilot won't touch. You apply on the site; JobPilot just records that you did.",

    linkedinLead: "LinkedIn jobs arrive without a description.",
    linkedinBody:
      "They come from Job Alert emails in your own inbox — LinkedIn's robots.txt forbids crawling the job pages, so JobPilot never fetches them. The alert carries the title, company and location, and nothing else.",
    linkedinHint:
      "Those jobs are flagged on their detail page. Open the posting, paste the description in, and then tailor — otherwise the agent is writing against an empty brief.",
  },
  vi: {
    title: "Hệ thống này chạy thế nào",
    subtitle:
      "Một job đi qua chín trạng thái. Sáu trạng thái là đường đi chính; hai là lối ra; một nghĩa là có gì đó hỏng.",

    waitingOnYou: "Đang chờ bạn ngay lúc này:",

    funnelTitle: "Phễu",
    funnelHint: "từ trên xuống dưới, mỗi lần một job",
    exits: "Lối ra",

    shortlistTitle: "Chọn vào danh sách để làm gì?",
    shortlistP1:
      "Mỗi lần tailor tốn một lượt gọi Claude và một lần build LaTeX — khoảng một phút và ngân sách API thật cho mỗi job. Một đêm crawl có thể ra hàng chục tin, mà phần lớn nhìn tiêu đề là loại được rồi.",
    shortlistLead: "Bước chọn chính là bộ lọc đó.",
    shortlistP2:
      "Bạn chọn ra vài tin đáng để làm riêng một bản CV; agent chỉ tốn công cho những tin đó. Còn lại bấm Bỏ qua, và lần crawl sau chúng sẽ không hiện lại trước mặt bạn nữa.",

    // "không làm được", not "không được phép làm". The English is a claim about
    // what the format makes *impossible*, not about a policy someone could relax
    // later — and this card exists precisely to say that. "Không được phép"
    // reads as a permission setting, which is the opposite of the point.
    agentTitle: "Những gì agent không làm được",
    agentLead: "Nó không thể thêm một kỹ năng bạn không có.",
    agentP1:
      "Plan tailor tham chiếu Master CV theo index — nó chỉ được sắp xếp lại, cắt bớt hoặc ẩn những gì đã có sẵn; đoạn chữ tự do duy nhất nó viết là phần summary, và phần đó bị soi từng chữ so với vốn từ trong chính CV của bạn.",
    agentP2:
      "Một kỹ năng bạn còn thiếu chỉ được nhắc đúng một chỗ: dòng “sẵn sàng học X” trong cover letter. Còn nói rằng bạn đã biết X thì format này không có cách nào diễn đạt.",

    channelsTitle: "Bấm Nộp đơn thì xảy ra chuyện gì là tuỳ kênh",

    emailLive: "Đang bật — bấm Nộp đơn là email gửi đi thật",
    emailHeld: "Đang chặn: {reason}",
    emailLead: "Kênh duy nhất tự gửi đi. Có ba cổng chặn độc lập canh nó —",
    emailGates:
      "— và cả ba đều mặc định đóng. Chừng nào còn một cổng đang chặn, bấm Nộp đơn chỉ dựng sẵn email rồi hiện ra cho bạn xem, không mở một kết nối nào, và job vẫn nằm ở",

    portalStatus: "Luôn do chính tay bạn bấm",
    portalBody:
      "Bạn nhận được một gói bàn giao: link, file PDF đã tailor, và mọi trường sẵn sàng để dán. Có thể cho browser mở sẵn form đã điền trước — nhưng tuyệt đối không có chuyện nó bấm nộp thay bạn. Nộp xong rồi thì bấm",
    portalConfirm: "Xác nhận đã nộp",

    externalStatus: "LinkedIn rơi vào nhóm này",
    externalBody:
      "Tin nằm ở chỗ JobPilot không đụng tới. Bạn tự nộp trên site đó; JobPilot chỉ ghi lại là bạn đã nộp.",

    linkedinLead: "Job từ LinkedIn về mà không kèm mô tả.",
    linkedinBody:
      "Chúng đến từ email Job Alert trong hộp thư của chính bạn — robots.txt của LinkedIn cấm crawl trang tin, nên JobPilot không bao giờ fetch chúng. Email alert chỉ mang theo tiêu đề, công ty và địa điểm, hết.",
    linkedinHint:
      "Những tin đó đều được gắn cờ ở trang chi tiết. Mở tin gốc, dán mô tả vào, rồi mới tailor — không thì agent viết CV mà chẳng có đề bài nào.",
  },
});
