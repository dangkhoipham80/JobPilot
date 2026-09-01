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
- **Con số chỉ là tiền khi nó ĐƯỢC VIẾT như tiền** — có ký hiệu **đứng trước** (`$2000`) hoặc
  đơn vị **đứng sau** (`2000 USD`, `20 triệu`). "Nằm cuối label" **không** tính.

  Hàng rào này có **giá bằng máu**, và phải lắp **ba lần** mới kín:
  1. Thêm `trên`/`dưới` vào `_MIN_ONLY`/`_MAX_ONLY` mà không đòi đơn vị ⇒ `"Lương 20 triệu,
     trên 2 năm kinh nghiệm"` báo sàn **2 triệu** (job 20tr rơi vào band `<$500`), `"20 triệu,
     dưới 30 tuổi"` lấy **tuổi** làm trần.
  2. Bản vá đầu cho phép "số ở cuối label" ⇒ đúng câu đó **đảo trật tự chữ** lại lọt:
     `"Lương 20 triệu, tuổi dưới 30"`. **Một cái neo không phải là một đơn vị.**
  3. `_MIN_SUFFIX` bị bỏ quên ⇒ mọi `<số>+` vẫn thành sàn mở: `"20 triệu, 3+ năm kinh
     nghiệm"` báo sàn **3 triệu**. Số năm kinh nghiệm là thứ hay đi kèm dấu `+` nhất trong
     một tin tuyển dụng.

  4. `_RANGE` bị bỏ ngoài hàng rào, mà lần sửa này lại **nới `_SEP` thêm `~ ～ 〜 −`** ⇒
     `"Lương 20 triệu, 2 ~ 3 năm kinh nghiệm"` ra `2tr–3tr`. **Khoảng số năm kinh nghiệm được
     viết y hệt khoảng lương**, chỉ khác cái đơn vị — nên nới separator mà không có hàng rào là
     mở cửa cho đúng thứ đó. Nay `_RANGE` đòi **ít nhất một trong bốn ô marker** (lead/unit ×
     hai bound) được điền; tiện thể đóng luôn ca `-` vốn sai sẵn trên `main`.

  ⚠️ Hàng rào giờ phủ **cả bốn** nhánh. Nhánh cuối cùng (`_ANY_NUM`) **cố ý** không có hàng
  rào: nó là chỗ mọi nhãn "không phải tiền" rơi xuống, và lấy **số đầu tiên** là câu trả lời
  đúng ở đó — nhãn lương hầu như luôn dẫn bằng lương.
- **Marker đứng trước (`_LEAD`) và marker đứng sau (`_MONEY`) mỗi thứ CHỈ ĐƯỢC CÓ MỘT BẢN.**
  Đã lệch **hai lần**: (1) `$` là marker hợp lệ *sau* con số ở bản này mà không ở bản kia ⇒
  `"Up to 2000$"` bịa ra sàn trong khi `"Up to 2000 USD"` thì không; (2) `US$` là tiền ở
  `_RANGE` (có test ghim hẳn `"US$ 2,000 - US$ 3,000"`) nhưng **không** ở `_MAX_ONLY` ⇒
  `"Thưởng 2 tháng, up to 3000 US$"` rơi xuống `_ANY_NUM` và báo lương = **2** (số "2 tháng").
  Lần thứ hai xảy ra **ngay trong commit tuyên bố đã gộp bảng**. Cùng bài học với
  `normalize_title` ở `crawler/CLAUDE.md`: hai bộ luật song song sẽ lệch, chỉ là lúc nào.
- **`k` CHƯA được đọc thành nghìn, và đó là quyết định có chủ đích.** `"$50k - $70k/year"` ra
  50–70 (sai 1000 lần, mà là cách viết phổ biến nhất của board Mỹ). Cách sửa rẻ — một cờ
  "nhãn này có chữ k" **toàn nhãn**, y như `millions` — **tệ hơn chính cái bug**: `401k` và
  `"thưởng 500k"` là boilerplate nằm cạnh lương bình thường, nên cờ đó nhân ×1000 những bound
  vốn đã đúng. Đã thử và **đã revert**: `"$800 - $900/month, 401k"` ra 800.000–900.000/tháng,
  và ca `"800 - 1200 USD + thưởng 500k"` còn tệ hơn — chỉ bound thấp bị scale rồi guard
  `low > high` **đảo hai đầu**, giấu luôn dấu hiệu bất thường.
  ⇒ `millions` sống được như cờ toàn nhãn **chỉ vì** tin VN có quy ước "số trần cạnh *triệu* là
  triệu"; `k` không có quy ước tương đương. Làm đúng = gắn scale vào **chính figure mang chữ
  `k`**, là một thay đổi riêng. Có test ghim giới hạn này để không ai thử lại lối tắt.
- **Fence KHÔNG cứu được nhãn dẫn đầu bằng số không-phải-tiền.** `"2 - 3 năm KN, 20 triệu"` ra
  **2 triệu**: `_RANGE` từ chối `"2 - 3"` (đúng), rồi `_ANY_NUM` lấy số đầu tiên. `_ANY_NUM` cố
  ý **không** có fence — phải có ai đó trả lời — và "lấy số đầu tiên" đúng nhiều hơn sai vì nhãn
  lương thường dẫn bằng lương, nhưng đó là **heuristic, không phải bảo đảm**. Đừng ghi nó thành
  "cửa đã đóng hết".
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
