import { ns } from "../ns";

/**
 * Copy that more than one page needs: buttons, load/empty/error states, the
 * pager. Anything used by exactly one page belongs in that page's namespace —
 * `common` earns its name only if every key in it really is shared.
 */
export const common = ns({
  en: {
    // Actions
    save: "Save",
    saving: "Saving…",
    cancel: "Cancel",
    close: "Close",
    delete: "Delete",
    edit: "Edit",
    retry: "Retry",
    refresh: "Refresh",
    copy: "Copy",
    copied: "Copied",
    download: "Download",
    open: "Open",
    add: "Add",
    remove: "Remove",
    confirm: "Confirm",
    apply: "Apply",
    reset: "Reset",
    search: "Search",
    all: "All",
    none: "None",
    yes: "Yes",
    no: "No",
    back: "Back",

    // States
    loading: "Loading…",
    noData: "No data yet",
    loadFailed: "Couldn't load",
    error: "Error",
    unknown: "Unknown",

    // Pager
    perPage: "Per page",
    previousPage: "Previous page",
    nextPage: "Next page",
    /** "1–25 of 312 jobs" */
    range: "of {total} {noun}",
    noRows: "No {noun}",
    rows: "rows",
  },
  vi: {
    save: "Lưu",
    saving: "Đang lưu…",
    cancel: "Huỷ",
    close: "Đóng",
    delete: "Xoá",
    edit: "Sửa",
    retry: "Thử lại",
    refresh: "Tải lại",
    copy: "Chép",
    copied: "Đã chép",
    download: "Tải về",
    open: "Mở",
    add: "Thêm",
    remove: "Bỏ",
    confirm: "Xác nhận",
    apply: "Áp dụng",
    reset: "Đặt lại",
    search: "Tìm kiếm",
    all: "Tất cả",
    none: "Không có",
    yes: "Có",
    no: "Không",
    back: "Quay lại",

    loading: "Đang tải…",
    noData: "Chưa có dữ liệu",
    loadFailed: "Không tải được",
    error: "Lỗi",
    unknown: "Không rõ",

    perPage: "Mỗi trang",
    previousPage: "Trang trước",
    nextPage: "Trang sau",
    range: "trên {total} {noun}",
    noRows: "Chưa có {noun}",
    rows: "dòng",
  },
});
