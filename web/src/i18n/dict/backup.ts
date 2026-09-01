import { ns } from "../ns";

/**
 * Copy for the backup surface.
 *
 * Two rules specific to this page. First, file names, the backup directory and
 * the `pg_restore` line are literals in both languages — they are pasted into a
 * shell, not read. Second, the warnings here are about losing data: the
 * Vietnamese is allowed to spell out consequences the English only implies
 * (restore overwrites the target database; a backup on the same disk dies with
 * the machine), but it is never allowed to say less than the English does.
 *
 * "backup", "restore", "remote", "upload", "database", "job" stay English in
 * Vietnamese — that is what the words are called out loud here, and translating
 * them buys nothing but ambiguity.
 */
export const backup = ns({
  en: {
    title: "Backup",
    backUpNow: "Back up now",
    backingUp: "Backing up...",

    // Failures
    alreadyRunning: "A backup is already running.",
    startFailed: "Could not start the backup.",
    taskFailed: "backup failed",
    dirUnreadable: "Couldn't read the backup directory.",

    // Stats
    statBackups: "Backups",
    statSize: "Total size",
    statRemote: "Off this machine",
    remoteNone: "not configured",
    filesCount: "{count} files",

    // Retention
    retentionLocal:
      "Kept {days}d or the last {last} of each kind here, whichever bites first — age alone never prunes files made on the same day.",
    retentionRemote:
      "Remote copies are kept {days}d — longer on purpose, so a bug in local pruning can't delete the surviving copies too.",
    directoryLabel: "Directory:",

    // Health banner
    healthNone: "No database backup exists yet. Everything lives on this one machine.",
    healthStale:
      "Newest backup is {days} days old — the scheduled job may not be running.",
    dumpCount: "{count} backups",
    dumpCountOne: "1 backup",
    healthNoRemote:
      "{files} here, but none off this machine. A backup on the same disk as the data doesn't survive losing the machine — which is the case it's for.",
    healthOk: "Backed up {when}, with a copy on {remote}.",

    // Restore
    restoreTitle: "Restore",
    restoreBody:
      "A backup nobody knows how to restore is a backup nobody has. Run this at least once against a scratch database, before you need it.",

    // Runs
    runsTitle: "Recent runs",
    runsEmpty:
      "Nothing has run yet. The nightly job records itself here, so an empty list after a night means it didn't fire.",
    runUploaded: "uploaded to {remote}",
    runLocalOnly: "local only",
    runPruned: "pruned {count}",
    runFailed: "failed",

    // Files
    filesTitle: "Files",
    filesEmpty: "No backups yet. The scheduled job runs nightly; the button above runs one now.",
  },
  vi: {
    title: "Sao lưu",
    backUpNow: "Sao lưu ngay",
    backingUp: "Đang sao lưu...",

    alreadyRunning: "Đang có một lượt backup chạy rồi.",
    startFailed: "Không khởi động được lượt backup.",
    taskFailed: "backup thất bại",
    dirUnreadable: "Không đọc được thư mục backup.",

    statBackups: "Bản backup",
    statSize: "Tổng dung lượng",
    statRemote: "Bản ngoài máy này",
    remoteNone: "chưa cấu hình",
    filesCount: "{count} file",

    retentionLocal:
      "Giữ {days} ngày hoặc {last} bản gần nhất của mỗi loại ở máy này, cái nào chạm trước thì cắt — chỉ tính theo tuổi thì không bao giờ dọn được các file tạo trong cùng một ngày.",
    retentionRemote:
      "Bản trên remote giữ {days} ngày — cố tình để lâu hơn, để một bug ở khâu dọn file dưới máy không xoá luôn những bản còn sót lại trên remote.",
    directoryLabel: "Thư mục:",

    healthNone:
      "Chưa có bản backup database nào. Toàn bộ dữ liệu đang nằm trên đúng một máy này — máy này mất là mất hết, không khôi phục lại được.",
    healthStale:
      "Bản backup mới nhất đã {days} ngày tuổi — nhiều khả năng job chạy định kỳ đang không chạy nữa.",
    dumpCount: "{count} bản backup",
    dumpCountOne: "1 bản backup",
    healthNoRemote:
      "Có {files} ở máy này, nhưng không có bản nào nằm ngoài máy. Backup để cùng ổ đĩa với dữ liệu thì mất máy là mất luôn cả hai — mà đó đúng là tình huống cần đến backup.",
    healthOk: "Đã backup {when}, có một bản trên {remote}.",

    restoreTitle: "Restore",
    restoreBody:
      "Bản backup mà không ai biết cách restore thì coi như không có. Chạy thử lệnh này ít nhất một lần vào một database nháp — restore GHI ĐÈ toàn bộ database đích, dữ liệu đang có trong đó mất sạch và không lấy lại được — làm trước khi thực sự cần đến nó.",

    runsTitle: "Các lượt chạy gần đây",
    runsEmpty:
      "Chưa có lượt nào chạy. Job chạy hằng đêm tự ghi lại ở đây, nên qua một đêm mà danh sách vẫn trống nghĩa là nó đã không chạy.",
    runUploaded: "đã upload lên {remote}",
    runLocalOnly: "chỉ ở máy này",
    runPruned: "đã dọn {count} file",
    runFailed: "thất bại",

    filesTitle: "File",
    filesEmpty:
      "Chưa có bản backup nào. Job định kỳ chạy hằng đêm; nút ở trên chạy ngay một lượt.",
  },
});
