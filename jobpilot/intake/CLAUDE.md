# `jobpilot/intake/` — dán JD vào, đọc nó, chấm nó

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Chọn provider/model ở `jobpilot/llm/CLAUDE.md`; hợp đồng route ở `jobpilot/api/CLAUDE.md`;
> `enrich()` mà nó dùng chung nằm ở `jobpilot/crawler/normalize.py`.

Ba bước **cố ý tách rời**, vì mỗi bước tự nó đã dùng được và mỗi bước là một loại khẳng định khác:

1. **Đọc** — `POST /jobs/intake` → `extract_jd()`. Model rút title/company/location/salary/level/
   skills ra khỏi một đống text. **Không ghi gì xuống DB**; câu trả lời quay lại form để user sửa.
2. **Lưu** — `POST /jobs` như cũ, không đổi hợp đồng.
3. **Chấm** — `POST /jobs/{id}/fit` → `assess_fit()`. Model so job với Master CV. Kết quả nằm ở
   `payload["fit"]`.

## Ba luật không được phá

- **JD lưu xuống là bản dán của user, KHÔNG BAO GIỜ là bản model kể lại.** (Tin chỉ tồn tại dưới
  dạng ảnh thì model được **chép**, không được kể — và bản chép đi qua ô mô tả trước khi thành row;
  xem "Tin là ảnh hoặc PDF" bên dưới.) Đây là luật quan trọng
  nhất ở đây. Mọi guardrail phía sau — `requirements` của tailor, cover letter, chính cái fit report
  này — đọc `description_md` như là **bằng chứng**. Để model viết lại JD là để nó tự bịa ra bằng
  chứng cho chính nó, và không có guard nào bắt được vì guard nào cũng đang so với đúng cái field
  đó. `JdExtract` vì thế **không có** field `description_md`; `clean_paste()` chỉ đổi HTML → markdown
  và gộp dòng trống.
- **`clean_paste` làm sạch THEO TỪNG DÒNG, không dùng `clean_text` cho cả khối.** `clean_text` gộp
  mọi khoảng trắng kể cả `\n` — đúng cho title/location, **phá** cho body: JD phần lớn là gạch đầu
  dòng, gộp hết thành một đoạn là ném đi cấu trúc mà tin đăng vốn có. Đã verify trên trình duyệt
  thật: bullet list render đúng.
- **Fit report chỉ để tham khảo, và ranh giới đó là thứ cho phép nó không có guardrail.** Nó không
  bao giờ được ghi vào CV, không bao giờ được trích vào cover letter, không bao giờ đi vào prompt
  của tailor. `intake/engine.py` vì thế **không có** vòng retry — không có luật máy móc nào phân
  biệt một ý kiến đúng với một ý kiến sai, nên không có gì để kiểm và không có gì để gửi lại. Nếu
  có ngày nào output này bắt đầu chảy vào tailor hay vào CV thì **phải viết guardrail trước**, không
  phải sau.

## Tin là ảnh hoặc PDF (`POST /jobs/intake/file`, `service.read_files`)

Bài đăng trong group Facebook/Zalo thường chỉ là một tấm ảnh. Endpoint này biến file thành **text
và chỉ text** — không đọc field nào, không lưu gì.

- **Hai request, không gộp.** File → text vào **ô mô tả** của form → `POST /jobs/intake` đọc field
  từ text đó, đúng lượt gọi mà một lần dán dùng. Ô mô tả là trạm kiểm: thứ được lưu làm
  `description_md` là thứ user đã nhìn thấy trong ô, với ảnh gốc cách một cú click. Gộp thành một
  lượt "ảnh → row" là để bằng chứng đi từ ảnh xuống DB mà không ai thấy.
- **`JdTranscript` chỉ có `text` + `unreadable`.** Cùng lý do `JdExtract` không có
  `description_md`, nhìn từ phía kia: lượt gọi được phép đụng vào chữ của tin thì chỉ được *chép*.
  Một lượt vừa chép vừa điền title/lương là vừa đọc vừa chép, và làm việc thứ hai tệ hơn.
- **PDF có text layer trên MỌI trang thì KHÔNG gọi model.** Layer là chữ của chính người đăng.
  `transcribed=False`, và form nói thẳng "không có AI nào viết". Sàn 200 ký tự (`_MIN_LAYER_CHARS`)
  tính **theo từng trang**: trang nào dưới sàn (con dấu số trang, footer, **hay một trang chỉ là
  ảnh**) thì cả upload qua model. Bản đầu tính sàn trên *tổng* — bài đăng in ra PDF gồm một trang
  caption + một trang poster qua được nhờ caption, ô chỉ có khung trang dưới dòng "không cần AI"
  (review gate tái hiện). Ở nhập CV thì layer chỉ để *đối chiếu* nên thiếu là báo động giả; ở đây
  layer **thay** bản đọc nên thiếu là mất nội dung — cùng một hàm, hướng hỏng ngược nhau.
  **Vẫn chưa kín:** chữ nằm *trong ảnh* trên một trang vốn đủ chữ thì layer không có; form ghi rõ
  điều đó cạnh ô. Chiều ngược lại sẽ gặp thường: PDF toàn chữ thật mà trang cuối chỉ có hai dòng
  liên hệ (< 200 ký tự) thì cả file đi qua model — tốn một lượt gọi, nhưng có nhãn "AI đã chép". Extractor pypdf không đánh dấu trang ⇒ sàn lại thành tính trên tổng (pdfminer là
  extractor mặc định). PDF đi kèm ảnh thì cả upload qua model.
- **Layer của PDF in từ trang web mang cả khung trang** (tên người đăng, số like, nút bấm) — đo
  thật. Không lọc: lọc là đoán, và `extract`/`sections` vốn đã viết để bỏ qua rác của một lần dán.
- **Kiểm file dùng lại `cv/importer`** (`decode_uploads`, `load_files`, `text_layer`, `pages_of`,
  `plain_text`): sniff theo byte, cùng giới hạn (6 file, ảnh 3,5 MB, PDF 10 MB, 10 trang). Đừng viết
  bộ kiểm thứ hai. Câu từ chối "không phải PNG/JPEG/WebP/PDF" nhận `text_hint` của caller — bản mặc
  định chỉ cách nhập *CV* và từng hiện nguyên trên form thêm job.
- **Không có vòng retry và không có phép kiểm máy nào** cho bản chép từ ảnh — như nhập CV từ ảnh.
  Guard là: note dưới ô mô tả nói rõ model đã chép, link "Bản gốc", và `unreadable` của model.
  Không có cờ nào lưu xuống job ghi rằng JD của nó từng là ảnh: sau khi qua ô, nó là text user đã
  duyệt, cùng cách bản nháp CV nhập từ ảnh thành version của `user`. **Rủi ro còn lại:** user bấm
  lưu mà không so, và một con số đọc nhầm thành "yêu cầu của nhà tuyển dụng" cho tailor/fit.
- **Bản đọc chỉ hạ cánh vào ô TRỐNG hoặc ô còn nguyên bản đọc trước** (`boxIsFree`). Ô có chữ user
  gõ/sửa thì nút bị khoá — bản đọc thay toàn bộ ô. **Ô bị khoá (`readOnly`) suốt lúc đang đọc**:
  `boxIsFree` chỉ kiểm lúc bắt đầu, và review gate gõ được một câu vào ô trong lúc chờ rồi nhìn nó
  bị thay sạch. URL thì đọc qua ref (`urlNow`) — `read()` chạy từ closure cũ hơn lượt đọc file.
- **Dán ảnh từ clipboard vào ô (`onPaste`) chỉ khi clipboard KHÔNG có text.** Copy từ bảng tính hay
  trình soạn thảo mang cả text lẫn ảnh của chính nó; thứ user muốn dán là text.
- **`llm_calls.task = "intake_file"`**, backend của task `intake`. Tên riêng để `llm stats` không
  giấu chi phí của ảnh (đắt hơn text nhiều lần) vào giữa các lượt dán.
- **Đo thật 2026-10-14** (`claude_cli`; một bài đăng **bịa**, song ngữ Việt/Anh, render thành ảnh
  chụp kiểu mạng xã hội 1200 px và thành PDF): ảnh → `claude-opus-5` 11 s, `claude-haiku-4-5`
  15 s, **mọi từ và mọi con số khớp** với text nguồn, khung app (tên người đăng, like, bình luận)
  được bỏ đúng như prompt dặn. Lượt đầu đọc **mọi dấu `|` thành chữ `l`** ("Java l Spring Boot")
  — sai kiểu trông-như-đúng; thêm một dòng vào prompt thì hết ở cả hai model. PDF → 0 s, không gọi
  model, nguyên văn kèm khung trang. Chưa thử: ảnh chụp bằng điện thoại, poster chữ cách điệu,
  ảnh nhiều trang.

## Nguồn của job thêm tay (`JobIn.source`, `HandSourceStr`)

- **`source` là nơi user nói đã thấy tin** — `manual` (nơi khác) / `facebook` / `linkedin` / `zalo`.
  Danh sách **đóng** vì nó thành `jobs.source`, cột mà mọi chart theo nguồn `GROUP BY`: chữ tự do
  ở đó tách một nơi thành "fb", "Facebook", "facebook group". Chỉ danh từ riêng, để tên không cần
  dịch (`sourceLabel`). Thêm nơi mới = thêm vào `HandSourceStr` + `HAND_SOURCES` ở `web/src/types.ts`
  + `SOURCE_NAMES`.
- **ID luôn là `manual:<native>`, bất kể source.** Nó là thứ khiến dán lại một tin rơi đúng row cũ,
  và là cách app phân biệt job thêm tay với job crawl trùng tên nguồn (`crawler/types.is_hand_added`)
  — job thêm tay ghi `linkedin` và job từ LinkedIn alert chung một `source` (cùng một nơi, đúng là
  thế) nhưng không bao giờ chung id. Đây là chỗ **duy nhất** `id` không mở đầu bằng `source`.
- **`source` của job thêm tay KHÔNG phải khoá crawler — ba chỗ từng coi nó là thế, đều do review
  gate tìm ra:**
  - `GET /jobs/{id}` lấy `crawl_passes(job.source)` ⇒ job dán tay ghi `linkedin` bị gắn `not_seen`
    ("có thể đã bị gỡ") sau hai lượt alert, dù chưa lượt crawl nào từng tìm nó. Giờ job thêm tay
    không có pass nào. *Chưa từng được tìm ≠ đã biến mất.*
  - Dedup lớp 2 (`persist._same_posting`) coi trùng `source` là "cùng board" và so tiêu đề chặt ⇒
    tin dán tay và bản của chính board thành hai job chỉ vì một cặp ngoặc. Luật cùng-board giờ bỏ
    qua row `manual:`.
  - `/analytics/market` đếm nguồn từ `payload["source"]` (thứ chỉ `normalize()` ghi) ⇒ mọi job thêm
    tay là một cột "?". `POST`/`PATCH /jobs` giờ ghi key đó. Row thêm tay có từ trước vẫn là "?"
    cho tới lần sửa kế tiếp.
- **Địa chỉ dán vào chỉ là danh tính của tin khi nó thật sự chỉ MỘT tin** (`_native_id` trả
  `(id, strong)`):
  - *Mạnh — chỉ số job của LinkedIn* (`/jobs/view/<n>`, hoặc `currentJobId=<n>` là thứ thanh địa
    chỉ hiện khi đang duyệt kết quả tìm kiếm). Số đó là 1-1 với một tin: dán lại luôn về đúng row,
    kể cả khi đã sửa tiêu đề.
  - *Yếu — mọi thứ khác*: số bài Facebook (`fbid` / `story_fbid` / `multi_permalinks`, hoặc
    `/posts|permalink|videos|share/p/<id>`) — một bài của recruiter **liệt kê nhiều vị trí**; và
    segment cuối của path (`…/careers` là **mọi** job của công ty đó). Id yếu chỉ được dùng khi row
    tìm thấy **cùng công ty và cùng tiêu đề so chặt** (`_as_listed`: giữ cấp bậc và phần trong
    ngoặc); khác thì rơi về `slug(company-title)`. **Không dùng `dedup_key`** ở đây: khoá đó bỏ
    "Junior" và "(Java)" vì hai *board* viết một vai trò theo hai kiểu — còn đây là cùng một form
    nói về cùng một địa chỉ. Bản đầu dùng `dedup_key`, và "Junior Backend Engineer" bị "Senior
    Backend Engineer" ghi đè (review gate vòng hai).
  - *Không có*: địa chỉ mạng xã hội không chứa bài nào (link group Facebook, `zalo.me/g/<id>`) —
    segment cuối ở đó là **cái group**, giống nhau cho mọi tin từng đăng trong đó.
  - Địa chỉ copy thiếu `https://` vẫn được đọc như địa chỉ (thêm scheme trước khi tách) — không thì
    không luật nào ở trên biết đó là Facebook.
  Trước khi sửa: hai bài khác công ty mở từ trình xem ảnh của Facebook cùng ra `manual:photo`, bài
  sau ghi đè bài trước và trả **201** — status, CV đã tailor và application của tin đầu dính vào
  nội dung của tin khác. Gốc lỗi có từ trước phase này; phase này là thứ mời URL Facebook vào ô đó.
  Hướng hỏng còn lại là hướng rẻ: sửa tiêu đề (kể cả chỉ thêm "Senior" hay một cặp ngoặc) của một
  job có địa chỉ *yếu* rồi dán lại thì thành row thứ hai — với bài Facebook cũng vậy. **Vẫn còn
  một ca đè:** hai tin *khác nhau* trùng hẳn công ty lẫn tiêu đề (hai team cùng tuyển "Backend
  Engineer") dùng chung một địa chỉ yếu, hoặc không có địa chỉ — không gì trên form phân biệt
  được chúng.
- **Đường lùi `slug(company-title)` cũng bị hỏi cùng câu đó** (`_fallback_id`). Slug chỉ giữ 80 ký
  tự `[a-z0-9]`: tên pháp nhân dài lấp đầy nó trước khi tới tiêu đề, và tiêu đề viết bằng chữ không
  phải Latin không góp ký tự nào — nên hai vị trí của một công ty tên dài, hay hai tin tiêu đề
  tiếng Trung/Nhật, từng ra cùng id và đè nhau (có từ trước phase này; review gate vòng ba chỉ
  ra). Row dưới slug mà khác tin thì id được gắn thêm digest của đúng `company|title`. **Id của
  row đang có không đổi**: digest chỉ xuất hiện khi slug đã có chủ khác. `_as_listed` so chuỗi gốc
  ở phần nào bộ chuẩn hoá trả rỗng — hai chuỗi rỗng thì bằng nhau, và đó chính là lỗi.
- **`None` = không nói**: job mới thì `manual`, dán lại job cũ thì **giữ nguyên** source đang có.
  Client cũ (Slack, bundle chưa build lại) không gửi field này và không được phép reset nó. Form
  vì thế **bỏ hẳn** field khi user chưa chọn và URL không nói lên điều gì.
- **`PATCH` chỉ đổi được source của job thêm tay** (422 với job crawl): source của job crawl là
  dữ kiện về nơi nó được crawl.
- Form đoán mặc định từ URL (`sourceFromUrl`: facebook.com/fb.com/fb.me, linkedin.com/lnkd.in,
  zalo.me); user chọn thì user thắng. Chưa có logo cho Facebook/Zalo — `SourceIcon` rơi về monogram.

## JD có cấu trúc — hai lượt gọi, chạy song song

`extract` (fact ở đầu tin) và `sections` (thân tin chia bucket) là **hai** structured call trên
**cùng một** đoạn text, chạy **đồng thời** trong `ThreadPoolExecutor`. Tách vì hai việc đọc khác
nhau — một bên chép 6 fact ngắn, một bên sắp xếp văn xuôi — và một prompt làm cả hai thì làm dở cả
hai; tách còn giữ mỗi schema nhỏ, thứ mà `llm/CLAUDE.md` ghi là yếu tố quyết định provider có nhận
hay không. Chạy song song vì hai lượt độc lập: đo thật, cả cặp tốn xấp xỉ đúng bằng lượt chậm hơn
(~3s khi prompt đã cache, ~8s lần đầu).

**Cùng một `body` đi vào cả hai.** Đưa hai input khác nhau là cách để hai câu trả lời mô tả hai job
khác nhau.

- **Bucket là MỤC LỤC của `description_md`, không thay thế nó.** Cả hai đều được lưu. UI cho toggle
  "Có cấu trúc / Nguyên văn" ngay trong card JD — **cố ý không phải card thứ hai**: bản gốc phải
  cách một cú click, vì *đối chiếu được* là điều duy nhất khiến việc hiển thị bản sắp xếp của model
  là an toàn.
- **KHÔNG ĐƯỢC DỊCH.** Đã dính thật: tin tiếng Việt trả về bucket tiếng Anh, mà mọi dòng đều đúng
  nội dung. Luật "giữ nguyên ngôn ngữ" nằm **lẫn trong một đoạn văn** thì bị bỏ qua; nâng lên thành
  **mục riêng, viết hoa, ở đầu system prompt** thì 4/4 lượt trên 2 backend trả đúng tiếng Việt
  nguyên văn. Đây là **lần thứ hai** cùng một bài học trong cùng file prompt (lần đầu là `summary`
  của fit) — luật về ngôn ngữ đặt trong danh sách field thì model không nghe.
- **`must_have` vs `nice_to_have` theo cách TIN ĐĂNG đánh dấu**, không theo việc kỹ thuật đó nghe
  quan trọng cỡ nào. "ưu tiên" / "là một lợi thế" / "a plus" → `nice_to_have`.
- **`soft_skills` tách riêng** vì CV không chứng minh được phần lớn chúng — và `FitReport` cho
  `soft` trọng số 0 vì đúng lý do đó.

## Lương có 4 dạng, không phải 3

`Salary.kind` **suy ra** từ `min`/`max`, không lưu — nên không thể lệch khỏi con số nó mô tả:

| kind | hình dạng | ví dụ |
|---|---|---|
| `fixed` | min == max | `25 triệu` |
| `range` | cả hai, khác nhau | `20 - 60 triệu` |
| `up_to` | chỉ có trần | `Up to $3000`, `Lên đến 40 triệu` |
| `from` | chỉ có **sàn** | `Từ 15 triệu`, `trên 20 triệu` |

Dạng thứ 4 (`from`) parser **vốn đã** sinh ra từ trước. Gộp nó vào `range` là bịa ra một cái trần,
gộp vào `fixed` là bịa ra một mức lương — đúng kiểu sai-mà-trông-hợp-lý mà repo này đã trả giá.

## Tỉnh/thành + hình thức làm việc

Hai lỗ đã đo trên corpus thật (216 job) rồi sửa:

- **Hậu tố quốc gia làm hỏng cả nhãn.** `"Ho Chi Minh City, Vietnam"` — dạng **mọi** LinkedIn alert
  dùng, mà LinkedIn là hơn nửa corpus — tách thành `["Ho Chi Minh City", "Vietnam"]`, phần
  `"Vietnam"` không phải city ⇒ trượt cửa "mọi phần đều là city" ⇒ **rớt cả nhãn**, `city=None`,
  job biến mất khỏi chart city của `/market`. Không có lỗi nào hiện ra.
- **`TP.HCM` fold thành `"tp hcm"`**, không có trong bảng alias ⇒ cũng `None`.
- Sửa bằng `_fold_place()` (= `_fold_city` + bỏ từ trang trí), và `looks_like_city` **bỏ qua** phần
  thuần trang trí thay vì để nó đánh trượt. Vẫn phải còn **ít nhất một** city thật, nên `"Vietnam"`
  đứng một mình vẫn không phải location, và bẫy `"remote debugging"` vẫn đóng.
- **`(On-site)` / `(Hybrid)` là chú thích của NHÃN, không phải của nơi chốn** — LinkedIn viết
  `"Hanoi Capital Region (On-site)"`. Strip trong `_CITY_SUFFIX_RE` (cùng họ với `(mới)` của TopCV)
  và đọc lại thành `work_mode`. ⚠️ **Chỉ đúng với caller giữ nhãn thô** (LinkedIn + đường intake):
  ITviec/TopCV/VietnamWorks cho location qua `find_city`/`clean_city` **trước khi lưu**, nên nhãn
  chúng lưu đã mất hậu tố và `parse_work_mode` không đọc lại được. Hôm nay vô hại (board VN không
  viết hậu tố đó) — nhưng đừng đọc thành "không bao giờ mất".

**Kết quả đo được sau `backfill --force`**: job có location mà không ra tỉnh **160 → 119** (phần còn
lại là thành phố nước ngoài — Berlin, London, Bangalore — `None` ở đó là *đúng*, `CITIES` chỉ có 34
tỉnh VN). `work_mode` phủ **105/216** job.

⚠️ **`is_remote` và `work_mode` không được phép mâu thuẫn.** Đo thật: 8 job ghi
`"Anywhere in the World"` — `_REMOTE_RE` biết, còn pattern viết tay song song thì không ⇒
`is_remote=true` mà `work_mode=null`, **cùng một dòng, cùng một câu hỏi**. Nhánh remote giờ **dùng
lại `_REMOTE_RE.pattern`**, có test ghim. Hai field suy ra từ một nhãn thì không được có hai bộ luật.

⚠️ **`backfill_facets` đọc từ CỘT (`job.location`/`job.salary`), không phải từ payload.**
`payload["location"]`/`["salary"]` **chỉ `normalize()` ghi** — job vào qua `POST /jobs` không có.
Đọc payload trước nghĩa là backfill gọi `derived_facets(None, ..., None)` cho **mọi job dán tay** và
null hoá sạch `city`/`salary_range`/`is_remote`/`work_mode`: một cú xoá **im lặng**, do chính lệnh
mà chỗ này bảo là bắt buộc. Đã dính thật trên Postgres.

⚠️ **`work_mode` đi qua `_merged_payload()`, đừng spread `signals.payload` sau payload.**
`signals.payload` **luôn** có key `work_mode` (derive từ nhãn location), nên spread nó sau cùng là
đè lên giá trị user/model đã nói ra. `POST` và `PATCH` từng có hai thứ tự khác nhau ⇒ hai hành vi
khác nhau, và test không bắt được vì mỗi endpoint chỉ test theo thứ tự của chính nó. Luật: **ai nói
ra thì thắng, nhãn location chỉ là fallback** — một helper dùng chung cho cả hai.

⚠️ **Sửa parser xong BẮT BUỘC `backfill --force`** — `city`/`salary_range`/`work_mode` là dữ liệu
**đã ghi** trong `payload`, không tính lại lúc đọc. Không chạy thì `/market` vẫn vẽ bằng số cũ và
mọi verify đều "xanh" một cách vô nghĩa.

## `match_score` — ba con số khác nhau, đừng trộn

| Ở đâu | Là gì | Ai ghi |
|---|---|---|
| cột `jobs.match_score` (trước tailor) | `stack_match_score` — tin có nhắc bao nhiêu phần `crawl.stacks` | crawler / `enrich()` |
| cột `jobs.match_score` (sau tailor) | độ phủ requirement do model chấm | `tailor_job` |
| `payload["fit"]["match_score"]` | độ phủ requirement của bản fit | `assess_fit` |

- **`assess_fit` KHÔNG đụng vào cột.** Nó là phép đo khác, và mọi job crawl về đều có cột kia; ghi
  đè cho vài job đã chấm là đem hai phép đo khác nhau xếp hạng với nhau trong một cột.
- **`PATCH /jobs` giữ lại cột khi job đã qua tailor** (`_apply_signals`, `api/routes/jobs.py`). Sửa
  location sau khi tailor mà chạy lại phép đo rẻ là **âm thầm hạ điểm** — bản payload thì vẫn
  refresh, nên `/market` không lệch.

## `FitReport.match_score` được TÍNH LẠI, không lấy của model

Đo thật trên **một** tin, cùng prompt, ba backend: **0.50 / 0.32 / 0.31**. Chênh lệch gần như hoàn
toàn đến từ **có bao nhiêu requirement bị xếp là `must_have`**, chứ không phải từ bất đồng về việc
CV có gì. Một con số nhảy 20 điểm trong khi cái list bên dưới gần như không đổi thì không phải là
một phép đo.

Nên `_recompute_score` derive điểm từ chính cái list đang hiện ra, và `verdict` bám theo điểm:

- **`soft` có trọng số 0.** CV không thể chứng minh "high growth drive" hay "product thinking"; tính
  chúng vào là đang chấm **văn phong của tin đăng**, không phải ứng viên. Chúng vẫn nằm trong list —
  một tin toàn yêu cầu tính cách là thứ đáng nhìn thấy — chỉ là không làm xê dịch con số.
  Cần thế vì model xếp `soft` **rất không ổn định**: cùng một model, cùng prompt, cùng job, lần thì
  4 `soft` lần thì 0.
- **Tin toàn `soft` → 0.5, không phải 0.0.** 0.0 đọc thành "CV bạn không đáp ứng gì cả", trong khi
  chuyện xảy ra là tin không hỏi gì mà CV có thể trả lời.
- **`verdict` derive từ điểm, và dealbreaker ép về `weak`.** "Khớp tốt · 31%" là một card dạy người
  đọc đừng tin cả hai nửa. Vẫn hỏi model cả hai field: model phải tự chấm thì nó đọc list của chính
  nó kỹ hơn.

## Vì sao KHÔNG chạy trên task queue

Cả repo, mọi lượt gọi model đều 202 + task. Hai cái ở đây thì không:

- `tailor`/`apply` rời request path ở Phase 10 vì chúng là **model call + build LaTeX** — hàng chục
  giây tới vài phút, và có một file PDF ở cuối.
- Hai cái này là **một** structured call, và user đang ngồi trước cái form. Queue chỉ có **một
  worker**: một lượt crawl chạy 5 phút trước sẽ để "đọc JD giúp tôi" nằm `queued` sau nó. Chậm còn
  hơn bị chặn.

Route khai bằng `def` (không phải `async def`) nên FastAPI chạy chúng trong threadpool — provider
chậm không treo event loop. Đo thật: extract ~3s, fit ~7s.

**Hệ quả đã cân nhắc: `assess_fit` KHÔNG `manager.broadcast`.** Mọi mutation job khác đều
broadcast `job_updated`, nhưng `manager.broadcast` là `async`, mà đổi route này thành `async def`
là đem một lượt gọi model ~7s **lên chính event loop** — chặn mọi request khác của cả app, đổi lấy
việc một tab thứ hai thấy fit mới. Đó là đánh đổi tệ hơn hẳn. Tab đang mở tự `refetch()` sau khi
bấm; tab thứ hai phải F5. Muốn có broadcast thì phải đẩy phần publish sang thread khác, là việc
riêng — **đừng** "sửa" bằng cách thêm `async`.

## Bẫy đã trả giá

- **`from jobpilot.crawler import normalize` bind vào *hàm*, không phải module.** Package re-export
  cả hai tên. Import theo tên (`from jobpilot.crawler.normalize import enrich`) — nếu không thì lỗi
  nổ lúc *chạy*, không phải lúc import.
- **`job.status` là `None` cho tới khi flush.** Default của cột do DB áp, không phải constructor.
  Đọc `job.status in _EARLY` trên một row vừa `db.add()` cho ra `False` → mọi job thêm tay từng có
  `match_score = 0.0`. Đúng cái bug mà `_apply_signals` sinh ra để sửa.
- **`posted_at` từ DB là naive, `vn_now()` là aware.** SQLite trả naive, Postgres trả aware, và
  `flags_for` so hai cái đó thì raise trên một backend chứ không phải cả hai. `enrich()` gọi
  `as_aware` một lần cho mọi caller.
- **`model_copy(update=...)` bỏ qua validator.** Test "level lạ bị drop" viết bằng `model_copy` là
  test không kiểm gì cả — provider trả JSON và pydantic **validate** nó, nên test phải dựng bằng
  `JdExtract(**...)`.
- **Prompt nói ngôn ngữ ở đâu thì model nghe ở đó.** Luật "viết bằng ngôn ngữ của tin đăng" nằm
  trong danh sách field thì bị bỏ qua (tin tiếng Việt → summary tiếng Anh, giữa dashboard tiếng
  Việt). Đưa lên thành **mục riêng ở đầu** system prompt thì đúng ngay. Đây là chuỗi backend soạn
  **duy nhất** trong app được i18n đúng, vì nó sinh ra theo từng request — khác với đống
  `facet.note`/`*_hint` ở `CLAUDE.md` gốc.
- **Field text do model điền phải qua `normalize.fit_column`.** Prompt bảo model *chép nguyên văn*
  nhãn lương, nên một tin ghi lương thành cả câu cho ra `salary` 148 ký tự → cột `VARCHAR(128)` →
  Postgres trả `StringDataRightTruncation` giữa flush ⇒ **500 không nói field nào sai**, sau khi
  user đã trả tiền cho lượt gọi model. SQLite **không** enforce width nên chỉ Postgres thật mới lộ.
  Đã clamp ở cả `POST` lẫn `PATCH /jobs`; verify lại trên Postgres thật (500 → 201, cắt đúng
  128/256).
- **CV rỗng thì từ chối, đừng chấm.** DB mới bootstrap một Master CV **rỗng** (`cv/skeleton.py`);
  gửi cái outline đó đi sẽ nhận về "weak, 0%" — một phán quyết tự tin về sự nghiệp user trong khi
  sự thật là "bạn chưa điền CV". `cv_is_unfilled()` chặn trước khi tiêu một lượt gọi. Ngưỡng
  **đo từ chính skeleton** chứ không gõ số: skeleton ra **đúng 200** ký tự (tên section là scaffold,
  không phải nội dung), nên một hằng 200 gõ tay sẽ nằm ngay trên ranh giới và cho lọt.
- **`llm bench --task intake` chỉ đo nửa việc.** Nó chấm phần *trích field*, không chấm phần *fit*.
  gpt-4o-mini 55/55 field và rẻ hơn 3 lần, nhưng hỏi 4 lần "CV có `Java, Spring Boot` thì có đáp
  ứng `working JVM knowledge` không" thì trả lời HAVE / MISSING / PARTIAL / MISSING. gpt-4.1-mini
  trả HAVE cả 4 lần. Vì thế default **không** phải cái rẻ nhất qua bench — lý do ghi ngay trong
  `config.yaml`. Muốn đổi model thì đo **cả hai** nửa.
