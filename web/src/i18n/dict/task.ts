import { ns } from "../ns";

/**
 * The background-task banner, shared by Applications, Backup and CV Review.
 *
 * Its own namespace rather than a page's, because three pages render it and
 * whichever page "owned" the copy would be an arbitrary winner.
 */
export const task = ns({
  en: {
    queued: "Queued",
    working: "Working",
    waitingForWorker: "waiting for a free worker",
    failed: "That didn't finish",
    // The queue keeps only the last 50 tasks. Reload long after one finished and
    // the poll 404s — the task is gone, not broken, and the copy should say the
    // difference. Written by `hooks/useTask.ts`, which sets `error_kind` only.
    evicted: "Lost track of this one — the queue only keeps the 50 most recent tasks, so it has aged out. It may well have finished.",
    guardrailTitle: "Blocked: the plan claimed something unsupported",
    guardrailBody:
      "Nothing was written to your CV. Add the experience to your Master CV if it's real, or try again — the agent re-plans from scratch.",
  },
  vi: {
    queued: "Đang xếp hàng",
    working: "Đang chạy",
    waitingForWorker: "chờ một worker rảnh",
    failed: "Chưa chạy xong",
    evicted: "Không theo dõi được task này nữa — hàng đợi chỉ giữ 50 task gần nhất nên nó đã bị đẩy ra. Nhiều khả năng nó đã chạy xong.",
    guardrailTitle: "Đã chặn: bản kế hoạch nêu điều không có căn cứ",
    guardrailBody:
      "Không có gì được ghi vào CV của bạn. Nếu kinh nghiệm đó là thật thì thêm vào Master CV, hoặc thử lại — agent sẽ lập kế hoạch lại từ đầu.",
  },
});
