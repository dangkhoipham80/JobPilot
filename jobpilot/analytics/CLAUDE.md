# `jobpilot/analytics/` — market analytics

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Phần **màu + chart** của trang `/market` ở `web/src/CLAUDE.md`.
> Parser sinh ra facet nằm ở `jobpilot/crawler/` (`salary.py`, `skills.py`, `vietnam.py`).

### Market analytics (Phase 21) — đọc trước khi thêm biểu đồ

- **Mỗi aggregate phải trả kèm `covered`/`total`** (`analytics/market.Facet`). Corpus này 57% là
  LinkedIn, mà LinkedIn **không có** skill/lương/tag ⇒ biểu đồ không kèm mẫu số thì đang mô tả
  *mấy board chịu gắn tag* nhưng trông như mô tả *thị trường*. UI in "18 of 73 jobs", **không**
  in % trần trụi. Dưới `MIN_SAMPLE=8` thì có `note` cảnh báo.
- **Trang `/market` mô tả *corpus đã crawl*, không phải thị trường VN.** Câu này nằm ngay đầu
  trang, cố ý.
- **Facet là dữ liệu dẫn xuất, luôn nằm CẠNH giá trị thô** (`skills` vs `skills_canonical`,
  `salary` vs `salary_range`). Parser sai thì còn thứ để chạy lại — `backfill --force`.
- **Ba nguồn nhiễu đã trả giá, cả ba cùng một dạng "trông như đúng":**
  1. Tag của board xếp `+2` (badge tràn card ITviec), `Vollzeit`, `IT Services and IT Consulting`,
     `India` ngang hàng với `Java`. Lọc bằng **pattern** (`_ROLE_RE` khớp danh từ số ít ⇒ bỏ
     "software engineer", giữ "data engineering"), không bằng blocklist dài mãi.
  2. `Hà Nội` / `Ha Noi` / `Hanoi` thành **ba** cột, mỗi cột 1/3 số thật. `vietnam.canonical_city`
     fold ASCII (cùng cách `apply/inbox.fold` làm) rồi map alias.
  3. `"15tr - 25tr"` parse ra **15–15**: unit nằm giữa số và dấu gạch làm vỡ regex range, rơi
     xuống nhánh một-số. Trần bị giảm một nửa mà không báo gì.
- **Lương: không đoán.** Không có ký hiệu tiền tệ ⇒ `None` ("20 - 60" là triệu VND hay USD/giờ
  tuỳ board). "Up to 3000" ⇒ `min=None`, **không** bịa 0. Quy đổi sang USD/tháng dùng
  `salary.USD_VND_RATE` có `FX_CHECKED_ON` — là **ước tính**, UI phải nói thế.
- **`posting_calendar` dùng `posted_at`**, khác `by_day` của Deck (dùng `crawled_at` — đo thói
  quen chạy crawler của mình, không đo thị trường). Nó phát ra **cửa sổ lịch 30 ngày thật,
  zero-fill**, và khai số bài rơi ngoài cửa sổ. Bản đầu chỉ phát ra *ngày có bài* nên hai điểm
  liền kề cách nhau khi 1 ngày khi 18 tháng — một trục thời gian không có thời gian.
