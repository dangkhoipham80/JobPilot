import { ns } from "../ns";

/**
 * The /companies page and the HR-contact card on a job.
 *
 * "HR" stays "HR" in both languages: Vietnamese job ads say "HR" and "nhân sự"
 * interchangeably, and the people this app records introduce themselves as HR.
 */
export const companies = ns({
  en: {
    title: "Companies",
    intro:
      "Every employer in your corpus, and the people you know at them. Rows appear on their own as jobs arrive — you only add the contacts.",
    search: "Search an employer",
    orderApplied: "Most applied to",
    orderJobs: "Most postings",
    orderName: "By name",
    onlyWithContacts: "Only with contacts",
    noun: "companies",
    empty: "No employers yet. They appear as soon as a crawl or a pasted job brings one in.",
    emptyFiltered: "No employer matches that.",
    loadFailed: "Couldn't load companies.",

    add: "Track an employer",
    addPlaceholder: "Company name",
    addHint: "For an employer you want on file before a posting from them lands.",
    addFailed: "Couldn't add that employer.",

    jobsCount: "{count} postings",
    /* The `…One` pair is this app's plural convention (see applications.ts):
       Vietnamese does not inflect for number, so the vi side of each pair is
       the same string, and only English needs the second form. */
    jobsCountOne: "{count} posting",
    appliedCount: "{count} applied",
    contactsCount: "{count} contacts",
    contactsCountOne: "{count} contact",
    /* Said out loud because it is the one thing on the page a person might
       disagree with: two spellings that were folded into one row. */
    foldedAs: "Filed under “{key}”",

    rename: "Rename",
    renameHint: "Display only — which jobs and contacts belong here is decided by the folded name.",
    renameFailed: "Couldn't rename.",

    contacts: "HR contacts",
    noContacts: "Nobody on file here yet.",
    addContact: "Add a contact",
    contactName: "Name",
    contactPhone: "Phone",
    contactEmail: "Email",
    contactNote: "Note",
    contactNoteHint: "Where you met, which role they cover, anything you'd forget.",
    saveContact: "Save",
    contactFailed: "Couldn't save that contact.",
    deleteContact: "Remove this contact",
    confirmDeleteContact: "Remove {name} from {company}?",

    postings: "Postings",
    postingsTruncated: "Showing the {count} most recent — the Jobs page has the rest.",
    noPostings: "No postings from this employer in the corpus.",

    /* The offer, on a job page. Deliberately worded as an offer: the button
       fills a field, it never sends anything. */
    offerTitle: "HR contacts at {company}",
    offerUse: "Use as apply target",
    offerNoEmail: "no email on file",
    offerHint:
      "Filling the apply target sends nothing — you still choose when to apply. It does switch this job to the email channel, so applying will compose a mail rather than hand you a link.",
    offerManage: "Manage contacts",
  },
  vi: {
    title: "Công ty",
    intro:
      "Mọi nhà tuyển dụng trong kho tin của bạn, kèm những người bạn quen ở đó. Dòng công ty tự xuất hiện khi có job mới — bạn chỉ cần thêm người liên hệ.",
    search: "Tìm nhà tuyển dụng",
    orderApplied: "Nộp nhiều nhất",
    orderJobs: "Nhiều tin nhất",
    orderName: "Theo tên",
    onlyWithContacts: "Chỉ nơi có liên hệ",
    noun: "công ty",
    empty: "Chưa có nhà tuyển dụng nào. Chúng xuất hiện ngay khi một lượt crawl hoặc một tin dán tay mang về.",
    emptyFiltered: "Không có nhà tuyển dụng nào khớp.",
    loadFailed: "Không tải được danh sách công ty.",

    add: "Theo dõi một nhà tuyển dụng",
    addPlaceholder: "Tên công ty",
    addHint: "Dùng khi bạn muốn lưu sẵn một nơi trước cả khi có tin tuyển dụng của họ.",
    addFailed: "Không thêm được nhà tuyển dụng đó.",

    jobsCount: "{count} tin",
    jobsCountOne: "{count} tin",
    appliedCount: "đã nộp {count}",
    contactsCount: "{count} liên hệ",
    contactsCountOne: "{count} liên hệ",
    foldedAs: "Gộp theo “{key}”",

    rename: "Đổi tên",
    renameHint: "Chỉ đổi cách hiển thị — job và liên hệ thuộc về đâu là do tên đã gộp quyết định.",
    renameFailed: "Không đổi tên được.",

    contacts: "Liên hệ HR",
    noContacts: "Chưa lưu ai ở đây.",
    addContact: "Thêm liên hệ",
    contactName: "Tên",
    contactPhone: "Điện thoại",
    contactEmail: "Email",
    contactNote: "Ghi chú",
    contactNoteHint: "Gặp ở đâu, phụ trách mảng nào, thứ gì bạn sẽ quên.",
    saveContact: "Lưu",
    contactFailed: "Không lưu được liên hệ.",
    deleteContact: "Xoá liên hệ này",
    confirmDeleteContact: "Xoá {name} khỏi {company}?",

    postings: "Tin tuyển dụng",
    postingsTruncated: "Đang hiện {count} tin mới nhất — phần còn lại ở trang Việc làm.",
    noPostings: "Chưa có tin nào của nhà tuyển dụng này.",

    offerTitle: "Liên hệ HR ở {company}",
    offerUse: "Dùng làm nơi nộp",
    offerNoEmail: "chưa có email",
    offerHint:
      "Điền nơi nộp thì chưa gửi gì cả — bạn vẫn là người quyết định lúc nộp. Nhưng job này sẽ chuyển sang kênh email, nên lúc nộp nó soạn mail chứ không đưa link cho bạn tự mở.",
    offerManage: "Quản lý liên hệ",
  },
});
