import { ns } from "../ns";

/**
 * CV Studio: the editor chrome only.
 *
 * Nothing the user wrote is in here. Section titles, bullet text, the tech
 * stack, the LaTeX and the template names the server reports are CV *content*
 * or backend values — they stay exactly as they are in both languages.
 *
 * Two blocks are load-bearing rather than decorative and were translated with
 * that in mind:
 *  - `override*`: while a raw-LaTeX override is in force, editing the fields
 *    does not reach the PDF. The Vietnamese has to be as blunt as the English,
 *    because a user who misses this edits for ten minutes into a void.
 *  - `facts*` / `refused*`: the instruction box is the one place a model may
 *    write a new claim onto the Master CV, and it may only because the user's
 *    own words license it. Softening that into "hãy mô tả rõ hơn" would sell a
 *    guardrail as a UX tip.
 */
export const cv = ns({
  en: {
    // --- Page chrome -----------------------------------------------------
    masterCv: "Master CV",
    tailoredScope: "Tailored · {scope}",
    unsaved: "unsaved changes",
    rawLatexActive: "building from raw LaTeX",
    saveVersion: "Save version",
    saveFailed: "Save failed",
    compileFailed: "Compile failed",
    restoreFailed: "Restore failed",
    editStartFailed: "Could not start the edit",
    versionsNoun: "versions",
    tabFields: "Fields",
    tabLatex: "LaTeX",

    // --- An agent edit landed while the editor was dirty ------------------
    skippedLead: "The agent saved",
    skippedBody:
      "while you had unsaved edits here. Your edits were kept — load it to bring it into the editor (this discards your local edits), or keep editing and Save: that replaces it at the head of history with your version instead (v{version} stays in History either way).",
    loadVersion: "Load v{version}",

    // --- Version compare --------------------------------------------------
    compareSame: "Same version on both sides — nothing to compare.",
    compareIdentical: "v{base} and v{target} have identical structure and text.",

    // --- Section types + add row -----------------------------------------
    typeParagraph: "Paragraph",
    typeBullets: "Bullets",
    typeEducation: "Education",
    typeExperience: "Experience",
    typeProjects: "Projects",
    addSection: "Add section",

    // --- Section header summary ------------------------------------------
    wordsOne: "{n} word",
    wordsMany: "{n} words",
    itemsOne: "{n} item",
    itemsMany: "{n} items",
    entriesOne: "{n} entry",
    entriesMany: "{n} entries",

    // --- Section editor ---------------------------------------------------
    hideFromPdf: "Hide from PDF",
    showInPdf: "Show in PDF",
    deleteSection: "Delete section",
    sectionTitle: "Section title",
    sectionKey: "Key",
    sectionKeyHint: "file name",
    summaryPlaceholder: "A short professional summary…",
    labelOptional: "Label (optional)",
    datePlaceholder: "Date",
    removeItem: "Remove item",
    addItem: "Add item",
    removeEntry: "Remove entry",
    addEducation: "Add education",
    addProject: "Add project",
    addRole: "Add role",

    // --- Entry fields -----------------------------------------------------
    degree: "Degree",
    institution: "Institution",
    location: "Location",
    date: "Date",
    dashHint: "use -- for the dash",
    entryTitle: "Title",
    link: "Link",
    role: "Role",
    techStack: "Tech stack",
    optional: "optional",

    // --- Identity card ----------------------------------------------------
    identity: "Identity",
    firstName: "First name",
    lastName: "Last name",
    position: "Position",
    email: "Email",
    mobile: "Mobile",
    address: "Address",
    usernameHint: "username",
    extraLink: "Extra link",
    extraLinkHint: "label + url, shown next to the home icon",
    accentColour: "Accent colour",
    accentHint: "Awesome-CV name or #hex",
    accentUnused: "not used by the {template} template",

    // --- Template picker --------------------------------------------------
    template: "Template",
    templatesLoading: "Loading templates…",
    templatesFailed: "Could not load the template list ({error}). This CV still builds with",
    templateMissingLead: "This version names template",
    templateMissingRest: ", which this build does not ship. Pick one above before compiling.",

    // --- Markup legend ----------------------------------------------------
    formatting: "Formatting:",
    formattingRest: "Everything else is escaped — no LaTeX needed.",
    addBullet: "Add bullet",
    removeBullet: "Remove bullet",
    moveUp: "Move up",
    moveDown: "Move down",
    tagsHint: "comma-separated, order is kept",

    // --- Import from a file ----------------------------------------------
    // Blunt on purpose, like the instruction box: this is a model putting
    // words on the Master CV with no text to check them against. The three
    // `importNumbers*` / `importUnchecked` lines are three different claims;
    // do not let a translation soften "nothing was checked" into reassurance.
    importTitle: "Import from an image or PDF",
    importChoose: "Choose files",
    importDropHint: "or drop them here — PNG, JPEG, WebP or PDF. For photos, one file per page, in order.",
    importRemove: "Remove {name}",
    importLead: "The AI copies the file into the fields below.",
    importLeadEmphasis: "Nothing is saved",
    importLeadRest:
      "until you press Save version — a misread date or number would otherwise become a fact every tailored CV repeats.",
    importRead: "Read into the editor",
    importReading: "Reading…",
    importReadingHint: "One model call — about a minute, sometimes two.",
    importBlocked: "You have unsaved edits. Save them first — an import replaces what is in the editor.",
    importUnsupported: "{name} is not a PNG, JPEG, WebP or PDF. Convert it first (iPhone HEIC photos land here).",
    importTooLarge: "{name} is too large, even after shrinking. A PDF can be 10 MB, an image 3.5 MB.",
    importUndecodable: "{name} could not be opened as an image.",
    importTooMany: "At most {max} files per import.",
    importFailed: "The import failed",
    importDraftTitle: "A draft is in the editor — it is not saved.",
    importDraftBody:
      "Read it against the original, line by line, and fix what is wrong. Save version keeps it; your current Master CV stays in History either way.",
    importHeldTitle: "The file has been read — but you edited while it was being read.",
    importHeldBody:
      "Your edits were kept and the reading was not applied. Loading it replaces everything in the editor, including those edits.",
    importHeldLoad: "Load the reading",
    importHeldDrop: "Throw it away",
    importMarkup:
      "The PDF will treat these as formatting, not print them as written — the symbols disappear and the words between them are restyled. Edit them if the original means the symbol:",
    importSameTitle: "The file reads the same as your saved Master CV.",
    importSameBody: "Nothing differs, so there is nothing to save. The notes below still apply to what is saved.",
    importDismiss: "Dismiss",
    importOriginals: "Original:",
    importPage: "page {n}",
    importNumbersFound: "Every number in the draft also appears in the PDF's own text. Words were not checked.",
    importNumbersMissing: "Not found in the PDF's own text — check these numbers in the draft:",
    importUnchecked:
      "Nothing here could be checked automatically: an image, a scanned PDF, or a PDF with a page that carries no text leaves nothing to compare with. Dates, numbers and names are yours to verify.",
    importUnreadableLead: "The AI noted what it could not read:",
    importDiscard: "Discard the draft",

    // --- Instruction box --------------------------------------------------
    askForChange: "Ask for a change",
    instructionPlaceholder: "Describe the change in your own words…",
    factsLead: "New facts have to come from",
    factsEmphasis: "your",
    factsRest:
      "words. Anything the agent cannot trace back to this box or to the CV — an extra tool, a number you did not give — is refused, so state the details you want on the CV.",
    applyToMaster: "Apply to Master CV",
    working: "Working…",
    // The three prefill chips stay English in BOTH languages, and that is a
    // deliberate exception to "translate everything the user reads".
    //
    // Clicking a chip fills the textarea, and that text is not chrome — it goes
    // to the model as the instruction, and for an `add_entry` the cited
    // `source_quote` must literally appear in it, so the user's phrasing lands
    // verbatim on the CV. A Vietnamese chip against an English Master CV writes
    // a Vietnamese bullet into an English document.
    //
    // Two guardrail notes behind this. `textnorm.quote_appears_in` does handle
    // Vietnamese correctly and fails closed. But `guard._NUMBER_WORDS` is
    // English-only and its `_WORD_RE` is `[a-zA-Z]+`, which cannot match "mười
    // hai" or "gấp đôi" — so an invented figure written as a Vietnamese number
    // *word* (digits are still caught) slips that one check. Nudging users into
    // Vietnamese instructions makes that pre-existing gap far easier to reach.
    //
    // Nothing stops the user typing Vietnamese; the box accepts it. We just
    // don't demonstrate it. Flip these three lines if the Master CV is Vietnamese.
    example1: "Rewrite my summary to lead with backend work",
    example2: "Merge the last two bullets of my ACME job",
    example3: "Add a project: JobPilot, a job crawler I built with FastAPI and React",
    refusedTitle: "Refused — nothing was changed.",
    refusedGuard:
      "This is the anti-fabrication guard, not a crash. Say the missing detail in your own words and it will go through.",
    noChangeTitle: "Nothing changed — no new version.",
    noChangeBody:
      "Either the instruction didn't give enough to act on without inventing something, or the result matched what's already there.",
    agentNoted: "The agent noted:",

    // --- PDF preview ------------------------------------------------------
    preview: "Preview",
    previewFrame: "CV preview",
    previewFull: "CV preview, full screen",
    closePreview: "Close preview",
    fullScreen: "Full screen",
    openNewTab: "Open in a new tab",
    pagesOne: "{n} page",
    pagesMany: "{n} pages",
    fitsOnePage: "Fits on one page",
    shouldFitOnePage: "A CV should fit on one page",
    compile: "Compile",
    compiling: "Compiling…",
    buildFailed: "LaTeX build failed",
    staleBuild: "Showing the last compiled build — save and compile to see your edits.",
    runningXelatex: "Running xelatex (tectonic)…",
    hitCompile: "Hit Compile to render the PDF.",
    needsEngine: "Needs tectonic installed on the host — the first build downloads the TeX packages it uses.",

    // --- ATS panel --------------------------------------------------------
    atsNotCheckedLead: "Readability not checked — no PDF text extractor installed. Run",
    atsNotCheckedRest: "to see what an ATS would read.",
    atsBadOne: "{n} thing an ATS can't read",
    atsBadMany: "{n} things an ATS can't read",
    atsOk: "An ATS can read this CV",
    atsChars: "{n} chars",
    atsEngine: "read by {engine}",
    atsKeywords: "Job keywords a parser can find in your PDF",
    atsKeywordsNote:
      "Struck-through keywords aren't in your CV. Only add one if it's genuinely true of you.",

    // --- Raw LaTeX --------------------------------------------------------
    rawLatex: "Raw LaTeX",
    latexLoadFailed: "Could not load the LaTeX.",
    revertToGenerated: "Revert to generated",
    revertHint: "Build from the structured document again",
    saveLatex: "Save LaTeX",
    latexActionFailed: "Failed",
    differsFromGenerated: "Differs from the generated file",
    latexCounts: "{lines} lines · {chars} chars",
    restoreFile: "Restore this file from the document",
    unsavedLatex: "Unsaved LaTeX edits.",
    generatedLead: "This is what the fields above render to. Saving it makes the build follow",
    generatedEmphasis: "this text",
    generatedRest: "instead — useful for the things the editor has no field for.",
    overrideLead:
      "The PDF is built from this LaTeX, not from the fields above — nothing parses",
    overrideRest:
      "back into the structured document, so edits up there will NOT reach the PDF until you revert. Version history keeps both.",

    // --- Version history --------------------------------------------------
    history: "History",
    versionCountOne: "{n} version",
    versionCountMany: "{n} versions",
    noVersions: "No versions yet.",
    currentVersion: "current",
    restore: "Restore",
    compareFrom: "Compare from",
    compareTo: "Compare to",
    compare: "Compare",
  },
  vi: {
    masterCv: "Master CV",
    tailoredScope: "Bản tailored · {scope}",
    unsaved: "chưa lưu",
    rawLatexActive: "đang build từ LaTeX thô",
    saveVersion: "Lưu version",
    saveFailed: "Lưu thất bại",
    compileFailed: "Compile thất bại",
    restoreFailed: "Khôi phục thất bại",
    editStartFailed: "Không khởi động được lượt sửa",
    versionsNoun: "version",
    tabFields: "Trường dữ liệu",
    tabLatex: "LaTeX",

    skippedLead: "Agent đã lưu",
    skippedBody:
      "trong lúc bạn còn sửa dở ở đây. Phần bạn sửa vẫn được giữ nguyên — bấm nạp để đưa version đó vào editor (thao tác này bỏ các sửa đổi cục bộ của bạn), hoặc cứ sửa tiếp rồi bấm Lưu: bản của bạn sẽ nằm ở đầu lịch sử thay cho nó (v{version} vẫn còn trong History dù chọn cách nào).",
    loadVersion: "Nạp v{version}",

    compareSame: "Hai bên là cùng một version — không có gì để so.",
    compareIdentical: "v{base} và v{target} giống hệt nhau về cấu trúc lẫn nội dung.",

    typeParagraph: "Đoạn văn",
    typeBullets: "Gạch đầu dòng",
    typeEducation: "Học vấn",
    typeExperience: "Kinh nghiệm",
    typeProjects: "Dự án",
    addSection: "Thêm mục",

    wordsOne: "{n} từ",
    wordsMany: "{n} từ",
    itemsOne: "{n} dòng",
    itemsMany: "{n} dòng",
    entriesOne: "{n} entry",
    entriesMany: "{n} entry",

    hideFromPdf: "Ẩn khỏi PDF",
    showInPdf: "Hiện trong PDF",
    deleteSection: "Xoá mục này",
    sectionTitle: "Tiêu đề mục",
    sectionKey: "Key",
    sectionKeyHint: "tên file",
    summaryPlaceholder: "Vài dòng giới thiệu ngắn…",
    labelOptional: "Nhãn (không bắt buộc)",
    datePlaceholder: "Thời gian",
    removeItem: "Bỏ dòng này",
    addItem: "Thêm dòng",
    removeEntry: "Bỏ entry này",
    addEducation: "Thêm học vấn",
    addProject: "Thêm dự án",
    addRole: "Thêm vị trí",

    degree: "Bằng cấp",
    institution: "Trường",
    location: "Nơi chốn",
    date: "Thời gian",
    dashHint: "dùng -- cho dấu gạch ngang",
    entryTitle: "Tiêu đề",
    link: "Link",
    role: "Vai trò",
    techStack: "Tech stack",
    optional: "không bắt buộc",

    identity: "Thông tin cá nhân",
    firstName: "Tên",
    lastName: "Họ",
    position: "Vị trí ứng tuyển",
    email: "Email",
    mobile: "Điện thoại",
    address: "Địa chỉ",
    usernameHint: "username",
    extraLink: "Link thêm",
    extraLinkHint: "nhãn + url, hiện cạnh icon nhà",
    accentColour: "Màu nhấn",
    accentHint: "tên màu Awesome-CV hoặc mã #hex",
    accentUnused: "template {template} không dùng tới",

    template: "Template",
    templatesLoading: "Đang tải danh sách template…",
    templatesFailed:
      "Không tải được danh sách template ({error}). CV này vẫn build được bằng",
    templateMissingLead: "Version này khai template",
    templateMissingRest:
      " — bản build hiện tại không có template đó. Chọn một cái ở trên trước khi compile.",

    formatting: "Định dạng:",
    formattingRest: "Còn lại đều được escape — không cần viết LaTeX.",
    addBullet: "Thêm gạch đầu dòng",
    removeBullet: "Bỏ gạch đầu dòng này",
    moveUp: "Đưa lên trên",
    moveDown: "Đưa xuống dưới",
    tagsHint: "cách nhau bằng dấu phẩy, giữ nguyên thứ tự",

    // --- Nhập từ file -----------------------------------------------------
    importTitle: "Nhập từ ảnh hoặc PDF",
    importChoose: "Chọn file",
    importDropHint: "hoặc thả vào đây — PNG, JPEG, WebP hay PDF. Ảnh chụp thì mỗi trang một file, đúng thứ tự.",
    importRemove: "Bỏ {name}",
    importLead: "AI chép nội dung file vào các ô bên dưới.",
    importLeadEmphasis: "Chưa có gì được lưu",
    importLeadRest:
      "cho tới khi bạn bấm Lưu version — đọc nhầm một ngày tháng hay một con số là mọi CV tailor về sau lặp lại đúng chỗ sai đó.",
    importRead: "Đọc vào editor",
    importReading: "Đang đọc…",
    importReadingHint: "Một lượt gọi model — khoảng một phút, có khi hai.",
    importBlocked: "Bạn đang có chỉnh sửa chưa lưu. Lưu trước đã — nhập file sẽ thay toàn bộ nội dung trong editor.",
    importUnsupported: "{name} không phải PNG, JPEG, WebP hay PDF. Hãy đổi định dạng trước (ảnh HEIC của iPhone rơi vào đây).",
    importTooLarge: "{name} quá lớn, kể cả sau khi thu nhỏ. PDF tối đa 10 MB, ảnh tối đa 3,5 MB.",
    importUndecodable: "Không mở được {name} như một tấm ảnh.",
    importTooMany: "Mỗi lần nhập tối đa {max} file.",
    importFailed: "Nhập file thất bại",
    importDraftTitle: "Bản nháp đang nằm trong editor — chưa lưu.",
    importDraftBody:
      "Hãy đối chiếu từng dòng với bản gốc và sửa chỗ sai. Bấm Lưu version thì nó mới được giữ; Master CV hiện tại vẫn còn trong Lịch sử dù bạn chọn thế nào.",
    importHeldTitle: "Đã đọc xong file — nhưng bạn đã sửa trong lúc nó đang đọc.",
    importHeldBody:
      "Phần bạn sửa được giữ nguyên, bản đọc chưa được áp vào. Nạp nó sẽ thay toàn bộ nội dung trong editor, kể cả phần bạn vừa sửa.",
    importHeldLoad: "Nạp bản đọc",
    importHeldDrop: "Bỏ đi",
    importMarkup:
      "PDF sẽ coi những chỗ này là định dạng chứ không in nguyên văn — ký hiệu biến mất, chữ ở giữa bị đổi kiểu. Nếu bản gốc thật sự có ký hiệu đó thì hãy sửa lại:",
    importSameTitle: "File đọc ra giống hệt Master CV đang lưu.",
    importSameBody: "Không có gì khác nên không có gì để lưu. Các ghi chú bên dưới vẫn đúng với bản đang lưu.",
    importDismiss: "Đóng",
    importOriginals: "Bản gốc:",
    importPage: "trang {n}",
    importNumbersFound: "Mọi con số trong bản nháp đều có trong phần chữ của chính file PDF. Phần chữ thì chưa được kiểm.",
    importNumbersMissing: "Không thấy trong phần chữ của file PDF — hãy kiểm các con số này trong bản nháp:",
    importUnchecked:
      "Không kiểm tự động được gì ở đây: ảnh, PDF scan, hay PDF có một trang không mang chữ thì không có gì để so. Ngày tháng, con số và tên riêng là phần bạn phải tự soát.",
    importUnreadableLead: "AI ghi lại những chỗ nó không đọc được:",
    importDiscard: "Bỏ bản nháp",

    askForChange: "Nhờ sửa giúp",
    instructionPlaceholder: "Mô tả thay đổi bạn muốn, bằng lời của bạn…",
    factsLead: "Dữ kiện mới phải đến từ lời của",
    factsEmphasis: "chính bạn",
    factsRest:
      "— thứ gì agent không truy ngược được về ô này hoặc về CV, kiểu một công nghệ lạ hay một con số bạn chưa đưa, đều bị từ chối. Nên hãy nói thẳng chi tiết bạn muốn có trên CV.",
    applyToMaster: "Áp dụng vào Master CV",
    working: "Đang chạy…",
    // Ba chip này KHÔNG dịch — xem chú thích ở khối `en` phía trên.
    example1: "Rewrite my summary to lead with backend work",
    example2: "Merge the last two bullets of my ACME job",
    example3: "Add a project: JobPilot, a job crawler I built with FastAPI and React",
    refusedTitle: "Đã từ chối — không có gì bị thay đổi.",
    refusedGuard:
      "Đây là guard chống bịa, không phải lỗi hệ thống. Nói chi tiết còn thiếu bằng lời của bạn thì nó sẽ đi qua.",
    noChangeTitle: "Không có gì đổi — không ghi version mới.",
    noChangeBody:
      "Hoặc câu lệnh chưa đủ dữ kiện để làm mà không phải bịa, hoặc kết quả trùng với thứ đã có sẵn.",
    agentNoted: "Agent ghi chú:",

    preview: "Preview",
    previewFrame: "Preview CV",
    previewFull: "Preview CV, toàn màn hình",
    closePreview: "Đóng preview",
    fullScreen: "Toàn màn hình",
    openNewTab: "Mở ở tab mới",
    pagesOne: "{n} trang",
    pagesMany: "{n} trang",
    fitsOnePage: "Gọn trong một trang",
    shouldFitOnePage: "CV nên gói gọn trong một trang",
    compile: "Compile",
    compiling: "Đang compile…",
    buildFailed: "Build LaTeX thất bại",
    staleBuild: "Đang hiện bản build gần nhất — lưu rồi compile để thấy phần vừa sửa.",
    runningXelatex: "Đang chạy xelatex (tectonic)…",
    hitCompile: "Bấm Compile để render PDF.",
    needsEngine: "Cần cài tectonic trên máy chủ — lần build đầu sẽ tải các gói TeX nó dùng.",

    atsNotCheckedLead: "Chưa kiểm tra khả năng đọc — máy chưa cài bộ trích text từ PDF. Chạy",
    atsNotCheckedRest: "để xem một ATS đọc được những gì.",
    atsBadOne: "{n} thứ ATS không đọc được",
    atsBadMany: "{n} thứ ATS không đọc được",
    atsOk: "ATS đọc được CV này",
    atsChars: "{n} ký tự",
    atsEngine: "đọc bằng {engine}",
    atsKeywords: "Từ khoá của JD mà parser tìm thấy trong PDF của bạn",
    atsKeywordsNote:
      "Từ khoá bị gạch ngang là thứ chưa có trong CV. Chỉ thêm vào nếu nó đúng là của bạn.",

    rawLatex: "LaTeX thô",
    latexLoadFailed: "Không tải được LaTeX.",
    revertToGenerated: "Quay về bản sinh tự động",
    revertHint: "Build lại từ tài liệu có cấu trúc",
    saveLatex: "Lưu LaTeX",
    latexActionFailed: "Thất bại",
    differsFromGenerated: "Khác với file sinh tự động",
    latexCounts: "{lines} dòng · {chars} ký tự",
    restoreFile: "Lấy lại file này từ tài liệu",
    unsavedLatex: "Có sửa đổi LaTeX chưa lưu.",
    generatedLead:
      "Đây là kết quả render của các trường phía trên. Lưu lại thì bản build sẽ đi theo",
    generatedEmphasis: "chính đoạn text này",
    generatedRest: "— tiện cho những thứ editor chưa có ô nhập.",
    overrideLead:
      "PDF đang được build từ đoạn LaTeX này, KHÔNG phải từ các trường phía trên — không có gì parse",
    overrideRest:
      "ngược lại thành tài liệu có cấu trúc, nên sửa các trường ở trên sẽ KHÔNG tới được PDF cho tới khi bạn quay về bản sinh tự động. Lịch sử version giữ cả hai.",

    history: "Lịch sử",
    versionCountOne: "{n} version",
    versionCountMany: "{n} version",
    noVersions: "Chưa có version nào.",
    currentVersion: "hiện tại",
    restore: "Khôi phục",
    compareFrom: "So sánh từ",
    compareTo: "So sánh với",
    compare: "So sánh",
  },
});
