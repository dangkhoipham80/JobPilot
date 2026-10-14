# `jobpilot/companies/` — nhà tuyển dụng thành row, và người ở đó

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Fold tên nằm ở `jobpilot/crawler/text.py`; hợp đồng route ở `jobpilot/api/CLAUDE.md`;
> đường ghi của crawler ở `jobpilot/crawler/CLAUDE.md`.

Hai bảng (`companies`, `hr_contacts`) + một cột (`jobs.company_id`), migration `0011`.

## Row công ty **tự sinh**, không phải thứ user phải nuôi

Mọi đường ghi job đều gọi `link_job()`: `persist_jobs` (crawl, cả insert lẫn refresh),
`POST /jobs`, `PATCH /jobs`. Nên `/companies` có nội dung ngay từ ngày đầu — 158 row từ
216 job — chứ không phải một cái form trống chờ user điền.

**`jobs.company` (chuỗi) vẫn giữ nguyên, `company_id` nằm CẠNH nó.** Chuỗi là thứ board in
ra và là **bằng chứng**; link chỉ là *ý kiến của một cái fold* về việc chuỗi đó chỉ nhà tuyển
dụng nào. Ý kiến suy lại được thì không bao giờ được phép là bản sao duy nhất của một sự thật
không suy lại được. Fold sai thì `backfill` sửa được; ghi đè chuỗi thì không.

## Fold: `normalize_company(name, strip_legal=True)`

Là **tham số** của hàm sẵn có, không phải hàm normalize thứ ba — cùng lý do với
`normalize_title(strip_level=)`, và repo này đã trả giá một lần vì hai bộ luật song song
(`crawler/CLAUDE.md`). Dedup **để `strip_legal=False`**: nó so hai bản của *cùng một tin*
trên hai board, vốn viết tên giống nhau. Chỗ này bật lên vì key phải giữ
`Tinhvan Software JSC.` và `Tinhvan Software` chung một row trong nhiều năm.

⚠️ **Hướng gộp NHẦM mới là hướng nguy hiểm.** Hai công ty chung một row = một bên được mời
dùng email HR của bên kia làm nơi nộp. Nên:

- **Từ pháp nhân tiếng Anh chỉ cắt ở ĐUÔI** (`Inc`, `Ltd`, `Co`, `JSC`, `GmbH`…) — `"SA Group"`
  và `"Co-op Bank"` là tên thật có token pháp nhân ở **đầu**.
- **Từ pháp nhân tiếng Việt chỉ cắt ở ĐẦU** (`Công ty`, `TNHH`, `Cổ phần`) — tiếng Việt viết
  chúng đằng trước.
- **`MTV` chỉ là pháp nhân KHI đã cắt được cái gì đó trước nó** ("một thành viên" luôn đi sau
  `Công ty TNHH`). Đứng đầu thì nó là tên thường: cắt nó biến `MTV Networks` → `networks`, đủ
  chung chung để đụng vào một nhà tuyển dụng khác — đúng hướng nguy hiểm.
- **Cụm 2 từ khớp nguyên cụm** (`cổ phần`, `joint stock`): `"phan"` đứng một mình là họ người
  Việt rất phổ biến, `"stock"` là từ thường.
- **Hậu tố quốc gia KHÔNG phải pháp nhân**: `DXC Technology Vietnam` ≠ `DXC Technology`.
- **Không bao giờ cắt tới rỗng** (`len > 1`): `"Company Ltd"` và `"Company"` cùng ra `company`,
  chứ không phải một cái rơi về chính tả gốc rồi lặng lẽ thành row thứ hai.

**Đã đo trên 160 tên thật trước khi chốt**: gộp đúng **2 cặp** (`GitLab`/`gitlab`,
`JetBrains`/`jetbrains`), **0 gộp sai**, **0 key rỗng**. Đổi bảng từ pháp nhân thì **chạy lại
phép đo đó**, đừng đoán — rồi `backfill` để relink.

**Tên hiển thị**: `link_all_jobs` chọn chính tả **phổ biến nhất** trong job của công ty đó
(nên 11 `GitLab` thắng 3 `gitlab`); hoà thì lấy bản **ngắn hơn**, rồi mới alphabet, cho hai lần
chạy không lệch nhau.
Chỉ áp cho row **nó tạo ra** — row đã có thì **không bao giờ đổi tên**, vì tới lúc đó cái tên
có thể đã được user sửa tay, và một backfill ghi đè lên bản sửa là một backfill không ai tin.

## Email HR làm nơi nộp: phải đổi **cả kênh**, không chỉ địa chỉ

⚠️ Ghi `apply_target` **là chưa đủ**. Mọi scraper trong repo hard-code
`apply_channel` là `portal` hoặc `external` — **không nguồn nào** sinh ra `email` — và
`dispatcher.resolve_channel` **ưu tiên cột đã khai**. Nên trên job crawl (tức gần như mọi job),
chọn email HR xong bấm nộp sẽ rơi vào `_apply_handoff`: *"đã chuẩn bị — mở link và tự nộp"*, với
`hr@example.com` đứng ở vai trò cái link, và `--open-portal` lái browser `goto()` vào đó. **Không
email nào được dựng.** App báo thành công một handoff trong khi quyết định "gửi cho người này" bị
bỏ qua sạch.

Job thêm tay **cũng dính** (`JobIn.apply_channel` mặc định `"external"`, và form Add-job không
gửi field đó) — nên lời mời `apply_email` của JD ở đợt `intake` vốn đã hỏng theo đúng cách này.

`_note_stated_target` vì thế làm **hai** việc: ghi cờ, **và** đổi `apply_channel` sang `email` khi
địa chỉ user nói ra parse được thành email.

- **Chỉ đẩy một chiều.** Địa chỉ không phải email thì **giữ nguyên** cột — board nói `portal` thì
  nó biết về URL của chính nó nhiều hơn một phép đoán ở đây.
- **Caller tự khai `apply_channel` thì thắng**, không bị đoán lại.
- **Ghi xuống DB, không suy ra lúc đọc.** Board Applications, Slack và CLI đều đọc `channel`; một
  luật chỉ sống trong `resolve_channel` sẽ để cả ba chỗ đó hiện sai.
- **UI phải nói ra** (`offerHint`): bấm nút không gửi gì, nhưng nó *có* đổi kênh — im lặng đổi
  nghĩa của nút Nộp sau đó là đúng thứ nguyên tắc 2 cấm.

## `PATCH /jobs {apply_target}` — ai NÓI RA thì thắng

⚠️ **Lỗi này chỉ lộ ra khi chạy thật, test xanh suốt.** Chọn email HR làm `apply_target`
giữ được **đúng tới lượt crawl tiếp theo** của nguồn đó: `_refresh` ghi đè cột bằng URL của
board. Âm thầm, vài ngày sau, và trên màn hình không có gì cho thấy một quyết định đã bị xoá.
Mà job crawl là gần như **mọi** job ⇒ nếu không sửa thì tính năng này không sống qua một đêm.

Sửa bằng đúng luật `_merged_payload` đã dùng cho `work_mode`: **ai nói ra thì thắng, bản scrape
là fallback**. `PATCH` ghi `payload["apply_target_source"] = "user"`, `_refresh` đọc nó rồi
**không** đụng vào cột nữa.

- **`_refresh` phải giữ CẢ HAI cột** (`apply_target` + `apply_channel`) sau cờ đó. Giữ mỗi địa chỉ
  là cùng một bug đội mũ khác: địa chỉ vẫn `hr@…` mà kênh về `external` ⇒ lại ra handoff.
- **`apply_target_source` phải nằm trong `_ROW_OWNED_KEYS`** của `persist.py`. `_refresh` thay
  **cả** `payload` bằng thứ scraper vừa sinh ra, nên key nào không được carry qua sẽ sống đúng
  tới lượt crawl kế — *y hệt* lý do `dedup` phải được carry. Một key tồn tại tới lần crawl sau
  thì bằng không tồn tại.
- **Đặt rồi thì ở lại, và đó là bất đối xứng có chủ ý.** `JobPatch` là `exclude_none` nên
  không có cách nào *nói* "trả về giá trị của board"; suy ra điều đó từ một field vắng mặt là
  huỷ quyết định của user ở **mọi** lần sửa không liên quan.

## `hr_contacts` — chỉ `name` là bắt buộc

Vì liên hệ tới theo đúng cách đó: một cái tên + số điện thoại sau cuộc gọi, một địa chỉ nhặt
từ chữ ký mail. Bắt buộc email nghĩa là hoặc bịa ra một cái, hoặc không ghi người đó lại.

⚠️ **Field text phải clamp** (`_clamped`): SQLite bỏ qua `VARCHAR(n)`, Postgres thì trả
`StringDataRightTruncation` **giữa flush** — một 500 không nói field nào sai. Dán nguyên chữ ký
mail vào ô "Tên" là đúng cái đầu vào 400 ký tự đó. Scar cũ, chỗ mới (`intake/CLAUDE.md`).

⚠️ **`_require_contact` kiểm CẢ `company_id`**, không chỉ `contact_id`: nếu không thì id của
liên hệ công ty A sửa được qua URL của công ty B — số điện thoại một người lặng lẽ nhảy sang
card của nhà tuyển dụng khác.

## Xoá: `SET NULL`, không phải `CASCADE`

Xoá công ty thì **gỡ link** job, không xoá job (`jobs.company_id` `ON DELETE SET NULL`). Gõ nhầm
tên nhà tuyển dụng không được phép làm mất 11 tin. Ngược lại `hr_contacts` **`CASCADE`** — một
người liên hệ không tồn tại ngoài công ty của họ.

`NULL` ở `company_id` đọc đúng là "chưa gắn": đó cũng là trạng thái của mọi row ghi trước khi
cột này tồn tại, và của job không có tên công ty (`company_key("") == ""` ⇒ **không** sinh row,
vì một card không tên trên `/companies` cho mỗi tin như thế là vô nghĩa).

## Bẫy đã trả giá

- **Import vòng.** `companies.service` cần `crawler.text`, mà import **bất kỳ** submodule nào
  của `jobpilot.crawler` cũng chạy `__init__` của nó, và `__init__` import thẳng `persist`.
  Nên `from jobpilot.companies.service import link_job` ở **module scope** của `persist.py` chỉ
  chạy được khi crawler tình cờ được import trước — và nổ `ImportError` khi có thứ gì chạm vào
  `companies.service` trực tiếp. Migration 0011 làm đúng thế. Import **trong hàm**
  `persist_jobs`, có comment; đừng "dọn" nó lên đầu file.
- **`backfill` không được phép trừ đi.** `link_all_jobs` chỉ **gán** link, không bao giờ
  `NULL` hoá — kể cả job không fold ra key nào (đếm vào `unlinkable`, giữ nguyên link cũ). Đây
  là cùng loại lỗi mà `backfill_facets` từng gây ra: một cú xoá im lặng do chính lệnh mà tài
  liệu bảo là bắt buộc chạy (`intake/CLAUDE.md`).
- **`ORDER BY` phải kết thúc bằng `Company.id`.** Gần như mọi công ty **hoà ở 0 đơn đã nộp**,
  nên tie là mặc định chứ không phải ngoại lệ, và tie dưới `LIMIT/OFFSET` là một row hiện hai
  lần còn một row không bao giờ hiện.
- **`applied_count` đếm JOB, không đếm row `applications`.** Gửi lại sau một lần bounce là
  **một** job đã nộp, không phải hai. Ngưỡng là **`SENT_RESULTS` import từ `apply/followup.py`**,
  không bao giờ chép lại — `apply/outcome.py` ghi thẳng luật đó ra, và đây đúng là ca nó đề phòng.
  Nó là `{"success", "awaiting_user"}`: đơn portal/external được handoff và nằm ở `awaiting_user`,
  mà **mọi phần khác của app đã coi đó là đã gửi** (board hiện, đồng hồ follow-up chạy, inbox sync
  match reply, `/analytics` tính vào reply-rate). Đếm mỗi `success` sẽ cho **`0 đã nộp`** ở đúng
  những công ty đang theo đuổi — và vì `order=applied` là mặc định, nó **dìm họ xuống đáy** 160
  dòng, đúng thứ trang này sinh ra để đẩy lên. `dry_run` vắng mặt có chủ ý: nó chưa rời khỏi máy.
- **`company_key` clamp NGAY trong nó**, không phải lúc insert. Key là thứ mọi lookup select trên
  đó: clamp muộn nghĩa là SELECT bằng fold đầy đủ (không khớp) → INSERT bản cắt → đụng unique →
  re-read lại bằng fold đầy đủ → **`None` cho một công ty đang tồn tại**. SQLite bỏ qua width nên
  chỉ Postgres mới lộ.
- **`link_all_jobs` select CỘT TƯỜNG MINH, không `select(Job)`.** Migration 0011 gọi nó, nên nó
  chạy trên schema **của thời điểm đó**. `select(Job)` phát ra **mọi cột model có hôm nay** (đo
  thật: 17 cột) và sẽ hỏng ngay khi một migration sau thêm cột vào `jobs` — `alembic upgrade head`
  từ đầu sẽ chết ở 0011 vì `UndefinedColumn` trên một cột chưa tồn tại ở mốc lịch sử đó. Bản core
  select cố định **3 cột**. (Một cú *rename* `jobs.company` thì vẫn hỏng — to tiếng, đó là đánh
  đổi đã ghi trong docstring của migration.) Hệ quả: nó dùng Core UPDATE nên phải `expire_all()`,
  nếu không `Job` đã nạp trong session giữ `company_id` cũ tới hết transaction.
- **`POST /jobs` upsert nên cũng phải tôn trọng cờ.** Dán lại đúng tin đó sẽ chạy nhánh fallback
  `body.url` và **xoá** lựa chọn của user, trong khi payload vẫn khai là "user" — cờ nói một đằng,
  cột một nẻo. Chỉ `apply_target` khai rõ trong **chính** body đó mới được ghi đè.
- **Tên hiển thị hoà phiếu thì lấy bản NGẮN hơn**, rồi mới alphabet: xếp theo alphabet thôi làm
  `"Cong ty TNHH Foo"` thắng `"Foo"` khi mỗi bên 1 job — hiện ra giấy tờ thay vì cái tên.
- **`q` phải escape `%`/`_` trước khi vào `ilike`** — không thì `100%` khớp `1000 …`, tức ô tìm
  kiếm lặng lẽ trả lời một câu hỏi khác câu đã gõ.
- **Đếm cho row của TRANG hiện tại thôi** (`_counts_for`), không phải correlated subquery mỗi
  row: 3 lần quét `jobs` cho một trang 25 dòng. Chỉ hai kiểu sort *cần* con số để xếp mới trả
  giá đó.

## Logo (`logos.py`, migration 0014)

Bốn cột trên `companies`: `logo_url` (board nói logo ở đâu), `domain` (site của chính công ty),
`logo_file` (bản cache), `logo_checked_at`.

- **Nguồn theo thứ tự:** (1) `hiringOrganization.logo` trong JSON-LD của trang tin — thu ở **một
  chỗ** trong `BaseScraper.crawl` (TopCV, ITviec có; đo 2026-10-14), không phải mỗi scraper một
  bản; (2) trang chủ của `domain`: `apple-touch-icon` → `icon` lớn nhất → `/favicon.ico`.
- **Không dùng dịch vụ favicon của Google**: robots.txt của nó cấm. Mọi request logo đi qua
  `RobotsPolicy` như crawler.
- **Chỉ nhận ảnh raster thật** (PNG/JPEG/GIF/WebP/ICO, đoán theo byte, ≤ 512 KB). **SVG bị từ
  chối**: nó là tài liệu chạy được script và sẽ được phục vụ từ chính origin của dashboard.
- **Dashboard không bao giờ hotlink CDN của board.** Ảnh tải về `<out_dir>/logos/<sha256[:20]>.<ext>`
  và phục vụ ở `/api/logos/<tên>` — route **duy nhất không cần token**, vì `<img>` không gửi được
  header. Nó chỉ nhận tên khớp `FILE_RE`; tên là hash nội dung, không suy ra được từ công ty.
- **Chỉ điền chỗ trống** (`service._take_brand`): domain người dùng sửa tay, hay logo của board đầu
  tiên, không bị lần crawl sau ghi đè.
- Tải sau mỗi lượt crawl (tối đa 25 công ty, lỗi chỉ log — không bao giờ làm hỏng kết quả crawl),
  bằng `jobpilot logos`, và ngay khi user đặt domain. Không tìm thấy thì thử lại sau 7 ngày.
- Đo thật trên bản sao DB: 8/8 công ty từ logo của board, 3/4 theo domain — chỗ còn lại trang chủ
  trả 403 cho bot. Không có logo ⇒ UI hiện chữ cái đầu (`CompanyLogo.tsx`), không lưu gì.
