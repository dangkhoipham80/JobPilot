# `jobpilot/critique/` — đánh giá Master CV so với thị trường đã crawl

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Facet + luật `covered`/`total` ở `jobpilot/analytics/CLAUDE.md`; cùng họ "ý kiến tham khảo" với
> fit report ở `jobpilot/intake/CLAUDE.md`.

`POST /api/cv/master/critique {role, lang}` → `service.critique_master()`; `GET` trả bản mới nhất
(hoặc `null`). Panel "Đánh giá CV so với thị trường" trong CV Studio (`CritiquePanel.tsx`), chỉ
scope master, tab Fields.

## Hai nửa, hai vị thế — đừng trộn

1. **`market.snapshot()` là ĐẾM**, từ `jobs.payload` (`title`, `skills_canonical`, `level`). Mọi con
   số trên panel lấy từ đây, kèm mẫu số. Nó mô tả **corpus đã crawl theo keyword của user**, không
   phải thị trường VN: 2026-10-14 có 430/526 job khớp `backend` vì crawl chạy bằng keyword backend.
2. **`CvCritique` là Ý KIẾN của model.** Prompt cấm trích con số từ snapshot — panel in số cạnh
   chữ, nên số trên màn hình luôn là số đã đếm, không phải số model nhớ sai.

Cả hai lưu chung một row `cv_critiques` (`market` = đúng snapshot đã đưa cho model), kèm
`cv_version`. Panel so với version hiện tại và nói "đánh giá này là của bản vN" khi CV đã đổi.

## Ba luật không được phá

- **Không bao giờ ghi vào CV, không bao giờ vào prompt của tailor.** Ranh giới đó là thứ cho phép
  nó không có guard truthfulness và không có vòng retry (cùng lý do intake fit). Nếu có ngày nó chảy
  vào CV thì viết guard **trước**.
- **Không khuyên thêm kỹ năng chưa có lên CV.** Kỹ năng thị trường đòi mà CV thiếu chỉ được khuyên
  `learn` / `optional` / `skip`. Khuyên thêm metric thì "nếu có số thật", không bao giờ đề xuất số.
- **Chỉ số (`entry_index`) không bao giờ tới mắt user.** `service.clean()` kiểm từng chỉ số với CV
  lúc đánh giá và **chốt `title` vào row** — CV sửa/xếp lại sau đó không làm verdict trỏ sai project.
  Verdict trỏ vào chỗ không có thì bỏ và đếm (`dropped`), không chuyển tiếp. Prompt cũng cấm viết
  "entry[0]" trong chữ tự do (lần chạy thật đầu tiên đã viết vậy).

## Bẫy đã gặp khi chạy thật (2026-10-14, `claude_cli` + `claude-opus-5`, ~60–80 s)

- **Không có ngày hôm nay thì model gọi ngày đúng là lỗi.** CV ghi "Oct 2026 -- Present", model
  (dữ liệu huấn luyện cũ hơn) khuyên "kiểm tra lại các mốc 2026 nằm ở tương lai". `user_prompt` giờ
  bắt buộc nhận `today`.
- **Master là kho → đừng để model khuyên "cắt kho xuống N project".** Tailor tự chọn vài project hợp
  job (nhánh `feat/tailor-pick-projects`); prompt nói rõ số project tự nó không phải vấn đề, `cut`
  chỉ dành cho entry không giúp được application nào.
- **`skills_canonical` có tag danh mục của board** ("software products and web services", "software
  development"). Prompt bảo bỏ qua; vẫn hiện trong chip thị trường vì đó là dữ liệu đếm thật, cùng
  thứ trang Market hiện.
- **Màu chip chỉ dùng token có trong `tailwind.config.ts`** (`good`, `accent`, `critical`, `live`).
  `positive`/`caution` không tồn tại → class biên dịch thành rỗng → chip xám im lặng.

## Vai trò mục tiêu

`ROLE_PATTERNS` khớp **title** (nguồn nào cũng có title; LinkedIn không có skill). Preset dùng
regex; chữ khác là cụm phải có trong title. Không job nào khớp → 409 **trước** khi gọi model. Thêm
preset = thêm một dòng ở `ROLE_PATTERNS` + một key `role_<x>` ở `i18n/dict/critique.ts`.

Chạy trên backend của task `intake` (cùng loại việc: đọc tài liệu, trả ý kiến), log
`llm_calls.task = "critique"` để `llm stats` tách chi phí. Đồng bộ (không 202) như fit.
