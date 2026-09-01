import { ns } from "../ns";

/**
 * Copy for the models surface.
 *
 * Provider and model identifiers (`claude`, `openai`, `gemini`,
 * `claude-opus-4-8`) never appear here: they are ids the CLI prints and the
 * config file stores, so translating them would break the only way to line the
 * page up with `jobpilot llm stats`. Same for `blockers`/`warnings`, which the
 * backend composes — see `jobpilot/llm/CLAUDE.md`.
 *
 * The data-handling copy (`creditNote*`, the task blurbs that say "sends your
 * whole Master CV") is deliberately blunt in both languages. This page is where
 * a user decides to hand their CV to a third-party API; a Vietnamese reader is
 * owed exactly as clear a warning as an English one.
 */
export const models = ns({
  en: {
    title: "Models",
    intro:
      "Which model runs which call, and what each one has cost. Defaults change nothing until you save.",

    // A stale OS environment variable beating .env looks exactly like a bad key.
    envShadowA: "{names} is set as an environment variable and in",
    envShadowB: ", with different values.",
    envShadowBodyA: "The environment variable wins, so your",
    envShadowBodyB: "edit is being ignored. On Windows:",
    envShadowBodyC: ", then open a new terminal.",

    // KPI row
    kpiSpend: "Recorded spend",
    kpiSpendAll: "across every recorded round",
    kpiSpendUnpriced: "{count} round(s) had no price — estimate excludes them",
    kpiCalls: "Model calls",
    kpiCallsNote: "rates appear from {count} calls per backend",
    kpiProviders: "Providers ready",
    providerNoKey: "{provider}: no key",
    allKeys: "all keys present",

    // Budget meters
    creditTitle: "Credit used and left",
    liveHint: "Ask each provider which models your key can use",
    liveOn: "Live models on",
    liveFetch: "Fetch live models",
    creditNoteA: "“Left” is your budget minus what",
    creditNoteB:
      "recorded spending — not a balance read from the vendor. Every provider’s spend endpoint needs an",
    creditNoteC:
      "key, which this app deliberately does not hold, so usage from anywhere else is invisible here.",
    noKey: "(no key)",
    modelsOffered: "{count} models offered",
    modelListUnavailable: "model list unavailable",
    used: "used",
    left: "left",
    budget: "budget $",
    unpricedRounds: "{count} round(s) ran on a model with no price on file — not counted above.",
    budgetsSave: "Budgets save with the button below.",

    // Picker
    pickerTitle: "Which model runs which call",
    saved: "Saved",
    saveFailed: "Save failed",
    badgeNoKey: "no API key",
    provider: "Provider",
    model: "Model",
    providerDefault: "provider default",
    perMtok: "per Mtok",
    cheapest: "cheapest",
    notOffered: "(not offered to your key)",

    taskTailor: "Tailor",
    taskTailorBlurb:
      "Reorders numbered CV items and writes one summary. Sends your whole Master CV.",
    taskLetter: "Cover letter",
    taskLetterBlurb: "300 words a stranger judges you on. Also sends your whole Master CV.",
    taskClassify: "Classify reply",
    taskClassifyBlurb:
      "One employer email into one of six labels. The easy one — try a cheap model here.",

    // Cost bars + table
    costTitle: "Cost so far, by backend",
    tableTitle: "Every backend that has run",
    emptyA: "No model calls recorded yet. Run",
    emptyB: "or tailor a job.",
    colTask: "Task",
    colModel: "Model",
    colCalls: "Calls",
    colCost: "Cost",
    colFirstTry: "1st try",
    colOk: "OK",
    tableNote:
      "“1st try” is the share of calls the guardrails accepted without a corrective round — the quality number. Rates are withheld below {count} calls and shown as a count instead. “—” under Cost means the model is not in the price table, which is not the same as free.",
  },
  vi: {
    title: "Mô hình",
    intro:
      "Việc nào chạy model nào, và mỗi model đã tốn bao nhiêu. Đổi xong phải bấm lưu mới có tác dụng.",

    envShadowA: "{names} đang được đặt vừa ở biến môi trường vừa trong",
    envShadowB: ", với hai giá trị khác nhau.",
    envShadowBodyA: "Biến môi trường thắng, nên thứ bạn sửa trong",
    envShadowBodyB: "đang bị bỏ qua. Trên Windows:",
    envShadowBodyC: ", rồi mở terminal mới.",

    kpiSpend: "Đã tiêu (ghi nhận được)",
    kpiSpendAll: "gộp mọi lượt gọi đã ghi",
    kpiSpendUnpriced: "{count} lượt không có giá trong bảng — số ước tính không tính phần đó",
    kpiCalls: "Lượt gọi model",
    kpiCallsNote: "đủ {count} lượt mỗi backend mới hiện tỉ lệ",
    kpiProviders: "Provider sẵn sàng",
    providerNoKey: "{provider}: chưa có key",
    allKeys: "provider nào cũng có key",

    creditTitle: "Credit đã dùng và còn lại",
    liveHint: "Hỏi từng provider xem key của bạn dùng được model nào",
    liveOn: "Đang lấy model trực tiếp",
    liveFetch: "Lấy model trực tiếp",
    creditNoteA: "“Còn lại” là ngân sách bạn tự nhập trừ đi phần",
    creditNoteB:
      "tự đo được — không phải số dư đọc từ nhà cung cấp. Endpoint chi phí của provider nào cũng đòi key",
    creditNoteC:
      "— thứ app này cố ý không giữ, nên tiền bạn tiêu ở chỗ khác thì ở đây không thấy.",
    noKey: "(chưa có key)",
    modelsOffered: "{count} model được liệt kê",
    modelListUnavailable: "không lấy được danh sách model",
    used: "đã dùng",
    left: "còn lại",
    budget: "ngân sách $",
    unpricedRounds: "{count} lượt chạy trên model chưa có giá trong bảng — không tính vào số trên.",
    budgetsSave: "Ngân sách lưu bằng nút bên dưới.",

    pickerTitle: "Việc nào chạy model nào",
    saved: "Đã lưu",
    saveFailed: "Lưu không được",
    badgeNoKey: "chưa có API key",
    provider: "Provider",
    model: "Model",
    providerDefault: "mặc định của provider",
    perMtok: "mỗi Mtok",
    cheapest: "rẻ nhất",
    notOffered: "(key của bạn không dùng được)",

    taskTailor: "Tailor",
    taskTailorBlurb:
      "Sắp xếp lại các mục CV đã đánh số và viết một đoạn summary. Gửi đi toàn bộ Master CV của bạn.",
    taskLetter: "Cover letter",
    taskLetterBlurb:
      "300 chữ mà một người lạ dùng để đánh giá bạn. Cũng gửi đi toàn bộ Master CV của bạn.",
    taskClassify: "Phân loại thư trả lời",
    taskClassifyBlurb:
      "Xếp một email nhà tuyển dụng vào một trong sáu nhãn. Việc dễ nhất — thử model rẻ ở đây.",

    costTitle: "Chi phí tới giờ, theo backend",
    tableTitle: "Mọi backend đã từng chạy",
    emptyA: "Chưa ghi nhận lượt gọi model nào. Chạy",
    emptyB: "hoặc tailor một job.",
    colTask: "Việc",
    colModel: "Model",
    colCalls: "Lượt",
    colCost: "Chi phí",
    colFirstTry: "Đạt vòng 1",
    colOk: "OK",
    tableNote:
      "“Đạt vòng 1” là tỉ lệ lượt gọi được guardrail nhận ngay, không phải gọi lại để sửa — đây là con số về chất lượng. Dưới {count} lượt thì không hiện tỉ lệ mà hiện số lượt. “—” ở cột Chi phí nghĩa là model không có trong bảng giá, khác với miễn phí.",
  },
});
