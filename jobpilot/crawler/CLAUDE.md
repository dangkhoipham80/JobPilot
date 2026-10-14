# `jobpilot/crawler/` — crawl job board

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Parser facet (`salary.py`, `skills.py`, `vietnam.canonical_city`) sinh dữ liệu cho trang
> `/market` — luật về facet ở `jobpilot/analytics/CLAUDE.md`.

## Thêm một site crawl mới

> Có subagent `scraper-smith` (`.claude/agents/scraper-smith.md`) đóng gói đúng quy
> trình dưới đây + toàn bộ bẫy đã gặp. Dùng nó thay vì làm tay.

0. **Đọc `robots.txt` TRƯỚC KHI viết code** (nguyên tắc 5). Nếu site cấm trang job
   thì dừng — không có cách nào "lách" cho hợp lệ (xem LinkedIn bên dưới).
1. **Tìm `<script type="application/ld+json">` có `@type: JobPosting` trước đã.** TopCV và
   VietnamWorks đều có, và đó là target tốt nhất: JD đầy đủ, `datePosted` tuyệt đối, và site có
   động lực giữ nó đúng (Google Jobs index dựa vào đó) — mạnh hơn động lực giữ tên class CSS.
   Dùng `crawler/jsonld.py`, không viết lại.
2. Tạo `crawler/<site>.py` kế thừa `BaseScraper`: `search_url()` + `parse_search()`
   + `parse_detail()`, tất cả **thuần** (HTML string → data, không network).
3. Nhận diện field **theo giá trị**, dùng `crawler/vietnam.py` (city / "thoả thuận"
   / posted / noise). Đừng match class theo substring — xem "Bài học selector".
4. `native_id` lấy từ **URL**, không bao giờ từ JSON-LD `identifier` (đó là id của
   *nhà tuyển dụng*: mọi job cùng công ty sẽ chung 1 row). Strip query tracking.
5. Normalize output về `Job` schema; set `apply_channel`/`apply_target`.
6. Test bằng snapshot HTML thật đã trim, ghim đúng các bẫy đã gặp (badge lẫn vào
   title, social proof lẫn vào location, "negotiable" thành salary).
7. Đăng ký trong `crawler/registry.SCRAPERS` + 1 dòng `config.yaml`.
8. **Crawl thật một lần** rồi đọc output — test xanh không có nghĩa là parser đúng.

**Nguồn có feed chính thức (RSS/JSON) thì kế thừa `crawler/feed.FeedScraper`**, đừng viết lại:
nó set `needs_detail = False` (feed đã có JD đầy đủ → 25 job = 1 request, không phải 26), chọn
`HttpFetcher` thay vì browser, và lo phần lọc query ở `matches_query`. Lọc theo **title + tag của
site**, không bao giờ theo JD — JD nào cũng nhắc nửa ngành công nghệ ở mục "nice to have".

**Đọc HẾT `robots.txt`, đừng `head -40`.** Jobicy để `Disallow: /api/` ở **dòng 48**; 40 dòng đầu
trông rất thoáng. Cách đáng tin duy nhất là chạy `RobotsPolicy(DEFAULT_USER_AGENT).allowed(url)`
— nó parse cả file, và nó là thứ sẽ chặn lúc crawl thật.

### Nguồn tier-2 đã loại (đừng kiểm tra lại từ đầu)

| Nguồn | Lý do loại |
|---|---|
| **Remotive** | `robots.txt`: `Disallow: /api/*` — mà API là đường duy nhất dùng được. |
| **Jobicy** | `robots.txt` dòng 48: `Disallow: /api/`. Filter `tag=` chạy rất tốt, `appliedFilters` còn echo lại — nhưng robots cấm thì dừng (nguyên tắc 5). |
| **RemoteOK** | `Content-Signal: ai-train=no, use=reference` + `User-agent: ClaudeBot → Disallow: /`. **Giống hệt TopDev** → cần một quyết định rõ ràng, không mặc định làm. |
| **Himalayas** | robots OK, nhưng API **bỏ qua mọi filter** (mọi tên param → `totalCount` y hệt 96.394, cùng job đầu) và **âm thầm cắt `limit` xuống 20**. Feed newest-first đủ mọi ngành: 2/20 title là phần mềm → crawl "thành công" và giao job bác sĩ X-quang. |

Bài học chung: một API trả 200 kèm filter bị bỏ qua **nguy hiểm hơn** một API trả lỗi.
Nếu response có field kiểu `appliedFilters` thì **check nó**, đừng tin.

## LinkedIn qua Job Alerts (không crawl)

`linkedin.com/robots.txt` **cấm** truy cập tự động vào trang job — kể cả endpoint
`/jobs-guest/` khi không đăng nhập — và mở đầu bằng *"The use of robots or other
automated means to access LinkedIn without the express permission of LinkedIn is
strictly prohibited."* Nên **không có cách crawl LinkedIn nào tuân thủ robots.txt**,
và dự án không làm (nguyên tắc 5).

Thay vào đó dùng chính cơ chế LinkedIn cung cấp: **Job Alerts**. LinkedIn gửi job
khớp vào mail của bạn, JobPilot đọc **hộp mail của bạn**. Không request nào tới
LinkedIn, không tài khoản nào bị ban.

**Cài đặt:**
1. LinkedIn → Jobs → tìm theo tiêu chí → bật **Job alert** (nên tạo 5–10 alert, đặt *Daily*).
2. Bật 2-Step Verification cho Google, rồi tạo **App Password** tại
   <https://myaccount.google.com/apppasswords> (mật khẩu Gmail thường sẽ bị từ chối).
3. Điền `IMAP_USER` / `IMAP_PASSWORD` trong `.env`.
4. Bật nguồn: `sources: - { key: linkedin, enabled: true }` trong `config.yaml`
   (hoặc bấm trên trang Settings).
5. `python -m jobpilot.cli run` — hoặc bấm **Crawl now** ở trang Runs.

**Giới hạn thật:** mail alert có title/company/location nhưng **không có JD đầy đủ**. Job vào DB
với cờ `needs_jd`; mở trang job, dán JD vào rồi mới tailor. Kênh apply luôn là `external`.

**Đã verify trên mail thật** (1.116 alert). Hai bẫy parser đã sửa + có test giữ: company và
location nằm **cùng một dòng** ngăn bằng `·`, và dòng social proof (`4 connections`) lọt vào
`location`.

**Đường thứ hai:** nút **Add job** ở trang Jobs — dán thẳng link + JD. Dùng cho job
thấy ngoài alert. Link LinkedIn cho ra id ổn định nên dán lại cùng link sẽ *update*
chứ không tạo bản trùng.

## Dedup — hai lớp, và cái bẫy "cửa sổ đo sai mốc"

Lớp 1 = PK `<source>:<native_id>`. Lớp 2 = cross-source `(company, title)` trong
`crawl.dedup_days` (mặc định 14, chỉnh được ở Settings; `0` = tắt hẳn lớp 2).

- **Cửa sổ đếm từ `last_seen_at`, KHÔNG phải `crawled_at`.** `crawled_at` là lần **đầu**
  thấy và **không bao giờ được bump** — `/stats` `by_day`, sort `order=crawled` và filter
  `crawled_after` đều đọc nó, bump là dồn mọi job từng thấy vào hôm nay (sai mà trông rất
  hợp lý). `last_seen_at` bump mỗi lần `_refresh`. Trước khi có nó, tin **vẫn đang sống**
  rớt khỏi cửa sổ của chính mình ở ngày 15 rồi bản của board khác chui vào.
- **Ranh giới với `repeat_postings` (Phase 20)**: giờ tin đăng lại chỉ vào DB khi bản cũ đã
  **thôi được nhìn thấy** đủ `dedup_days`. Đăng lại *trong khi* bản cũ còn listing → bị coi
  là trùng (trước cũng vậy nếu <14 ngày). Repost nhanh hơn `dedup_days` sau khi gỡ tin thì
  **không còn thành row riêng** — bằng chứng vẫn nằm ở `payload.dedup.suppressed` (có
  timestamp), `repeat_postings` chưa đọc chỗ đó.
- **Level chỉ tách khi CẢ HAI phía nói rõ.** `dedup_key` vẫn strip level (board bỏ chữ
  "Junior" không có nghĩa là job khác), nhưng `title_level` đi kèm bên cạnh: Senior/Junior/
  Intern cùng title cùng công ty = 3 job. `title_level` đọc **title thôi**, không dùng
  `infer_level` (nó quét cả JD, mà "we hire senior engineers" trong JD không được quyền
  quyết định hai tin là hai tin).
- **Hai tin trên CÙNG một board chỉ là một khi board đặt cho chúng cùng tiêu đề** (2026-10-14,
  `persist._same_posting`). Luật "tiêu đề không ghi level thì khớp mọi level" và việc bỏ phần trong
  ngoặc khỏi key là nhân nhượng cho **board khác** viết cùng một vai trò theo kiểu khác. Áp cho hai
  tin cùng board thì gộp những vai trò chính board đó liệt kê riêng: tin không ghi cấp bị coi là
  bản sao của bản cấp cao đứng cạnh — và bản **sống sót là bản cấp cao**, đúng nửa không ai cần.
  Cùng board + cùng tiêu đề (khác hoa thường/dấu/gạch nối/khoảng trắng thì vẫn là cùng) vẫn là một:
  đó là đăng lại dưới id mới, và là 56/65 lần gộp cùng-board đã có trong DB; 9 lần còn lại là gộp
  nhầm. So bằng `normalize_title(strip_level=False, keep_parens=True)` — **tham số thứ hai của cùng
  một hàm**, không phải hàm normalize thứ ba (bản đầu của fix này đã viết một hàm riêng).
- **`repeat_postings` sẽ thấy nhiều nhóm hơn sau fix trên, và đó là đúng.** Nó gộp theo
  `normalize_title(strip_level=False)` — vẫn bỏ ngoặc — nên các tin "X (team A)" / "X (team B)"
  cùng board, giờ là row riêng thay vì bị dedup nuốt, được đếm chung vào "tin đăng lại". Row trước
  đây bị giấu mới là cái sai; nhưng nếu cần "đăng lại đúng nghĩa" thì hàm đó phải dùng
  `keep_parens=True`.
- **Không bỏ job im lặng.** Tin bị skip được ghi lên row sống sót
  (`payload.dedup.suppressed`, cap 10, sống qua re-crawl) + log có `extra=`. Bản **có JD**
  thắng bản `needs_jd` kể cả khi bản rỗng vào trước (ca LinkedIn alert): row mới được
  giữ, hai bên link nhau bằng `supersedes`/`superseded_by`, row cũ **chỉ được annotate** —
  nó có thể đã shortlist/apply rồi, dedup không có quyền bỏ phiếu. Đếm ở `stats.superseded`
  (là **sub-count của `inserted`**, không phải bucket thứ tư).
- **Một luật normalize duy nhất** ở `text.py`: `normalize_company` + `normalize_title(strip_level=)`.
  `dedup_key` dùng `strip_level=True`, `analytics.repeat_postings` dùng `False`. Trước đây là
  hai bộ luật viết tay và **đã lệch nhau**. Thêm kiểu so sánh mới = thêm tham số, **đừng viết
  hàm normalize thứ ba**. `fold` cũng ở đây, `apply/inbox` re-export.
- **Dấu chấm cuối token là dấu tắt, không phải tech token**: `.net` mang dấu ở đầu, `node.js`
  ở giữa. Giữ nó lại làm `"Sr."` vừa không nhận ra là level, vừa tách hẳn key khỏi `"Senior"`.

## Board công ty (Greenhouse / Lever) — phạm vi địa điểm + cổng stack (2026-10-13)

Luật dưới đây đo trên hai board thật: một board cỡ vài trăm tin với khoảng 4% ở thành phố đang
tìm, một board cỡ vài chục tin với khoảng một phần tư.

**Không ghi tên công ty user đang nhắm vào repo, và cũng đừng để lại dấu vân tay của nó**: số tin
chính xác, tiêu đề tin nguyên văn, thành phố trụ sở, dạng nhãn đặc trưng trong fixture — ghép lại
là khoanh ra được một công ty. Repo public, và "đang tìm việc ở X" là thông tin cá nhân dù không
nằm trong CV. Viết tỉ lệ thay cho số đếm, loại vị trí thay cho tiêu đề.

- **`ats.locations` lọc TRƯỚC khi đếm `limit`** (trong `AtsScraper.matches_query`, tức bên trong
  vòng đi qua các board). Không có phạm vi thì `limit` tiêu vào văn phòng nào board liệt kê trước,
  và crawl vẫn báo "đủ tin, ok". Rỗng = mọi nơi (hành vi cũ, không đổi gì).
- **Khớp theo NGUYÊN TỪ, không substring** (`ats.place_matches`): "India" không được nhận
  "Indianapolis" — cùng bẫy với `"remote" in "remote debugging"`. Cách viết không chung từ nào
  ("HCMC", "Saigon", "Ha Noi") đi qua `canonical_city` của từng phần của nhãn (tách ở `, ; / | &`,
  ` - `, ` or `, ` and `); phần **≤ 2 ký tự bị bỏ qua** ở nhánh này vì trên board toàn cầu đó là
  mã bang/quốc gia (`"San Pedro Sula, HN"` là Honduras, mà bảng city đọc `HN` là Hà Nội).
- **Term "Vietnam" phải nhận ra tin trong nước dù board không viết chữ "Vietnam".** Nhãn thường chỉ
  là tên thành phố. Hai đường: nhãn mà `canonical_city` ra một thành phố Việt Nam thì thuộc
  Vietnam; và Lever có `country: "VN"` ở field riêng (`scope_hints`). Bản đầu để ví dụ
  `["Vietnam"]` trong chính `config.yaml` và nó loại **toàn bộ** tin trong nước của board Lever.
  "Việt Nam"/"Viet Nam" được coi là "Vietnam". Mã quốc gia khác **không** được đưa vào thô ("CA",
  "IN", "DE" cũng là từ và là bang), nên với nước khác term phải có mặt trong chính nhãn.
- **Gợi ý để KHỚP ≠ nhãn để LƯU** (`scope_hints` vs `places`). Bản sửa trên lúc đầu nhét "Vietnam"
  vào `places()`: phạm vi `["Vietnam"]` giữ đủ tin nhưng **lưu cả loạt với `location = "Vietnam"`,
  `city = None`** — crawl báo thành công, không tin nào còn thành phố, và `_refresh` sẽ ghi đè cả
  row đang đúng. Thứ code *suy ra* chỉ được dùng để quyết định phạm vi; thứ được lưu luôn là nhãn
  board viết. Cũng vì thế tin không có nhãn nào thì vẫn là "không biết thành phố" ⇒ giữ, dù có gợi ý.
  **Verify bộ lọc thì đọc thứ được LƯU, đừng chỉ đếm số tin trong phạm vi** — lỗi này qua được
  đúng một lượt "verify" bằng cách đếm.
- **Tin không ghi địa điểm thì GIỮ.** Không biết ở đâu ≠ biết là ở chỗ khác.
- **Lever: đọc cả `categories.allLocations`**, và **lưu nhãn đã đưa tin vào phạm vi**
  (`location_of`), không phải văn phòng đầu tiên — giữ tin vì có văn phòng trong phạm vi rồi lưu
  dưới văn phòng khác thì bộ lọc thành phố không bao giờ thấy nó.
- **Board công ty được miễn cổng stack — CHỈ KHI có `locations`** (`AtsScraper.stack_gated` là
  property = `not self.locations`). Cổng `match_score > 0` dọn tin lạc đề khỏi board *tìm kiếm*.
  Trên board đã khoanh vùng nó loại đúng các tin kỹ sư phần mềm không ghi stack trong JD: cùng một
  mức `limit`, cổng giữ khoảng **một phần năm** số tin trong phạm vi, miễn thì **hơn một nửa**
  (phần còn lại bị loại theo tiêu đề, luật đó **vẫn áp dụng**). Không khoanh vùng thì **không
  miễn**: query khớp bất kỳ từ nào của tiêu đề, nên "ai engineer" trên cả board lấy luôn vài chục
  tin kỹ sư **không phải phần mềm** ở score 0. Tin được miễn vào với `match_score = 0` — hiện ra,
  thấy rõ là chưa xếp hạng.
- **`limit` đếm SAU khi lọc tiêu đề** (2026-10-14, § "Lọc tiêu đề trước `limit`" bên dưới). Trước đó,
  ở `jobs_per_site: 10`, hơn nửa số chỗ của một board bị tin cấp cao chiếm rồi mới bị loại, và phần
  bị cắt lại chính là các tin không ghi cấp bậc — board trả cùng thứ tự mỗi lần nên lượt sau cắt
  **đúng những tin đó**. Còn lại: `limit` vẫn cắt tin *hợp lệ* nằm sau vị trí N (log `at least N …
  were cut by the limit`), nên lượt đầu cho một board mới vẫn nên crawl tay với limit cao.
- **Nợ: nhiều board trên một ATS dùng chung một `limit`.** Board đầu đủ `limit` thì board sau
  **không được gọi**, và log không nhắc tới nó. Hôm nay mỗi ATS một board nên chưa dính.
- **Nợ: `payload.city` của Greenhouse không canonical** — nhãn dạng `"<thành phố>, <thành phố>,
  <nước>"` đi qua `canonical_city` nguyên xi, nên facet thành phố ở `/market` không đếm nó vào
  đúng thành phố (Lever ghi tên thành phố trần thì đúng).
- **Nợ: `infer_level` không đọc bậc ghi bằng số trong tiêu đề** ("… Engineer I/II/III") — level rơi
  về những gì JD tình cờ nhắc, nên một tin bậc thấp có thể ra `senior`.

## Nợ kỹ thuật + bẫy đã trả giá

- **Tiêu đề VietnamWorks còn nguyên thực thể HTML** (thấy 2026-10-13, **chưa sửa**): DB có tin
  `Java Developer (&gt;5 YOE)`. Title đến từ JSON-LD và không qua `html.unescape` — sửa ở chỗ đọc
  JSON-LD (`jsonld.py`) rồi `backfill`, đừng vá ở frontend.

- **Nguồn đang chạy**: ITviec + TopCV + VietnamWorks + LinkedIn(alerts) + WeWorkRemotely + Arbeitnow chạy thật; chỉ TopDev còn chưa có scraper (disabled trong config). Trang Runs chỉ cho chọn nguồn `enabled && ready` — `ready` = có scraper đăng ký trong `registry.SCRAPERS`, vì bật trong Settings không có nghĩa là đã implement. Cần `pip install -e '.[crawler]' && playwright install chromium` để crawl (2 nguồn tier-2 **không cần** Playwright).
- **Bật nguồn trên máy đã dùng Settings**: `config.local.yaml` merge **theo key** nên nguồn mới trong `config.yaml` luôn hiện ra; nhưng key nào overlay từng ghi `enabled: false` thì vẫn tắt. Bật lại trong Settings, hoặc xoá `config.local.yaml`.
- **VietnamWorks lazy-load — xử lý bằng phân trang, không phải scroll**: 1 fetch chỉ render ~9–20 card, nhưng `search()` đi tiếp `?page=N` nên `jobs_per_site` > 9 vẫn đủ hàng (verify thật: 9 → **29 job**; trang 3 lặp lại trang 2 và bị guard bắt). Giữ `PlaywrightFetcher` là `(url) -> html` thuần — scroll sẽ đổi contract dùng chung cho mọi site, phân trang thì không.
- **TopCV thực tế chỉ ~50 job/lần crawl**: request thứ 2 trong cùng session bị Cloudflare chặn (403). Không phải bug — mặc định `jobs_per_site: 10` không chạm tới, và khi chạm thì báo "blocked — anti-bot" rồi giữ 50 hit của trang 1. **Query dài cũng làm TopCV trả 0 job**: keyword vào *path* nên "Java Spring Boot Backend" thành slug 4 từ; `default_query` = 3 stack đầu nên đổi thứ tự `crawl.stacks` là đổi chất lượng search.
- **Nguồn tier-2 là remote/toàn cầu** (WWR: US/worldwide; Arbeitnow: Đức/EU) và **thiên về senior**, nên `exclude_keywords: [Senior, Lead, ...]` mặc định lọc đi khá nhiều. Tắt trong Settings nếu chỉ muốn job Việt Nam.
- **TopDev**: robots `Allow: /` cho `*` nhưng chặn riêng `ClaudeBot` + `Content-Signal: ai-train=no`. Chưa làm — cần một quyết định rõ, không mặc định làm.
- **Bài học selector (ITviec)**: site dùng utility CSS nên **match class theo substring là bẫy** — `[class*=city]` khớp `opa-city-50` (mọi job thành location `"Hiring"`), `[class*=salary]` bắt trúng banner "IT Salary Report". Location/posted/salary nhận diện **theo giá trị** (`crawler/vietnam.py`, dùng chung cho cả 3 site VN), không theo cấu trúc. ITviec giấu lương sau login → `salary=None` là câu trả lời đúng. `test_itviec.py` ghim các bẫy này.
- **SQLite KHÔNG enforce `VARCHAR(n)`, Postgres thì có.** Field quá dài chỉ nổ trên Postgres thật, và nó nổ *giữa flush*. `normalize._fit()` clamp `title/company/location/salary` theo width cột (payload vẫn giữ text đầy đủ); **`id` cũng vậy** — `types.make_job_id()` giữ đầu id + nối digest 12 ký tự khi `<source>:<native_id>` > 128 (ITviec để nguyên tên pháp nhân của NTD trong slug → id 134 ký tự, 2026-10-04). Digest tính trên **cả** id nên vẫn deterministic: crawl lại rơi đúng row cũ. Job thêm tay (`manual:`) đi qua cùng hàm. Verify crawl phải chạy qua **Postgres thật**, không chỉ SQLite.
- **Lỗi DB chỉ được phép tốn đúng một row.** `persist_jobs` ghi mỗi job trong một `begin_nested()` savepoint, `run_crawl` bọc mỗi site trong một savepoint nữa. Trước đó một row bị Postgres từ chối để lại session ở `PendingRollbackError` và **mọi site chạy sau** fail theo (6/6 nguồn đỏ vì một tin). Row hỏng giờ thành **`rejected += 1`** (không phải `errors` — `errors` đếm *site* fail) + log `persist_failed`; CLI in site đó là **`PART`** kèm `REJECTED=n`, trang Runs có cột riêng tô đỏ. Tách ra vì gộp chung thì một site mất *mọi* row trông y như "chạy ổn, không có job mới". Đừng `index.add()` hay đếm stats *bên trong* savepoint — chỉ sau khi nó commit, nếu không row bị từ chối vẫn che bản copy tiếp theo **trong cùng site** (index dựng lại mỗi lần gọi `persist_jobs`, tức mỗi site) — `test_a_refused_row_does_not_shadow_or_annotate_the_job_it_matched` ghim luật này.
- **Đừng quét salary trên cả body detail.** Body detail của TopCV chứa panel "việc làm tương tự", card trong đó **có lương riêng** sau khi hydrate → 2 job không liên quan cùng ra "20 - 60 triệu". Salary chỉ lấy từ nguồn chắc chắn thuộc job này: card của chính nó, hoặc `baseSalary`; không có thì `None`. `parse_salary` có guard `MAX_SALARY_LEN=80` — lương là *label*, không phải đoạn văn (từng trả nguyên blob 6.7 KB JD làm salary).
- **`select_one("a, b")` KHÔNG theo thứ tự selector** mà theo thứ tự trong document. Trên card VietnamWorks link logo đứng trước `h2 a` nên one-liner lấy trúng logo và title lặng lẽ đến từ sai element. Dùng `_first(root, *selectors)` khi thứ tự ưu tiên là có ý.
- **Fetch strategy**: `PlaywrightFetcher` load bằng `domcontentloaded` rồi *cố* chờ `networkidle` 6s, timeout thì bỏ qua. Chờ `networkidle` như **điều kiện** load là bẫy: job board chạy analytics/socket không bao giờ im → trang render xong nhưng `goto` treo tới timeout rồi fail cả crawl. Nó cũng **raise theo status code**: trang chặn (403/429) là một *trang* hợp lệ với parser, không chặn ở tầng fetch thì lặng lẽ thành "0 job".
- **Chọn fetcher theo thứ site phục vụ**: `HttpFetcher` cho document (RSS/JSON/HTML server-render), `PlaywrightFetcher` cho app (ITviec/VNW). Đừng dùng chung 1 fetcher cho mọi scraper trong production — `build_scrapers(fetcher=...)` chỉ dành cho test, vì browser bọc JSON thành `<pre>` và feed parser vỡ.
- **`infer_level` vẫn quét cả JD**, nên JD nhắc "we hire senior engineers" có thể kéo job mid thành senior. Phần substring đã sửa, phạm vi quét thì chưa — thu về title-only sẽ mất job VN ghi "thực tập sinh" trong body.

### Lọc tiêu đề trước `limit` (2026-10-14)

- **`crawl.exclude_keywords` được hỏi trên tiêu đề của LISTING, trong `BaseScraper.search`** — trước
  khi hit được đếm vào `limit` và trước khi tải trang chi tiết. Trước đó pipeline loại đúng các tiêu
  đề này nhưng *sau* khi `limit` đã tiêu vào chúng. Đo trên trang listing thật của 3 board VN với 3
  từ khoá của lịch tự động: **34/87 chỗ đầu** thuộc về tiêu đề bị loại, mỗi chỗ tốn một request
  trang chi tiết rồi vứt. Giờ các chỗ đó thuộc về tin được giữ; giá phải trả là thêm trang
  **listing** khi trang 1 không đủ `limit` tiêu đề qua lọc — thường một trang, tối đa
  `max_pages − 1` (ITviec 20 card/trang; VietnamWorks ~9, và một trang đã lưu của nó chỉ có 3/9
  tiêu đề qua lọc). Keyword được so **nguyên văn, kể cả dấu cách**; chỉ entry rỗng bị bỏ qua.
- **Một matcher duy nhất: `normalize.title_excluded`.** Scraper và pipeline gọi cùng một hàm; đừng
  viết bản thứ hai trong scraper. **Pipeline vẫn kiểm lại** — tiêu đề trên card là cái nhìn đầu,
  tiêu đề trên trang chi tiết mới là thứ được lưu. Đối chiếu 59 tin đã lưu với card của chính nó:
  59/59 cùng kết luận, nhưng đó là số đo, không phải bảo đảm.
- **Mặc định TẮT với scraper dựng trần** (`exclude_keywords=()`); chỉ `registry.build_scrapers` đưa
  danh sách từ config vào. Test dựng scraper bằng tay muốn lọc sớm thì phải truyền vào.
- **Hit không có tiêu đề thì GIỮ** — không biết tên ≠ biết là bị loại; trang chi tiết sẽ trả lời.
- **`fetched` và `filtered` giữ nguyên nghĩa**: `fetched` = số tin crawl đã *nhìn*, `filtered` = số
  trong đó bị luật loại. Tin bị loại sớm (`scraper.titles_dropped`) được cộng vào **cả hai**; không
  cộng thì cùng một board hôm trước báo "10 found, 6 filtered", hôm sau báo "10 found, 0 filtered".
  Hệ quả: `fetched` có thể **lớn hơn `limit`** (10 giữ + 12 loại = 22) — nó chưa bao giờ là số
  request. `titles_dropped` chỉ đếm tới **điểm `limit` được lấp đầy**: tiêu đề bị loại xếp sau tin
  cuối cùng được giữ thì chưa từng nằm trong cửa sổ của lượt crawl này (board công ty trả cả listing
  một lần — đếm hết thì con số thành "mọi tin cấp cao công ty đó có").
- **Trang toàn tiêu đề bị loại không phải parser hỏng**: cảnh báo "0 hits — selectors no longer
  match" chỉ phát khi không có hit nào *và* không tiêu đề nào bị loại.
- **Keyword rỗng bị bỏ qua** (`"" in title` đúng với mọi tiêu đề): một dòng trống trong danh sách
  từng có nghĩa là loại cả crawl; với lọc sớm nó còn kéo mỗi board đi tới `max_pages`.
- **Nợ: danh sách loại trừ càng gắt thì đi càng sâu**, chặn trên bởi `max_pages`. TopCV bị 403 ở
  request listing thứ hai, nên nếu 50 card trang 1 không đủ `limit` tiêu đề qua lọc thì site đó về
  thiếu (có log `only N hit(s)`), không lấy thêm được.
- **Nợ: LinkedIn alerts tự viết `crawl()`** nên vẫn cắt `limit` rồi mới lọc (ở pipeline). Không tốn
  request nào — nó đọc mail — nhưng tin bị loại vẫn chiếm chỗ trong `limit`.
- **Nợ: `title_excluded` khớp SUBSTRING** — "Lead" loại cả "Leading …", và "Sr."/"Principal"/"Staff"
  không bị loại trừ khi user thêm vào danh sách. Đổi sang nguyên từ là đổi luật lọc cho mọi nguồn,
  việc riêng.

### Nhiều từ khoá + crawl lại (2026-10-04)

- **Dấu phẩy tách *lượt tìm*, dấu cách thì không** (`pipeline.split_queries`, mirror ở
  `CrawlSetup.splitKeywords`): `"java, spring boot"` = 2 lượt; "spring boot" là một cụm với board.
  Bỏ trùng không phân biệt hoa thường; **tối đa `MAX_QUERIES` = 8** — vượt thì **422**, không cắt
  bớt (cắt im lặng = báo crawl đã tìm thứ bạn không hỏi).
- **Vòng lặp là site ngoài, từ khoá trong**: mỗi site chạy hết các từ khoá rồi mới `close()`.
  Savepoint theo (site, từ khoá). Site chỉ `ok=False` khi **mọi** từ khoá đều fail (một từ thì đúng
  luật cũ). **Fail một phần phải hiện ra**: `errors` cộng theo từng lượt tìm hỏng, `error` có tên từ
  khoá, CLI in `PART … FAILED:`, trang Runs in dòng ⚠ dưới site, lịch sử in `java: failed` — review
  bắt bản đầu hiện từ khoá bị chặn y như `java: +0`.
- **Rate limit nằm ở `BaseScraper._fetch`, không ở call site** (review bắt): `RateLimiter` không giữ
  trạng thái, và bản cũ chỉ `wait()` trước trang 2+ và trang chi tiết — đủ khi mỗi run một lượt tìm,
  hổng ngay khi có nhiều: trang 1 của từ khoá sau bắn sát request cuối của từ khoá trước (Greenhouse 4
  từ = 4 GET liền nhau, 0 sleep). Giờ: chờ trước **mọi** request trừ request đầu của run. Thêm
  **memo URL theo run** (xoá ở `close()`): feed/ATS lọc tại chỗ nên listing giống nhau mọi từ khoá →
  tải một lần; trang chi tiết của job hai từ khoá cùng thấy → không tải lại. Lỗi không được memo.
- **`query_aware = False`** (LinkedIn alerts — đọc mail, bỏ qua query): chạy **một lần** mỗi run, không
  gán cho từ khoá nào trong `by_query` — nếu không mọi job dồn vào từ khoá đầu và thành "updated" ở
  các từ sau. Nên tổng `by_query` có thể nhỏ hơn `totals`.
- **Ngữ nghĩa bộ đếm khi nhiều từ khoá**: `fetched`/`updated` là **lượt nhìn thấy**, không phải số job
  — job do 2 từ khoá cùng thấy được đếm `updated` ở từ thứ hai. `inserted` vẫn là số job mới thật.
- **`Run.stats.request = {queries, sources, limit}`** là thứ làm "Crawl lại y hệt" được:
  `GET /crawl/recent` trả đúng shape `POST /crawl` nhận, frontend gửi lại **nguyên** item. Gộp các
  cấu hình trùng (lịch tự động lặp 2 lần/ngày, không được đẩy mất lượt tìm một-lần). Run cũ không có
  `request` được đọc ngược từ `query` + key của `sites`, `limit` = không biết (mặc định).
- **Lịch tự động đọc `crawl.queries`**; rỗng thì giữ query cũ ghép từ 3 stack đầu (config cũ chạy y
  như trước — dù query đó dài tới mức TopCV trả 0).
