# `web/src/i18n/` — song ngữ Việt/Anh cho dashboard

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc,
> bẫy React/chart ở `web/src/CLAUDE.md`.

**Mặc định là Tiếng Việt.** App là control plane một người dùng và người dùng là người Việt.
English vẫn là ngôn ngữ hạng nhất vì một nửa từ vựng trên màn hình (`DISCOVERED`, `Greenhouse`,
`thin_jd`) vốn là tiếng Anh trong DB.

## Dùng thế nào

```tsx
import { useT } from "@/i18n";

const t = useT("jobs");          // namespace = 1 file trong i18n/dict/
<h1>{t("title")}</h1>
<p>{t("found", { count: 12 })}</p>   // "{count}" trong chuỗi được thay
```

Chuỗi sống ở `i18n/dict/<namespace>.ts`, viết bằng helper `ns({ en, vi })`. `vi` được **type**
theo `keyof en`, nên thiếu một chuỗi tiếng Việt hoặc thừa một key lạ là **lỗi biên dịch** —
`npm run build` chạy `tsc --noEmit` nên không cần công cụ lint riêng. Thêm namespace mới thì
đăng ký một dòng ở `i18n/dict/index.ts`.

Không dùng `react-i18next`: app cố ý chỉ có 7 dependency runtime, bảng chữ là 2 ngôn ngữ cố
định, và tiếng Việt **không biến cách số nhiều** nên không có luật plural nào đáng mô hình hoá.
Đổi lại được type-check theo key, thứ mà tra cứu bằng string thuần không cho.

## Ba helper phải đi qua, không tự chế lại

| Cần gì | Dùng | Ở đâu |
|---|---|---|
| ngày/giờ (`3 giờ trước`, `10 thg 7`) | `useFormat()` → `.relativeTime/.shortDay/.clockTime` | `lib/format.ts` |
| tên cờ chất lượng, seniority | `useLabels()` → `.qualityLabel/.levelLabel` | `lib/labels.ts` |
| 9 trạng thái job | `useStatuses()` → `.info(s)` `{label,meaning,next}`, `.tooltip(s)` | `lib/statuses.ts` |

Cả ba là **hook**, không phải hàm thuần, và đó là điểm chính: một hàm `relativeTime(iso)` đọc
biến "ngôn ngữ hiện tại" ở module scope sẽ **không re-render** khi user bấm đổi ngôn ngữ —
bảng "3h ago" cứ đứng nguyên tiếng Anh cho tới khi có thứ khác tình cờ invalidate nó. Bản
`qualityLabel`/`levelLabel`/`STATUS_INFO` **không có tham số ngôn ngữ đã bị xoá hẳn**, để mọi
call-site cũ thành lỗi biên dịch thay vì lặng lẽ hiện tiếng Anh giữa trang tiếng Việt.

## Cái gì KHÔNG dịch

- **Danh từ riêng**: `ITviec`, `TopCV`, `Greenhouse`, `PostgreSQL`, `Node.js`, `CI/CD`.
  `sourceLabel`/`skillLabel` vì thế vẫn là hàm thuần, không qua dictionary.
- **Bậc seniority**: thị trường VN rao tin bằng đúng thang tiếng Anh ("tuyển Senior Backend"),
  nên `level_senior` là "Senior" ở **cả hai** ngôn ngữ. Dịch thành "cao cấp" là đặt tên cho một
  nấc không ai đăng tuyển.
- **Giá trị từ backend**: `task.progress`, `task.error`, tên model, `job.status` thô, đường dẫn
  file, lệnh CLI, JSON/LaTeX trong code block. Đó là log và dữ liệu, không phải copy.
- **Thuật ngữ dev cộng đồng VN vẫn nói tiếng Anh**: crawl, tailor, commit, provider, token,
  prompt, worker, queue. Dịch hết thành từ thuần Việt làm câu **khó đọc hơn**, không dễ hơn.

## Bẫy đã biết

- **`StatusPill` giờ hiện chữ Việt** (`đã nộp`), nhưng tooltip **luôn mở đầu bằng state thô**
  (`SUBMITTED · …`) ở cả hai ngôn ngữ. `SUBMITTED` là từ mà API trả, CLI in và `PHASES.md` ghi;
  dịch pill mà giấu luôn từ gốc thì không cách nào đối chiếu UI với log.
- **Hook phải gọi trước mọi `return` sớm.** `CompactPager` return `null` khi chỉ có 1 trang —
  thêm `useT` vào phải đặt **trên** dòng đó, không thì vi phạm rules-of-hooks tuỳ dữ liệu.
- **`noUnusedLocals` đang bật.** Bỏ chuỗi cứng cuối cùng của một file mà quên xoá import cũ
  (`relativeTime`, `statusTooltip`) là fail `npm run build`, không phải cảnh báo.
- Prop `noun` của `Pagination` nhận chuỗi **đã dịch sẵn** từ caller. Trang biết nó đang liệt kê
  cái gì, pager thì không — nhét danh sách mọi danh từ của app vào namespace `common` chỉ tạo
  thêm một chỗ nữa phải giữ đồng bộ.
