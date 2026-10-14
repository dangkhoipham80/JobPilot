# 🤖 JobPilot — tự động hoá CV, chạy trên máy của bạn

[English](README.md) · **Tiếng Việt**

> Crawl việc làm cho dev → duyệt trên dashboard local → tailor CV theo một tin → duyệt phần thay đổi → nộp đơn → theo dõi phản hồi.
> Xây trên template LaTeX [Awesome-CV](https://github.com/posquit0/Awesome-CV), và phần template này dùng riêng cũng được.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![Postgres](https://img.shields.io/badge/PostgreSQL-17-blue?logo=postgresql)](https://www.postgresql.org/)
[![Tectonic](https://img.shields.io/badge/Tectonic-LaTeX%20build-blue?logo=latex)](https://tectonic-typesetting.github.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Repo có hai lớp:

1. **CV template** — bộ khung LaTeX của Awesome-CV (`awesome-cv.cls`, `fontawesome.sty`, `fonts/`),
   build bằng tectonic. Dùng riêng cũng được; xem [Chỉ dùng phần dựng CV](#-chỉ-dùng-phần-dựng-cv).
2. **JobPilot** — pipeline FastAPI + React + PostgreSQL: crawl việc làm, dùng LLM tailor CV theo
   từng tin, gửi đơn và theo dõi kết quả. Kiến trúc ở [`PLAN.md`](PLAN.md), quy tắc tailor CV ở
   [`SKILL.md`](SKILL.md), hướng dẫn đóng góp ở [`CONTRIBUTING.vi.md`](CONTRIBUTING.vi.md).

> **Repo này không chứa CV nào.** Tên, email, kinh nghiệm và mọi bản CV đã tailor của bạn nằm trong
> bảng `cv_versions` của Postgres trên máy bạn. Database mới sẽ có sẵn một CV *rỗng* để bạn điền
> trong CV Studio. `jobpilot/cv/sample.py` là dữ liệu hư cấu, chỉ dùng cho test.

---

## 🧭 Nó làm gì

```
crawl các nguồn ──▶ dashboard Jobs ──▶ bạn chọn tin ──▶ model tailor CV
                                                              │
                        bạn duyệt / sửa phần thay đổi ◀────────┘
                                      │
              email (tự động, 3 chốt an toàn) │ portal & external (bạn tự bấm nộp)
                                      │
                                      ▼
          replied · interview · offer · rejected ◀── hộp thư gợi ý, bạn xác nhận
```

Ba luật mà code được xây quanh:

- **Không bịa kinh nghiệm.** Agent tailor chỉ được sắp xếp lại, bỏ bớt hoặc diễn đạt lại những gì
  đã có trong CV. Schema của plan dựa trên chỉ số (index), nên "thêm một skill bạn không có" là
  thứ không thể biểu diễn được.
- **Mọi thứ rời khỏi máy đều phải được bạn duyệt**, trừ kênh email sau khi bạn bật nó một cách rõ
  ràng (và nó vẫn chạy dry-run cho tới khi bạn tắt nốt chế độ đó).
- **Tôn trọng robots.txt và rate limit.** Nguồn nào cấm truy cập tự động thì không crawl — xem
  [Nguồn](#-nguồn).

### Dashboard

Mười một trang, ở `localhost:5173` khi dev (hoặc ở `:8000`, do API phục vụ, sau khi đã build `web/`):

| Trang | Dùng để làm gì |
|---|---|
| **Deck** | Phễu và các con số trong ngày |
| **Jobs** | Mọi tin đã crawl, lọc được; chọn hoặc bỏ qua ngay trên từng dòng |
| **CV Studio** | Trình sửa có cấu trúc cho Master CV, lịch sử version, so sánh hai version bất kỳ; nhập CV có sẵn từ ảnh, PDF hoặc text dán vào thành bản nháp để bạn soát rồi mới lưu |
| **Applications** | Bảng các đơn đã gửi theo từng giai đoạn; nhắc follow-up và gợi ý từ hộp thư |
| **Companies** | Nhà tuyển dụng và liên hệ HR; email HR có thể trở thành nơi nhận đơn của một tin |
| **Runs** | Bắt đầu một lượt crawl, xem hàng đợi, đọc lịch sử chạy |
| **Market** | Corpus đã crawl trông ra sao — skill, lương, thành phố, cấp bậc |
| **Models** | Chọn provider và model theo từng việc; chi phí, độ trễ và tỉ lệ qua guardrail lần đầu theo từng backend |
| **Backup** | Backup database: đang có những bản nào, chạy một bản ngay, và lệnh khôi phục |
| **Settings** | Nguồn, phạm vi crawl, các chốt khi nộp — ghi vào một file overlay đã gitignore |
| **Guide** | Cả pipeline khớp với nhau thế nào |

Danh sách được phân trang ở server, kích thước trang do bạn chọn cho từng danh sách
(10/25/50/100) và được nhớ giữa các lần mở.

---

## 🚀 Bắt đầu nhanh

```bash
# 1. cài đặt (các extra là tuỳ chọn; `all` lấy hết)
pip install -e '.[all]'
playwright install chromium          # chỉ cần cho ITviec / TopCV / VietnamWorks

# 2. trỏ tới một database và đặt API token local
cp .env.example .env                 # DATABASE_URL + JOBPILOT_API_TOKEN, cộng key của
                                     # provider bạn chọn (xem Model)
psql -U postgres -c "CREATE DATABASE jobpilot;"
alembic upgrade head

# 3. chạy
uvicorn jobpilot.api.main:app --reload    # API + WebSocket ở :8000
cd web && npm install && npm run dev      # dashboard ở :5173
```

Thay token `changeme` trước bước 3: backend từ chối khởi động nếu token là giá trị mẫu hoặc ngắn
hơn 20 ký tự. Đặt cùng giá trị đó trong `web/.env.local` dưới tên `VITE_API_TOKEN` (xem
`web/.env.example`), nếu không dashboard sẽ nhận 401.

`make dev` bật Postgres và API; dashboard cần một terminal riêng (`make web`), vì
`uvicorn --reload` chặn terminal và Makefile chạy các bước theo thứ tự.

Mọi thứ bind vào `localhost` và được bảo vệ bằng token trong `.env` — đây là công cụ local cho
một người dùng, không phải dịch vụ để mở ra ngoài.

### CLI dùng hằng ngày

```bash
python -m jobpilot.cli crawl                          # crawl mọi nguồn đang bật
python -m jobpilot.cli crawl --query "java spring" --limit 30
python -m jobpilot.cli run --every 60                 # vòng lặp đơn giản cho cron
python -m jobpilot.cli backfill --force               # tính lại facet sau khi sửa parser
python -m jobpilot.cli cv seed                        # tạo Master CV rỗng nếu chưa có
python -m jobpilot.cli cv read scan.png -o my-cv.local.json   # AI đọc ảnh/PDF thành bản nháp (không lưu gì)
python -m jobpilot.cli cv read --text cv.txt -o my-cv.local.json   # như trên, từ một file text
python -m jobpilot.cli cv import my-cv.local.json     # nạp một CV vào DB
python -m jobpilot.cli cv export my-cv.local.json     # backup ra file (đã gitignore)
python -m jobpilot.cli cv build                       # render JSON → .tex → PDF
python -m jobpilot.cli tailor <job_id>                # cần key của provider đang cấu hình
python -m jobpilot.cli apply <job_id>
python -m jobpilot.cli confirm-submit <job_id>        # bạn đã tự nộp một đơn portal/external
python -m jobpilot.cli llm providers                  # việc nào chạy bằng gì, còn thiếu key nào
python -m jobpilot.cli llm stats                      # chi phí, tỉ lệ qua lần đầu, độ trễ theo backend
python -m jobpilot.cli llm bench --task classify      # chấm một backend trên bộ có đáp án
pytest jobpilot/tests
```

Giữ từ khoá ngắn. Nó thành từ tìm kiếm ở từng site, và một từ khoá quá cụ thể
("Java Spring Boot Backend") hoàn toàn có thể không khớp tin nào.

---

## 🧠 Model

Không có gì gắn cứng vào một nhà cung cấp. Provider và model được chọn **theo từng việc** —
`tailor`, `letter`, `classify`, `intake` — trong `jobpilot/config.yaml` hoặc từ trang **Models**
(trang này ghi vào file overlay đã gitignore):

```yaml
llm:
  provider: claude          # mặc định cho việc nào không đặt riêng bên dưới
  tailor: ""                # "" = dùng `provider`
  letter: ""
  classify: ""              # vd openai — lượt gọi rẻ và dễ
  intake: ""                # đọc JD dán vào và chấm độ khớp với CV
  models:
    claude: claude-opus-4-8
    openai: gpt-4.1
    gemini: gemini-3.5-flash
```

Thêm một backend là thêm một mục trong `llm/registry.PROVIDERS` cùng một module client — không
phải sửa một `Literal` ở bốn chỗ. Các provider gọi qua API không nhận cùng một JSON Schema, nên `llm/schema.py`
chuyển đổi cho từng bên (tập con của Gemini, strict mode của OpenAI).

Provider thứ tư, `claude_cli`, chạy cùng các model Claude qua CLI `claude` trên máy, tính vào gói
Claude của bạn thay vì tính tiền theo token. Nó chỉ dành cho việc dùng cá nhân trên máy của bạn.

**Đo, đừng đoán.** Mọi lượt gọi — kể cả lượt bị guardrail chống bịa từ chối và lượt lỗi — đều ghi
một dòng vào `llm_calls`. Đọc bằng `jobpilot llm stats` hoặc trang Models: chi phí, độ trễ, và tần
suất một plan qua guardrail ngay lần đầu. `jobpilot llm bench` chạy lại một bộ chấm cố định, để
"rẻ nhất mà vẫn dùng được" là một kết quả đo chứ không phải cảm giác. Mẫu nhỏ thì hiện
`n=<số lượng>` thay cho phần trăm — ở n=5 bài bench này từng xếp một model nhanh nhất, tới n=10
hoá ra nó chậm nhất.

Hai giới hạn cần nói thẳng:

- **Chỉ có một cảnh báo riêng tư đáng kể: gói miễn phí của Gemini.** Anthropic, OpenAI và Gemini
  bản trả phí không train trên dữ liệu gửi qua API. Gemini miễn phí thì có, và điều khoản của nó
  nói đừng gửi thông tin cá nhân — đúng là thứ `tailor` và `letter` gửi đi, vì cả Master CV nằm
  trong system prompt. Đặt `llm.gemini_paid_tier: false` thì JobPilot cảnh báo trước mỗi lượt gọi
  như vậy. Nó chỉ cảnh báo, không chặn.
- **"Credit còn lại" là bộ đếm ngân sách, không phải số dư tài khoản.** Anthropic, OpenAI và
  Google đều đòi admin key cho endpoint chi phí, nên con số này là `llm.budget_usd` của bạn trừ đi
  phần JobPilot đo được. Model không có mục trong `llm/pricing.py` được tính là chưa có giá chứ
  không phải miễn phí, và mọi tổng đều ghi rõ có bao nhiêu model như vậy.

---

## 🔎 Nguồn

Cấu hình trong `jobpilot/config.yaml`, bật tắt ở trang Settings. Thêm một nguồn là thêm một
scraper cùng một dòng config (`PLAN.md` §5.1.1).

| Nguồn | Tier | Cách đọc | Ghi chú |
|---|---|---|---|
| **ITviec** | 1 | Playwright | Sau Cloudflare; lương phải đăng nhập mới thấy, nên `salary` là `null` |
| **TopCV** | 1 | Playwright | Render ở server + `JobPosting` của schema.org. Từ khoá nằm trong *path*, không phải `?keyword=` |
| **VietnamWorks** | 1 | Playwright | Tin về qua XHR; lazy-load khoảng 9–20 thẻ mỗi trang, nên phải đi từng trang |
| **LinkedIn** | 1 | IMAP | Đọc **email Job Alert trong hộp thư của chính bạn**. Không bao giờ crawl LinkedIn |
| **We Work Remotely** | 2 | RSS | Mỗi category một feed, JD đầy đủ ngay trong feed, không cần browser |
| **Arbeitnow** | 2 | JSON API | Phân trang thật; chủ yếu Đức/EU, mô tả thường bằng tiếng Đức |
| **Greenhouse** | 3 | Board JSON API | Mọi công ty dùng Greenhouse. Mặc định tắt — liệt kê các board bạn theo dõi |
| **Lever** | 3 | Board JSON API | Mọi công ty dùng Lever. Mặc định tắt |
| TopDev, Ashby | — | — | Cố ý không có — xem bên dưới |

Nguồn tier-2 là việc remote/toàn cầu. Tắt chúng trong Settings nếu bạn chỉ muốn việc ở Việt Nam.

**Tier 3 — trang tuyển dụng của công ty.** Phần lớn công ty không tự xây job board mà thuê một
cái, và một vị trí thường xuất hiện ở đó trước khi tới các trang tổng hợp. Một adapter phủ mọi
công ty trên cùng nền tảng, nên theo dõi thêm một công ty chỉ là thêm một từ trong `config.yaml`,
không cần code:

```yaml
ats:
  greenhouse: [gitlab, grafanalabs, elastic]   # slug trong job-boards.greenhouse.io/<slug>
  lever:      [palantir, spotify]              # slug trong jobs.lever.co/<slug>
  locations:  ["Ho Chi Minh"]                  # tuỳ chọn — chỉ giữ tin ở những nơi này
```

Sau đó bật `greenhouse` / `lever` trong Settings. Mỗi board là một request mỗi lượt crawl, nên
danh sách dài thì crawl chậm. Board của một công ty là toàn cầu, nên hãy đặt `locations` trừ khi
bạn muốn mọi văn phòng: nó khớp theo nguyên từ với nhãn địa điểm của chính tin đó, bỏ qua dấu, và
biết các cách viết thường gặp của thành phố Việt Nam ("HCMC", "Saigon", "Ha Noi"). "Vietnam" khớp cả nhãn
chỉ ghi tên một thành phố Việt Nam; với nước khác thì term phải là thứ board thật sự viết ra, mà
nhiều board chỉ ghi tên thành phố. Khi đã đặt `locations`, tin từ các board
này được giữ kể cả khi mô tả không nhắc `crawl.stacks` nào (công ty và nơi làm là do bạn chọn) và
khi đó hiện độ khớp 0%; luật loại theo tiêu đề vẫn áp dụng. Không đặt `locations` thì bộ lọc stack
vẫn bật, vì từ khoá khớp bất kỳ từ nào của tiêu đề và một board toàn cầu có rất nhiều "engineer".

**Nguồn cố ý không thêm.** Vài nguồn đã được đánh giá và loại — đọc
[`jobpilot/crawler/CLAUDE.md`](jobpilot/crawler/CLAUDE.md) → *"Nguồn tier-2 đã loại"* trước khi
thêm nguồn mới, để khỏi kiểm tra lại từ đầu:

- **Remotive**, **Jobicy** — `robots.txt` cấm `/api/`, mà đó là endpoint duy nhất có ích.
- **RemoteOK**, **TopDev** — `Content-Signal: ai-train=no, use=reference` cộng thêm chặn
  `ClaudeBot`. Chưa hẳn là cấm, nhưng cần một quyết định có cân nhắc chứ không phải mặc định.
- **Ashby** — `api.ashbyhq.com` không trả `robots.txt` nào (401), còn `jobs.ashbyhq.com` thì cấm
  `/api/`. Không có robots không có nghĩa là được phép.
- **Himalayas** — robots ổn, nhưng API bỏ qua mọi tham số lọc và lặng lẽ giới hạn `limit` ở 20,
  nên một lượt crawl sẽ "thành công" và trả về việc của ngành khác.

Một API trả 200 trong khi bỏ qua bộ lọc của bạn nguy hiểm hơn một API trả lỗi. Nếu response có
trả lại thứ gì kiểu `appliedFilters` thì hãy kiểm tra nó.

> Đọc **hết** `robots.txt` trước khi viết scraper. `Disallow: /api/` của Jobicy nằm ở dòng 48;
> một lệnh `head -40` làm nó trông như cho phép, và chỉ khi chạy thật qua `RobotsPolicy` mới bắt
> được.

---

## 📬 Sau khi nộp đơn

Nộp đơn là đoạn giữa của câu chuyện, không phải đoạn kết.

- **Follow-up.** Đơn nào im lặng lâu sẽ nổi lên trên bảng kèm một lời nhắc gợi ý. Không có gì
  được gửi đi — follow-up là tin nhắn tới người đang quyết định về bạn, nên luật chặn việc nộp đơn
  cũng chặn việc này.
- **Kết quả.** Ghi `replied`, `interview`, `offer`, `rejected`, `withdrawn` hoặc `ghosted` cho
  từng đơn, có lịch sử. Hai loại cuối do bạn tự khai — không bộ đếm nào quyết định hộ rằng bạn bị
  ghost. Tỉ lệ được tính từ mốc xa nhất mà một đơn *từng đạt tới*, không phải vị trí hiện tại của
  nó; nếu không thì tỉ lệ phỏng vấn sẽ tụt khi phỏng vấn chuyển thành offer.
- **Đồng bộ hộp thư** (mặc định tắt). Khi có thông tin IMAP, JobPilot đọc hộp thư *của bạn*, khớp
  thư với đơn ngay trên máy, rồi mới hỏi model xem một thư đã khớp có nghĩa là gì. Thư không thuộc
  đơn nào thì không bao giờ rời khỏi máy. Mỗi gợi ý đều trích dòng nó đã đọc, và không có gì được
  ghi cho tới khi bạn bấm nút.

Bật ở `apply.inbox` cùng `IMAP_USER` / `IMAP_PASSWORD` — với Gmail thì phải là
[App Password](https://myaccount.google.com/apppasswords), không phải mật khẩu tài khoản.

---

## 📄 Chỉ dùng phần dựng CV

Bộ khung LaTeX chạy độc lập được — đặt một file `cv.tex` cạnh `awesome-cv.cls` rồi chạy:

```bash
# tectonic — một binary tĩnh, không cần daemon (https://tectonic-typesetting.github.io)
tectonic -X compile cv.tex
```

Kết quả là `cv.pdf` trong cùng thư mục. JobPilot dùng đúng engine đó, ghi các bản tailor ra
`out/cv/<scope>/` và không bao giờ đụng vào bản master.

Tectonic là engine duy nhất: khoảng 10 MB, không có gì chạy nền, có binary cho x86-64 và ARM64.
(Image Docker `csmith/awesome-cv-builder`, 3.18 GB và cần daemon, từng là đường lui và đã bị gỡ;
config còn ghi `cv.engine: docker` sẽ nhận một lỗi build nói rõ điều đó.)

Tectonic được tìm trên `PATH` trước, rồi tới **`tools/`** trong repo — nên trên máy mà bạn không
muốn đụng vào `PATH`, thả binary đã tải vào `tools/` là đủ, không cần cấu hình gì.
(`cv.tectonic_bin` vẫn dùng được, nhưng một đường dẫn tuyệt đối chỉ đúng trên một máy.)

Nên sửa qua **CV Studio** thay vì sửa tay: nội dung là JSON có cấu trúc, được chuyển thành `.tex`
qua Jinja2, nên `.tex` sửa tay sẽ không quay ngược lại được thành JSON. Đổi màu nhấn bằng
`theme.color` trong Studio, đừng sửa trong `.cls`.

**Xử lý sự cố.** Lần chạy đầu, tectonic tải các gói TeX mà tài liệu cần rồi cache lại (khoảng
50 MB) theo từng user, nên lần build đầu cần mạng và chậm; các lần sau chạy offline. Cài extra
`[cv]` để có `pypdf`, nếu không số trang sẽ hiện là không rõ.

---

## 🗺️ Cấu trúc dự án

```
jobpilot/
  api/        FastAPI: REST + WebSocket, mỗi bề mặt một module route · paging.py
  crawler/    base.py (hợp đồng + vòng lặp phân trang) · mỗi nguồn một module · feed.py cho RSS/JSON
  cv/         schema CvDocument · Jinja2 → .tex · compile LaTeX · kho version · ats.py
  tailor/     schema plan theo index · guardrail chống bịa · engine gọi model · diff
  apply/      cover letter · email (3 chốt) · chuyển giao cho portal · dispatcher
              followup.py (nhắc) · outcome.py (chuyện gì đã xảy ra) · inbox.py (đọc thư trả lời)
  intake/     đọc JD dán vào · chấm độ khớp với CV
  companies/  nhà tuyển dụng và liên hệ HR · gộp tên nhà tuyển dụng
  llm/        registry provider · engine theo từng việc · adapter schema · đo chi phí & chất lượng
  analytics/  facet thị trường, mỗi cái kèm nó đã thấy bao nhiêu phần của corpus
  store/      model SQLAlchemy + migration Alembic
  slack/      kênh phụ, tuỳ chọn; là client thuần của REST API
  orchestrator.py   hàng đợi task đứng sau các endpoint trả 202 kèm task id
  backup.py         backup database + CV, đứng sau CLI, timer và trang Backup
web/          dashboard React + Vite + TS + Tailwind
```

## 🤝 Đóng góp

Xem [`CONTRIBUTING.vi.md`](CONTRIBUTING.vi.md) để biết cách cài đặt, những gì CI kiểm tra và các
luật mà mọi thay đổi phải giữ. Bản thân các quy ước nằm ở [`CLAUDE.md`](CLAUDE.md) và ở `CLAUDE.md`
của từng vùng code, cùng với những bug chỉ lộ ra khi chạy trên site thật.

## 📝 Giấy phép

MIT — xem [LICENSE](LICENSE) — cho phần code của riêng JobPilot. Thành phần của bên thứ ba giữ
điều khoản riêng:

- `awesome-cv.cls` và `fontawesome.sty` lấy từ Awesome-CV (LPPL v1.3c); cả hai đã được sửa ở đây.
- Các template trong `jobpilot/cv/templates/awesome_cv/` phái sinh từ template mẫu của Awesome-CV
  (CC BY-SA 4.0).
- Font trong `fonts/` theo Apache 2.0 (Roboto) và SIL OFL 1.1 (Font Awesome); văn bản giấy phép
  nằm ngay cạnh chúng.
- Logo các job board trong `web/public/logos/` là nhãn hiệu của chủ sở hữu tương ứng.

## ⭐ Ghi nhận

- [Awesome-CV](https://github.com/posquit0/Awesome-CV) của Claud D. Park
- [Tectonic](https://tectonic-typesetting.github.io/) — engine LaTeX
- Dữ liệu việc làm từ [We Work Remotely](https://weworkremotely.com/) và
  [Arbeitnow](https://www.arbeitnow.com/) qua feed công khai của họ
