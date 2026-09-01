import { ns } from "../ns";

/**
 * Sidebar and chrome.
 *
 * "CV Studio" and "JobPilot" stay untranslated in both languages — they are
 * product names, not descriptions, and the URLs (`/cv`, `/market`) name them in
 * English regardless.
 */
export const nav = ns({
  en: {
    deck: "Deck",
    jobs: "Jobs",
    cv: "CV Studio",
    applications: "Applications",
    runs: "Runs",
    market: "Market",
    models: "Models",
    backup: "Backup",
    settings: "Settings",
    guide: "Guide",

    tagline: "Local control plane · single user",
    live: "Live",
    offline: "Offline",
    toLight: "Switch to light",
    toDark: "Switch to dark",
    language: "Language",
  },
  vi: {
    deck: "Tổng quan",
    jobs: "Việc làm",
    cv: "CV Studio",
    applications: "Đơn ứng tuyển",
    runs: "Lượt chạy",
    market: "Thị trường",
    models: "Mô hình",
    backup: "Sao lưu",
    settings: "Cài đặt",
    guide: "Hướng dẫn",

    tagline: "Control plane nội bộ · một người dùng",
    live: "Trực tuyến",
    offline: "Mất kết nối",
    toLight: "Chuyển sang nền sáng",
    toDark: "Chuyển sang nền tối",
    language: "Ngôn ngữ",
  },
});
