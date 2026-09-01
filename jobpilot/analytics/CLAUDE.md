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
- **Nhánh một-số (`_ANY_NUM`) là cái bẫy có hệ thống, không phải một bug lẻ.** Mỗi lần
  `_RANGE` không khớp, parse **rơi xuống đó và báo sàn thành cả hai đầu** — im lặng, trông
  hợp lý. Đã dẫm **ba lần nữa** sau ca `15tr - 25tr`, cùng một hình dạng:
  - `"2000～3000 USD"` → 2000–2000. Dấu ngăn là **tilde**, và bộ gõ CJK biến nó thành
    full-width `～` / wave dash `〜`. `_SEP` giờ có `- – — − ~ ～ 〜 to đến`.
  - `"$2,000 - $3,000"` → 2000–2000. Unit được cho phép **sau** số thứ nhất nhưng không có gì
    được phép **trước** số thứ hai, mà board Mỹ ghi ký hiệu ở **cả hai** đầu.
  - `"Lương admin 5 triệu"` → sàn mở 5tr. Từ khoá `min` **không có `\b`** nên khớp vào giữa
    chữ "ad**min**". Mọi keyword trong `_MIN_ONLY`/`_MAX_ONLY` giờ phải có `\b`.

  ⇒ Sửa parser lương thì **thêm case vào `test_market.py`**, và nhớ `min == max` là một tín
  hiệu đáng nghi: nó chỉ đúng cho lương một mốc ("2000 USD"), còn lại thường là range vỡ.
- **Con số chỉ là tiền khi nó ĐƯỢC VIẾT như tiền** — dính đơn vị (`tr/triệu/k/m/usd/vnd/đ`)
  hoặc kết thúc label. Đây là hàng rào mới, và nó có **giá bằng máu**: lần sửa trên thêm
  `trên`/`dưới` vào `_MIN_ONLY`/`_MAX_ONLY` mà **không** đòi đơn vị ⇒ `"Lương 20 triệu, trên
  2 năm kinh nghiệm"` báo sàn **2 triệu** (job 20tr rơi vào band `<$500`), còn `"20 triệu,
  dưới 30 tuổi"` lấy **tuổi** làm trần lương. Tệ hơn hẳn nhánh một-số nó thay thế — nhánh đó
  lấy số đầu tiên, mà label lương thì luôn dẫn bằng lương. `trên`/`dưới` là hai từ phổ biến
  nhất trong boilerplate tin Việt; thêm keyword mà không neo vào đơn vị là mở lại đúng cái
  cửa vừa đóng.
- **Lương: không đoán.** Không có ký hiệu tiền tệ ⇒ `None` ("20 - 60" là triệu VND hay USD/giờ
  tuỳ board). "Up to 3000" ⇒ `min=None`, **không** bịa 0. Quy đổi sang USD/tháng dùng
  `salary.USD_VND_RATE` có `FX_CHECKED_ON` — là **ước tính**, UI phải nói thế.
- **Sàn mở cũng phải để `max=None`** — đối xứng với "up to". `"160 triệu+"`, `"20 triệu trở
  lên"`, `"Trên 30 triệu"` trước đây ra `min=max=160tr`, tức **khẳng định một cái trần mà tin
  không hề nói**. ⚠️ Nói cho đúng mức: ca này **không đổi con số nào hôm nay** — `usd_month`
  lấy trung bình các bound *đã biết* nên `min=max=160tr` và `min=160tr, max=None` ra **cùng
  6299.21**, mà `market.py` chỉ đọc `usd_month`. Sửa vì mô hình hoá sai, không vì biểu đồ sai.
- **Phân biệt sàn mở với "cộng thêm" bằng KHOẢNG TRẮNG TRƯỚC dấu `+`**, không phải thứ đứng sau
  nó: `(?<!\s)\+`. `"2000 USD + phụ cấp"` (rời) là một khoản cộng thêm — rất phổ biến trong tin
  Việt — còn `"2000+"` (dính) là sàn mở. Bản đầu nhìn ký tự **sau** dấu `+` và vì thế đọc ngược
  `"15tr+ gross"` với `"2000+ USD"`: cả hai đều là sàn mở mà lại bị bịa trần trở lại.
- **Đổi parser thì phải `backfill --force`.** `salary_range` là **dữ liệu đã ghi** trong
  `payload`, không tính lại lúc đọc — sửa regex xong mà không backfill thì `/market` vẫn vẽ
  bằng số cũ và mọi verify đều "xanh" một cách vô nghĩa.
- **`repeat_postings` group bằng chính luật normalize của crawler** (`crawler.text.
  normalize_company` + `normalize_title`), khác `dedup_key` **đúng một tham số**
  `strip_level=False`: dedup hỏi "board khác đã đưa tin này chưa" (chữ level thường chỉ là
  văn phong của board), còn đây hỏi "công ty này đăng đi đăng lại chưa" — tuyển senior và
  junior là hai việc bình thường, không phải lặp. Trước đây hai bên là hai bộ luật viết tay
  và đã lệch. Thêm kiểu so sánh mới thì thêm tham số, **đừng fork hàm thứ ba**.
- **Nó phụ thuộc vào việc tin đăng lại thành row riêng**, mà điều đó do `dedup_days` của
  crawler quyết định — chi tiết ranh giới ở `jobpilot/crawler/CLAUDE.md` §Dedup.
- **`posting_calendar` dùng `posted_at`**, khác `by_day` của Deck (dùng `crawled_at` — đo thói
  quen chạy crawler của mình, không đo thị trường). Nó phát ra **cửa sổ lịch 30 ngày thật,
  zero-fill**, và khai số bài rơi ngoài cửa sổ. Bản đầu chỉ phát ra *ngày có bài* nên hai điểm
  liền kề cách nhau khi 1 ngày khi 18 tháng — một trục thời gian không có thời gian.
