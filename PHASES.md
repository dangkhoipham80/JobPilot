# PHASES.md — nhật ký triển khai JobPilot

Chi tiết từng phase (scope, quyết định, bug chỉ lộ ra khi chạy thật).
Tách khỏi `CLAUDE.md` để file đó dưới ngưỡng context; bài học còn *đang áp dụng*
nằm ở `CLAUDE.md` mục "Nợ kỹ thuật" và "Thêm một site crawl mới".

## Nhật ký phase

- ✅ Khung LaTeX Awesome-CV hoạt động (`awesome-cv.cls` + `fonts/`, build Docker). Nội dung CV nằm trong DB, không trong repo.
- ✅ Docs nền tảng: `PLAN.md`, `SKILL.md`, `CLAUDE.md`.
- ✅ **Phase 0** — scaffold `jobpilot/` + `web/` (placeholder) + `docker-compose` + `pyproject` + `Makefile` + `config.yaml`/`.env.example` + config loader + CLI + smoke tests.
- ✅ **Phase 1** — Python build wrapper (`tailor/build.py` + `cli build`, Docker LaTeX, page-count qua pypdf) + cải thiện Skills của Master CV (ATS, giữ 1 trang) + untrack LaTeX aux cũ.
- ✅ **Phase 2** — Data + API skeleton: SQLAlchemy 2.0 models (`store/models.py`: jobs/applications/edits/runs/cv_versions + `JobStatus` enum) + engine/session (`store/db.py`, sync psycopg3, schema `jobpilot`, SQLite translate-map cho test) + Alembic (initial migration, GIN trên payload) + FastAPI (`api/main.py`: `GET /jobs`, `GET /jobs/{id}`, `GET /stats`, `WS /ws`, token auth, CORS localhost) + `cli serve`. 25 test pass; verify live HTTP+WS trên SQLite; migration render Postgres DDL hợp lệ (Docker chưa chạy nên chưa `alembic upgrade` lên Postgres thật).
- ✅ **Phase 3** — Crawler MVP: `crawler/` framework (`base.BaseScraper` template + pure `search_url`/`parse_search`/`parse_detail`; `fetch.PlaywrightFetcher` lazy import; `ratelimit` jittered delay; `robots` policy; `text`/`normalize` HTML→md + posted_at + level + match_score; `persist` upsert-by-id + cross-source dedup `(company, normalized_title)`; `pipeline.run_crawl` graceful per-site fail + `Run` record; `registry` config→scrapers). ITviec scraper implemented (real selectors); TopCV/VietnamWorks scaffolded to the same interface (disabled in config until real HTML snapshot); `FixtureScraper` for offline e2e. `cli crawl` wired (`--query`, `--no-robots`). No schema change (payload holds §3.1). 52 tests pass; verified live crawl→persist→Run on SQLite via fixture + real CLI path (ITviec fails gracefully w/o Playwright).
- ✅ **Phase 4** — Web Dashboard MVP: React (Vite+TS+Tailwind, shadcn-style hand-rolled UI) "flight deck" dashboard. Backend additions: `POST /jobs/{id}/shortlist|skip` (state transitions + WS `job_updated` broadcast), stats enriched (`fresh`, `by_level`, `by_day`), `/jobs` search (`q`) + `fresh` filter, `JobDetailOut` (skills/description_md/is_fresh from payload), shared `timeutil` (+07 fixed offset). Frontend: Dashboard (KPI cards + signature "approach funnel" + BySource/ByDay charts via validated dataviz palette), Jobs (filter/search + shortlist/skip inline), Job detail (JD + skills + actions), realtime via `useWebSocket` (LIVE indicator + auto-refetch), dark/light theme. 58 py tests pass; `npm run build` clean (tsc+vite); verified live over HTTP (seeded SQLite → serve → curl /stats, /jobs, detail, q+fresh, shortlist transition, 401).
- ✅ **Phase 4.5** — CV Studio (slice lõi): `jobpilot/cv/` — `schema.py` (Pydantic `CvDocument`: theme/header/sections discriminated union paragraph|bullets|education|experience|projects), `latex.py` (inline markup `**bold**`/`` `tech` ``/`~techfe~`/`[label](url)` + escape mọi ký tự LaTeX đặc biệt — content không bao giờ chứa LaTeX thô), `templates/awesome_cv/*.j2` (Jinja2, delimiter `<< >>`/`<% %>`), `render.py` (JSON → `cv.tex` + `resume/*.tex` + `tex_snapshot`), `master_seed.json` (import 1 lần từ `resume/*.tex` — **PDF text identical** với `cv.pdf` gốc), `store.py` (`cv_versions` append-only, auto-seed master, rollback = re-save, `fork_from_master` cho Phase 5), `compile.py` (build dir riêng `out/cv/<scope>/`, không đụng `resume/`). API: `GET/PUT /cv/{scope}`, `POST /cv/{scope}/compile`, `GET /cv/{scope}/pdf`, `GET /cv/{scope}/versions[/{v}]`, `POST /cv/{scope}/rollback/{v}`, `GET /cv/templates` + WS `cv_updated`/`cv_compiled`. CLI `cv seed|render|build|versions`. Web: trang **CV Studio** (editor structured — reorder/toggle section, bullet/entry/tag inputs — + PDF preview compile-on-demand + version history/restore). 115 py tests pass; `npm run build` clean; verified live: auto-seed → edit (đổi position, đưa Skills lên, ẩn Honors) → PUT v2 → Docker compile → PDF phản ánh đúng 3 thay đổi → rollback v1 → PDF **identical** với Master gốc → WS push.
- ✅ **Phase 5** — Tailor engine + CV Review: `jobpilot/tailor/` — `schema.py` (`TailorPlan` **index-based**: agent chỉ được reorder/drop/ẩn theo chỉ số của Master CV; free text duy nhất là `summary` → bịa skill là *shape schema không diễn đạt được*, không phải luật để agent tuân theo), `guard.py` (2 tầng: structural — mọi index phải trỏ vào content có thật; lexical — mọi token "trông như tech" trong summary phải có trong vocabulary của Master CV; trả về violations để engine retry 1 lần), `prompt.py` (system prompt encode SKILL.md §0/§2 + Master CV render thành **indexed outline** = address space của plan; system ổn định/user volatile để cache tốt), `engine.py` (`claude-opus-4-8`, adaptive thinking, structured output qua `messages.parse(output_format=TailorPlan)`, 1 vòng retry khi vi phạm guardrail; `FixtureEngine` cho test), `apply.py` (plan → tailored `CvDocument`, thuần & không mutate Master), `diff.py` (structural diff: rewritten/trimmed/hidden/reordered — không dùng line diff vì tailor chủ yếu *di chuyển* content), `service.py` (state machine SHORTLISTED→TAILORING→REVIEW→APPROVED/SKIPPED, edit loop có cap `edit_max_rounds`, `Run` record, lưu plan+diff vào `cv_versions.meta`). Migration **0002** thêm `cv_versions.meta`. API: `POST /jobs/{id}/tailor|edit|approve|reject`, `GET /jobs/{id}/review|cv` (router `review` phải include **trước** `jobs` vì `GET /{job_id:path}` là greedy) + WS `tailor_done`. CLI `tailor`. Web: trang **CV Review** (PDF tailored | diff + gap report + edit box), CV Studio nhận scope `/cv/:scope`. 186 test pass; verify live qua HTTP với Docker build thật (chỉ giả lệnh gọi Claude): plan→PDF 1 trang phản ánh đúng 4 thay đổi, facts/metrics giữ nguyên, Master CV không đổi, edit round + approve + 409/422 đúng, **guardrail chặn plan bịa "Apache/Terraform" ở tầng HTTP và không ghi CV nào**.
- ✅ **Phase 6** — Apply dispatcher + Applications board: `jobpilot/apply/` — `letter.py` (cover letter SKILL.md §2 bước 4; **tách `paragraphs` (claim, check nghiêm ngặt theo vocabulary Master CV) khỏi `learning_note` (chỗ DUY NHẤT được nhắc skill MISSING, và chỉ những MISSING mà tailor plan đã xác định)** → câu "chưa dùng X, sẵn sàng học" diễn đạt được còn "thạo X" thì không), `email.py` (**3 gate độc lập**: `enabled` → `dry_run` → `test_recipient`; `build_email` thuần không chạm socket, `send_email` là hàm duy nhất nói chuyện với mail server và từ chối khi dry_run; MIME + đính kèm PDF qua stdlib `smtplib`), `portal.py` (handoff package: URL + CV + field để paste, luôn chạy được không cần Playwright; `match_field` so khớp **theo từ** — `prefill_with_browser` chỉ nối vào CLI, không bao giờ tự submit), `dispatcher.py` (email full-auto | portal/external chờ user confirm; **dry run giữ job ở APPROVED** vì không có gì được gửi; mọi nhánh đều ghi `Application` + `Run`). Migration **0003** thêm `applications.meta` + `created_at`. API `POST /jobs/{id}/apply|confirm-submit|report-failure`, `GET /applications[?result=]`, `GET /applications/settings` + WS `apply_done`. CLI `apply` / `confirm-submit`. Web: trang **Applications** (4 cột Prepared/Your turn/Submitted/Failed + banner trạng thái gate) + nút Apply ở CV Review. 232 test pass; verify live: dựng **SMTP server thật tại chỗ** → dry run không gửi & giữ APPROVED → bật gate → gửi thật, message bắt được có đúng recipient test, cover letter làm body, câu gap còn nguyên, và **PDF đính kèm byte-identical với bản tailored**; portal không tự submit; config mặc định (`enabled: false`) chặn gửi ở tầng HTTP.
- ✅ **Phase 7** — Slack (kênh phụ): `jobpilot/slack/` — **Slack là client thuần của REST API, backend không biết gì về Slack** (PLAN.md §10: 1 nguồn sự thật = Postgres, mọi action đi qua API → Web và Slack không thể lệch state). `client.py` (`JobPilotClient` gọi REST; nhận inject `httpx.Client` nên test chạy thẳng vào ASGI app thật), `blocks.py` (Block Kit builders **thuần**, không import SDK; `check_blocks` validate đúng limit Slack — 50 blocks / 3000 char section / 75 char label / 2000 char value; builder truncate thay vì để Slack trả 400), `events.py` (WS event → tin nhắn; **cố tình im lặng** với các transition thường để channel còn dùng được — chỉ post review/apply/failure), `app.py` (Socket Mode; nút = dispatch table `ACTIONS` → method của client; mirror WS chạy thread riêng, tự reconnect; degrade rõ ràng khi thiếu SDK/token). CLI `slack --api --web`. 256 test pass; verify live: client drive toàn bộ funnel qua HTTP thật (shortlist→tailor→approve→apply→confirm-submit), render đúng job/review/apply card (gap "Apache Kafka" hiện rõ, portal card có đủ field để dán), WS thật đẩy 2 event → mirror lọc còn 1 notification. ~~Chưa verify được: gửi thật lên Slack workspace~~ → **đã verify ngày 2026-08-08** trên workspace thật: app `jobpilot` (scope đúng một `chat:write`), Socket Mode + `connections:write`, digest lên channel, và **bấm nút Shortlist trên Slack thật** → `POST /jobs/{id}/shortlist` 200 → Postgres `DISCOVERED`→`SHORTLISTED` → dashboard đọc cùng state → Slack post ngược xác nhận. Khẳng định của `PLAN.md §10` giờ là quan sát được chứ không còn là thiết kế trên giấy.
- ✅ **Phase 8** — Orchestration & polish: `orchestrator.py` — `TaskQueue` in-process (ThreadPoolExecutor **1 worker**: máy chạy Docker + browser cùng lúc thì fan-out chỉ tranh tài nguyên, và serial làm chữ "queued" có nghĩa; mỗi task body tự mở session DB riêng vì session SQLAlchemy không thread-safe). Worker thread đẩy progress về event loop của API qua `run_coroutine_threadsafe` → WS `task_updated`. **Invariant**: `status` được ghi *cuối cùng* (sau `result`/`finished_at`) vì đó là tín hiệu mọi consumer poll; eviction history không bao giờ xoá task chưa chạy xong. `POST /crawl` → 202 + task (chặn crawl thứ 2 khi đang chạy: sẽ đua rate-limit cùng site), `GET /tasks[/{id}]`, `GET /runs`, `GET/PUT /settings`. **Settings ghi vào `config.local.yaml` (gitignored) merge đè lên `config.yaml`** — vì comment trong `config.yaml` là tài liệu (nhất là 3 cổng an toàn email) và YAML round-trip sẽ xoá sạch; patch không validate được thì bị từ chối *trước khi ghi*. CLI `run [--query] [--every N]` (loop đơn giản thay vì thêm dependency scheduler; rc=1 khi mọi site fail để cron thấy được). Web: trang **Runs** (queue realtime + history + nút Crawl) và **Settings** (crawl/sources/apply gates/CV, mỗi card save riêng). 279 test pass; verify live: `POST /crawl` → 202, crawl thứ 2 → 409, WS stream `queued→running(progress)→done` với `finished_at`+`result` đầy đủ, site fail được báo chứ không nuốt, settings round-trip mà `config.yaml` **byte-identical**, patch sai bị từ chối, và crawl thật (không có Playwright) fail có thông báo hành động được + vẫn ghi `Run`.
- ✅ **Phase 9** — TopCV + VietnamWorks chạy thật (hết scaffold): `crawler/jsonld.py` — parser schema.org **`JobPosting`** dùng chung, vì cả 2 site đều nhúng block đó cho Google Jobs và **nó là target ổn định nhất**: có JD đầy đủ, `datePosted` tuyệt đối, và site có động lực giữ nó đúng (index Google phụ thuộc vào đó) mạnh hơn động lực giữ tên class CSS. `crawler/vietnam.py` — nhận diện theo giá trị dùng chung (CITIES, "thoả thuận/thương lượng" → `salary=None`, regex posted, lọc noise "+3"/"Rất đông ứng viên"); `itviec.py` refactor để dùng chung, không còn 3 bản copy danh sách thành phố. **TopCV**: KHÔNG phải Vue SPA — server-rendered, curl là đủ; card `.job-item-search-result` + `data-job-id`. **VietnamWorks**: `__NEXT_DATA__` chỉ chứa dropdown filter, job đến từ XHR → **phải qua Playwright**; đọc DOM (`.new-job-card`) chứ không gọi API nội bộ `ms.vietnamworks.com` (host đó không có robots.txt; trang user-facing thì `robots.txt` cho phép rõ ràng — nguyên tắc 5). 354 test pass; **verify live cả 3 site**: TopCV 4/4 job Java thật (match 0.5–1.0, JD 2.4–3.1k chars), VNW 2/4 insert (2 bị filter đúng luật), ITviec không regress sau refactor.

  **Helper dùng chung nay ở `crawler/text.py`**: `el_text`, `first_match`, `strip_query`, `leaf_texts` — trước đó `_text` bị copy ở 4 file, `_clean_url`/`_first` ở 2 file.

  **8 bug chỉ lộ ra khi chạy thật hoặc khi review, đều đã có test ghim:**
  1. `/tim-viec-lam-it?keyword=java` **im lặng bỏ qua `keyword`** — trả 200 + 50 card của category IT chung (1.655 job: "IT Support", "IT Comtor"), rồi **cả 4/4 bị filter vì match_score = 0**. Search thật là slug trong path: `/tim-viec-lam-java-spring-boot` → 84 job Java. Param bị bỏ qua *tệ hơn* lỗi: crawl báo thành công và lặng lẽ giao sai job.
  2. JSON-LD `identifier` là id của **nhà tuyển dụng**, không phải job (TopCV: 198409 = id trong URL công ty). Dùng làm `native_id` thì mọi job cùng công ty chung 1 row và mỗi lần crawl ghi đè lần trước. `native_id` luôn lấy từ URL.
  3. `select_one("h2 a, a")` chọn theo **thứ tự document**, không theo thứ tự selector — link logo VNW đứng trước `h2 a` nên title lặng lẽ đến từ sai element. Dùng `text.first_match(root, *selectors)`.
  4. TopCV có 3 nhóm tag markup y hệt nhau; lấy hết thì "Team building"/"Bảo hiểm xã hội" thành **skill**, chảy vào `match_score` và gap report của tailor. Chỉ đọc nhóm "Chuyên môn".
  5. `SearchHit.extra` **không tự chảy sang `RawJob`** — `normalize` chỉ spread `raw.extra`. Đặt extra trên hit rồi quên `extra=dict(hit.extra)` trong `parse_detail` là mất sạch (TopCV mất label kinh nghiệm ở mọi job) *mà test cấp-card vẫn xanh*. `linkedin.py` đã làm đúng từ trước.
  6. Match city bằng substring không phân biệt hoa/thường: `"remote" in "remote debugging"` → tag skill thành **location**. Sai dữ liệu *trông như đúng*, tệ hơn thiếu dữ liệu. Giờ city phải **chiếm gần hết** label (bỏ tên city ra chỉ còn filler "TP."/"City"/dấu câu), và mọi phần tách bởi dấu phẩy đều phải là city → giữ "Hà Nội, Hồ Chí Minh", loại "Java, Remote debugging".
  7. Hard-stop khi thấy chữ "competitive/thoả thuận" **ăn mất lương thật** đứng sau nó ("Competitive salary package" rồi mới tới "$2,000 - $3,000"). Chỉ **login wall** mới stop scan (đúng ca ITviec, để không nhặt số từ banner "IT Salary Report"); "negotiable" chỉ là *leaf này không có lương*, tiếp tục quét.
  8. Regex posted bắt buộc có "ago"/"trước" → card render duration trần ("8 hours") bị mất timestamp, job mới trông như không có ngày. Suffix giờ là optional.

  **Crawl 0 job giờ có cảnh báo** (`base.crawl`): selector chết trả `[]` và crawl "thành công" với 0 job — không phân biệt được với query không có kết quả (PLAN §10 "cảnh báo khi 0 job"). Có cả cảnh báo khi `hits < limit` (VNW lazy-load).

- ✅ **Phase 10** — Tailor + apply rời request path, lên `TaskQueue`: `POST /jobs/{id}/tailor|edit|apply` giờ trả **202 + task**, tiến độ về qua WS `task_updated` (web có poll 1.5s làm lưới an toàn khi socket rớt). **Cái KHÔNG hoãn**: mọi thứ chỉ cần đọc DB là từ chối được vẫn là 409/422 **ngay trong request** (`service.check_tailorable` / `dispatcher.check_appliable` — sai status, hết edit round, chưa build CV). Hoãn một lỗi rõ ràng thành "chờ 1 phút rồi mới biết sai" là làm UX tệ đi, không phải làm nó async. Task body mở **session riêng** (session của request không sống lâu hơn request) và tự `queue.publish` các event domain (`job_updated`/`tailor_done`/`apply_done`) vì route đã return trước khi việc chạy — nhờ đó **guardrail fail giờ mới tới được Slack**: đường 422 cũ không broadcast gì cả. Guard **1 task / 1 job** (409) vì 2 vòng tailor sẽ tranh cùng build dir — guard nằm **trong `TaskQueue.submit(exclusive=True)`**, không phải ở route: check và insert phải cùng một lần giữ lock (xem bug 4). `Task.error_kind` (tên class exception) tách khỏi `error` để UI phân biệt `GuardrailViolation` (sự kiện truthfulness — hiện riêng, nói rõ "chưa ghi gì vào CV") với lỗi build/mạng. `progress` đặt tên đúng stage ("planning against the JD" / "building the PDF" / "writing the cover letter") — 2 stage này fail vì lý do hoàn toàn khác nhau. Task result cố tình **nhỏ** (`/tasks` trả 50 cái một lúc); plan/diff vẫn ở `cv_versions` qua `GET /review`. CLI giữ nguyên đồng bộ (terminal thì chờ là đúng). Web: hook `useTask` + component `TaskProgress`. 392 test pass; **verify live trên Postgres thật + Docker LaTeX thật + browser thật** (chỉ giả lệnh gọi Claude): `POST /tailor` **202 trong 34 ms** (trước là block cả vòng build), WS đẩy `queued→running→"planning against the JD"→"building the PDF"→job_updated→tailor_done→done`, PDF thật 1 trang; POST lần 2 khi đang chạy → 409; plan bịa "Golang/Terraform" → task **failed** + `error_kind=GuardrailViolation` + job FAILED + **không ghi thêm cv_version nào**; apply → 202 → `result=awaiting_user` + `job_updated SUBMITTING`; edit round 1→3 rồi round 4 bị chặn 409 ngay trong request; trang CV Review hiện pill TAILORING + card tiến độ chạy thật, không lỗi console.

  **5 bug chỉ lộ ra khi chạy thật / chạy full suite / khi review, đều đã có test ghim:**
  1. **`TestClient` dùng làm context manager chạy lifespan**, mà lifespan exit gọi `queue.shutdown()` → `ThreadPoolExecutor` **không restart được**. Sau test đó, mọi task submit tiếp theo nằm `queued` **vĩnh viễn** — UI thấy "đang chạy" nhưng không có gì chạy, và không có lỗi nào để đọc. Pool giờ **lazy + dựng lại sau shutdown**; task còn `queued` lúc shutdown bị đánh dấu `failed` ("cancelled — the queue shut down") thay vì nói dối là đang chờ.
  2. **SQLite in-memory + `StaticPool` = 1 connection dùng chung**, nên hết mô phỏng được Postgres ngay khi có thread thứ hai: worker đang mở transaction thì request thread `close()` session → **ROLLBACK nuốt luôn việc của worker**. Triệu chứng: apply task báo thành công mà job vẫn APPROVED. Test DB giờ là **file SQLite + WAL** → mỗi session một connection, giống thật. (Cùng họ với bài học "verify crawl phải chạy Postgres thật".)
  3. **`pypdf` là extra `[cv]` chưa cài** → `_pages_from_pdf` fallback regex không đọc nổi PDF của xelatex (object stream nén), builder image cũng không để lại `.log` → `pages = ... or 0`. `0` bị render thành badge đỏ "0 pages" trên một CV 1 trang hoàn toàn bình thường. `pages` giờ là `int | None`, `None` = *không biết* (UI ẩn badge, CLI nói "page count unknown"). "Không biết" và "0" là hai khẳng định khác nhau.
  4. **Guard "1 task / 1 job" đặt ở route là TOCTOU.** Route tailor/apply là `def` thuần → FastAPI chạy chúng trong threadpool, nên 2 request đồng thời cùng đọc `queue.active()` thấy trống rồi cùng `submit`. Verify thật: bắn **8 POST /tailor song song** → trước khi sửa nhiều task lọt, sau khi chuyển guard vào `submit(exclusive=True)` (check + insert + schedule trong **một** lần giữ lock) → đúng **1× 202, 7× 409, 1 task**. Cùng lock đó cũng đóng race `submit` vs `shutdown` (pool bị đóng giữa lúc dựng và lúc dùng → task kẹt `queued` vĩnh viễn → job đó 409 mãi mãi).
  5. **Exception "không lường trước" bỏ job kẹt ở TAILORING/SUBMITTING.** Service commit trạng thái đang-chạy *trước* phần chậm, nhưng chỉ đổi sang FAILED cho các lỗi nó biết (guardrail/build/SMTP). Một `KeyError` là job đứng mãi ở "đang tailor" mà chẳng có gì đang tailor. `_publish_job_status(settle=True)` ở nhánh lỗi giờ hạ trạng thái treo xuống FAILED — task vẫn giữ nguyên văn lỗi thật.

- ✅ **Phase 11** — Phân trang + nguồn tier-2: `base.BaseScraper.search()` đi **nhiều trang** thay vì 1 fetch (`search_url(query, page)`, `crawl.max_pages` mặc định 5). Dừng ở cái đến trước: đủ `limit`, hết `max_pages`, trang rỗng, `search_url` trả URL trùng/`""`, hoặc **trang lặp lại id đã thấy**. Cái cuối là cái gánh: site *nhận* `?page=2` rồi bỏ qua sẽ trả lại trang 1 — không dedup xuyên trang thì crawl gom cùng 10 job 5 lần và báo cáo một "deep sweep" thành công (đúng họ với bug `?keyword=` của TopCV). Hook mới: `needs_detail` (feed đã đủ JD → không fetch detail) và `matches_query` (feed không có search phía server). `fetch.HttpFetcher` (httpx thuần) cho nguồn phục vụ *document* chứ không phải *app* — browser không chỉ chậm mà **làm hỏng JSON**: Chromium bọc response thành `<html><body><pre>…`. `crawler/feed.py` = `FeedScraper` + `parse_rss_items` (stdlib XML: RSS là XML, parser HTML sẽ "sửa" tag hỏng thay vì báo) + `parse_json_feed` (lỗi có kèm 80 byte đầu → nhận ra ngay là trang lỗi HTML hay JSON bị bọc `<pre>`). **2 nguồn tier-2 mới**: `weworkremotely.py` (RSS mỗi category = 1 "trang"; `<title>` là `"Company: Job Title"` → tách ở `": "` **đầu tiên**) và `arbeitnow.py` (JSON, `?page=` phân trang thật). Config: `crawl.max_pages` + 2 dòng source; Settings page có ô "Max pages per site". 428 test pass; **verify live cả 6 nguồn qua API + Postgres 17 thật**: WWR 8 job (JetBrains/Stripe/Reddit/Coinbase, JD 3.5–8.7k chars), Arbeitnow 9 job Java thật, 9 row vào DB với `posted_at` đủ 9/9 và JD đủ 9/9, re-crawl idempotent (updated=9, inserted=0), settings round-trip mà `config.yaml` **byte-identical**.

  **6 bug chỉ lộ ra khi chạy thật (test xanh suốt), đều đã có test ghim:**
  1. **`config.local.yaml` xoá sổ nguồn mới.** `deep_merge` ghi đè list, mà trang Settings ghi **cả danh sách `sources`** như lúc save. Máy nào đã mở Settings một lần là 2 nguồn tier-2 **không tồn tại** — không phải "tắt sẵn" mà *vắng mặt*, nên chính trang Settings cũng không hiện để bật. Giờ `config.yaml` giữ **danh mục**, overlay chỉ mang **tuỳ chọn theo key** (`config.merge_sources`).
  2. **Trang chặn anti-bot parse ra 0 hit → bị đọc là "hết kết quả".** Request thứ 2 tới TopCV trong cùng session trả Cloudflare "Sorry, you have been blocked", và crawl ghi "end of results" rồi đi tiếp — một lời nói dối. `PlaywrightFetcher` giờ **raise theo status code** (như `HttpFetcher` vẫn làm), nên 403 thành "page 2 failed (blocked — anti-bot), keeping 50 hit(s)". Lợi ích thật sự lớn hơn log: trước đây trang 403 vẫn được *parse* thành RawJob rỗng rồi ghi vào DB.
  3. **Trang không có job hợp lệ ≠ hết trang.** Arbeitnow trang 3 có 100 job, 0 cái khớp "Java" — vòng lặp dừng ở đó. Nhưng trang 4 và 5 mỗi trang có 1 job Java thật (JOIN, Doctolib). Tách hai câu hỏi: "site có sang trang không" (so `page_ids` với id đã thấy) khác "mình có muốn gì trên trang này không". Sau khi sửa: 7 → **9 job**.
  4. **TopCV trả 0 kết quả nhưng vẫn đổ 50 card gợi ý vào đúng container `.job-list-search-result`.** Query mặc định "Java Spring Boot Backend" (3 stack đầu) → slug 4 từ → `"Tuyển dụng 0 việc làm"` + 50 job **kế toán/QC/sale**. Không có cách nào phân biệt bằng cấu trúc, nên đọc **số đếm trong `<h1>`**; 0 thì trả `[]` + cảnh báo "try a shorter query". Không có số đếm = *không biết*, vẫn tin card (nếu TopCV đổi chữ thì không tự nhiên crawl 0 job mãi).
  5. **`infer_level` match substring**: "intern" nằm trong "internal"/"international", "lead" trong "leadership" — job senior của Stripe bị ghi **`level=intern`**. Sai dữ liệu *trông như đúng*, chảy thẳng vào chart by_level và bộ lọc. Giờ match theo **từ**; và riêng "intern" trần chỉ tính trong **title** — trong JD nó là từ thường (tiếng Đức "beraten wir uns intern", gặp thật trên Arbeitnow), còn "internship"/"thực tập" thì rõ nghĩa ở đâu cũng được.
  6. **`parse_posted_at` không đọc được ngày của feed.** RSS dùng RFC-822 ("Wed, 22 Jul 2026 07:00:51 +0000"), JSON API dùng unix epoch — cả hai đều rơi về `None`. Nguồn feed mà mất `posted_at` thì **không bao giờ được gắn 🔥 <48h** và biến mất khỏi chart by-day, tức là mất đúng thứ khiến feed đáng dùng. Epoch chỉ nhận 9–11 chữ số: `int()` không chặn sẽ đọc "2026" thành tháng 1/1970 — một câu trả lời sai tự tin, tệ hơn "không biết".

- ✅ **Phase 12** — ATS adapter (tier 3): `crawler/ats.py` — `AtsScraper` (base) + `GreenhouseScraper` + `LeverScraper`. **Một adapter phủ mọi công ty dùng nền tảng đó**, nên thêm công ty = thêm 1 từ trong `ats:` của `config.yaml`, không thêm code. Ý tưởng then chốt: **"trang" ở đây là một công ty** — vòng lặp phân trang Phase 11 hỏi `search_url(query, page)` rồi dừng khi hết URL, tức là "đi lần lượt các board đã khai báo". Không phải sửa gì trong vòng lặp; chỉ override `max_pages` vì `crawl.max_pages` sinh ra để chặn board *vô hạn*, còn danh sách công ty đã hữu hạn sẵn. `robots` kiểm bằng chính `RobotsPolicy` (không đọc bằng mắt): Greenhouse chỉ cấm `/embed/`, Lever `Allow: /` + `Crawl-delay: 1` (rate limiter 2–5s đã vượt). **Ashby cố tình không làm**: `api.ashbyhq.com` không phục vụ robots.txt (401) trong khi `jobs.ashbyhq.com` cấm `/api/` — đúng hình dạng của host XHR nội bộ VietnamWorks mà dự án đã từ chối gọi. 444 test pass; **verify live qua API + Postgres**: bật 2 nguồn qua trang Settings (patch chỉ nêu 2 key vẫn giữ đủ 9 source — merge-by-key của Phase 11 làm việc thật), crawl → 7 job vào DB, `posted_at` đủ 7/7, JD 2.6–7.8k chars, `apply_channel=external` 7/7, và Lever `duplicates=4` là các bản đăng lại nhiều thành phố bị gộp đúng theo `(company, normalized_title)`.

  **3 điều chỉ thấy khi đọc output thật:**
  1. **Greenhouse double-encode `content`** — JD về dạng `&lt;div&gt;…`. Lưu thẳng thì người đọc thấy tag thô còn agent tailor nhận markup như văn xuôi. Unescape đúng **một** lần: `&amp;` còn lại là cách mã hoá đúng của ký tự `&` *bên trong* HTML đã khôi phục.
  2. **Lever `createdAt` là mili-giây** (13 chữ số) và **payload không bao giờ ghi tên công ty**. Đổi ms→giây ngay tại scraper thay vì nới guard epoch (guard nhận 9–11 chữ số chính là để một con số 13 chữ số bất kỳ *không* bị hiểu thành ngày); tên công ty lấy từ slug trong `hostedUrl`. Ngoài ra JD của Lever nằm rải ở `description` + `lists` + `additional` — chỉ lấy `description` là đưa cho tailor bài PR của công ty mà không có yêu cầu nào để CV đáp (cùng bài học JSON-LD của VNW).
  3. **Any-word matching quá rộng trên board lớn**: query "backend engineer java" khớp 44/184 job GitLab, và 6 cái `limit` giữ lại là "AI Engineer" + 4 "Customer Success Engineer" — tất cả nhờ mỗi chữ *engineer*. Lọc chặt hơn sẽ vứt nhầm job tốt, nên **xếp hạng** thay vì lọc: `BaseScraper.rank_hits` (mặc định giữ nguyên — nguồn có search đã tự xếp hạng) và `FeedScraper` sắp theo số từ khoá khớp giảm dần. Sau khi sửa, 6/6 đều là Backend Engineer thật.

- ✅ **Phase 13** — ATS đọc được PDF không: `cv/ats.py` — build trả lời *"compile được chưa"*, file này trả lời *"máy đọc được không"*, và cái thứ hai mới quyết định có ai đọc CV hay không. Trích text layer rồi đối chiếu **những gì CV nói** với **những gì parser lấy lại được**: tên, email, điện thoại (so theo chữ số vì extraction làm xô lệch dấu cách), heading section, ligature (`ﬁ` phá keyword search), và độ phủ keyword của job. **Không có điểm số** — "ATS score 72/100" chẳng cho biết phải sửa gì, còn "email của bạn không nằm trong text layer" thì có. Keyword thiếu **không bao giờ chặn Approve**: chặn ở đó là mời người dùng dán skill không có vào CV, đúng thứ guardrail tailor sinh ra để ngăn. Surface ở `POST /cv/{scope}/compile` (`ats`) + panel ở CV Studio. 464 test pass; verify live bằng build Docker thật + kiểm chứng ngược (đổi email/tên trong doc → 2 error, message nêu đúng địa chỉ mà ATS sẽ gửi tới thay thế).

  **Bug đáng giá nhất của phase này là bug của chính checker.** Lần chạy thật đầu tiên, `pypdf` đọc một PDF Awesome-CV **hoàn toàn tốt** thành `FRESHERSOFTWAREENGINEER` và `WorkExperience` — mất sạch dấu cách — nên checker kết luận CV hỏng, thiếu heading. Đọc lại đúng file đó bằng **pdfminer.six**: "FRESHER SOFTWARE ENGINEER", "Work Experience", "Honors & Awards" — chuẩn từng khoảng trắng. **PDF chưa bao giờ hỏng; công cụ đo mới hỏng.** Báo hạn chế của công cụ thành lỗi của tài liệu còn tệ hơn không kiểm tra: nó đẩy người ta đi sửa một template vốn đã đúng. Nên: ưu tiên `pdfminer.six` (đã thêm vào extra `[cv]`), `pypdf` chỉ là fallback và **tự khai báo `spacing_reliable=False`** — khi đó mọi phép so khớp bỏ hết khoảng trắng ở cả hai vế, để một engine yếu không thể bịa ra finding. Cùng họ với bài học "`pages=0` vs `pages=None`": *không biết* và *hỏng* là hai khẳng định khác nhau.

- ✅ **Phase 14** — Vì sao điểm đó, và tin đó còn sống không: `crawler/quality.py` (thuần, **không LLM**). (1) `stack_coverage` gọi tên hai vế của `match_score` — job 0.25 và job 0.75 trước đây là bản án không kèm lý do, trong khi lý do vốn đã nằm sẵn trong danh sách `stacks` bạn tự khai. Dùng **đúng luật** của `stack_match_score`, không phát minh luật hay hơn: nếu lời giải thích bất đồng với con số nó giải thích thì nó thành một điểm số thứ hai đang cạnh tranh. (2) `flags_for` đánh dấu tin đáng xem lại: `no_jd`, `thin_jd` (<400 ký tự), `stale` (> `crawl.stale_days`, mặc định 45), `undated`. **Không cờ nào lọc bỏ job** — chỉ chú thích rồi để người quyết, giống cách crawler phơi gap ra chứ không tự lấp. `undated` tách khỏi `stale` vì *không biết tuổi* khác *già* (cùng họ `pages=None` vs `pages=0`). Web: tooltip trên MatchMeter liệt kê stack khớp/không khớp + badge cảnh báo ở trang Jobs và Job detail. 479 test pass; verify live trên Postgres thật: 7 job vừa crawl có đủ giải thích, và `cli backfill` gắn tín hiệu cho **66 row cũ** (chạy lần 2 → 0, idempotent) cho ra histogram thật **42 `no_jd` (toàn bộ LinkedIn alert), 10 `undated` (ITviec), 4 `stale` (Palantir reqs 2024–2025)** — tức 42/73 job trong DB không thể tailor nếu chưa dán JD, giờ nhìn phát biết thay vì tới lúc tailor mới lộ.

  **2 bẫy khi verify:**
  1. **`pkill` không giết được uvicorn trên Windows** → server cũ vẫn giữ cổng 8000, `curl` nói chuyện với **code cũ**, và crawl "thành công" mà không ghi quality nào. Suýt kết luận sai là tính năng hỏng. Giết theo cổng (`netstat -ano` → `taskkill //F //PID`) và kiểm `Application startup complete` trong log trước khi tin kết quả.
  2. **FastAPI serialize thẳng ORM row qua `from_attributes`**, nên override `model_validate` trên schema là **code chết** — không bao giờ được gọi. Chỗ đúng để lộ field dẫn xuất là `@property` trên chính model (`Job.quality`): một nơi duy nhất, cả route list lẫn detail đều nhận được.

- ✅ **Phase 15** — Nhắc follow-up sau khi nộp: `apply/followup.py` + migration **0005** (`applications.next_followup_at`, `followup_stage`, index trên cột due). Pipeline trước đây kết thúc ở "submitted" rồi im lặng — mà đơn thường **không bị từ chối, chỉ bị quên**, vì nhớ follow-up là việc đúng ra công cụ này phải gánh. Nhịp hữu hạn: `first_nudge` (5 **ngày làm việc**) → `second_nudge` (+7) → `done` (hai lá thư không hồi âm đã là câu trả lời). Hai quyết định đáng bảo vệ: (1) **không tự gửi gì cả** — đến hạn thì hiện nhắc trên board, vì follow-up là thư gửi cho người đang cân nhắc mình, và thư rời máy mà mình chưa nhìn thấy đúng là thứ nguyên tắc 2 cấm; (2) **dry run không nợ ai cái gì** — không có gì rời máy thì không có ai để nhắc, và `NULL` nói điều đó thật thà hơn một cái hạn đã trôi qua. Dùng ngày làm việc chứ không phải ngày lịch: nhắc rơi vào Chủ nhật là nhắc bị đọc vào sáng Thứ hai với tâm trạng tệ hơn. API `GET /applications/followups`, `POST /applications/{id}/followed-up|stop-followups`. Web: card "N application worth chasing" trên trang Applications với 2 nút *I followed up* / *Let it go*. 491 test pass; `alembic upgrade head` sạch lên **Postgres 17 thật**, và verify live trọn nhịp qua API: due → `second_nudge` (rớt khỏi danh sách due) → `done` (hết hạn) → id lạ trả 404.

  **Bẫy gặp phải:** `is_due` so `next_followup_at` với `vn_now()` → **SQLite trả datetime naive còn Postgres trả aware**, nên so thẳng thì *nổ ở backend này và chạy ngon ở backend kia*. Ép cả hai vế về offset +07 cố định trước khi so — cùng họ với bài học "verify phải chạy Postgres thật, không chỉ SQLite".


- ✅ **Phase 16** — Diff giữa 2 version CV bất kỳ: `GET /cv/{scope}/diff?base=&target=` + card compare trong History của CV Studio. Đây là món nợ cuối của Phase 4.5 (`PLAN.md §9`), và nó rẻ đúng như đã hẹn — **không viết diff mới**: `tailor/diff.py:diff_documents()` vốn đã đi theo cấu trúc (reordered / hidden / trimmed / rewritten) thay vì so từng dòng, và `cv_versions` đã append-only từ đầu nên hai đầu so sánh luôn có sẵn. Frontend tái dùng luôn `review/DiffPanel.tsx` (thêm prop `title`/`action`, `changes` thành optional) — panel này sinh ra để trả lời đúng câu hỏi "cái gì đổi", không lý do gì vẽ lại lần hai.

  **Quyết định đáng bảo vệ — cùng một máy so, hai bộ từ vựng.** `diff_documents` trước đây nhúng cứng lời văn của tailor: section tắt đi được chú thích *"hidden from this CV to keep it to one page"*, summary đổi thì *"summary rewritten for this role"*. Đưa nguyên văn đó cho một so sánh v3 → v7 là **giải thích một sửa tay của người dùng thành một quyết định mà agent đã cân nhắc cho một job** — câu chú thích tự tin nhưng bịa, đúng họ với "sai dữ liệu *trông như đúng*" mà repo đã trả giá nhiều lần. Nên tách `DiffLabels`: `TAILOR_LABELS` (Master → tailored) và `VERSION_LABELS` ("section turned off", "summary rewritten"). **Chỉ lời văn được tham số hoá**, phần nhận diện cấu trúc dùng chung một hàm — hai bộ luật song song sẽ lệch nhau lúc nào không biết. Có test ghim rằng diff version **không** chứa "this role" / "one page".

  **`base`/`target` trong response là do server phát biểu lại**, không phải echo mù: UI đặt tiêu đề panel từ đó, nên nếu backend hiểu khác thứ frontend tưởng mình hỏi thì cái sai lộ ra ở tiêu đề chứ không âm thầm gán nhãn nhầm cho một diff đúng.

  **Bug bắt được trước khi ship: `CvDiff.changed` là `@property` thuần nên pydantic *không* serialize nó.** UI định dùng `diff.changed` để in "hai bản giống hệt nhau" — mà field đó sẽ luôn `undefined` ⇒ điều kiện luôn falsy ⇒ dòng đó không bao giờ hiện, im lặng, không lỗi console, test Python vẫn xanh vì phía Python `changed` chạy tốt. Chữa bằng `@computed_field` (một định nghĩa duy nhất, phía server) thay vì chép lại `order_changed || sections.some(...)` sang TS — hai bản sao của cùng một câu hỏi là mầm lệch pha. Type `CvDiff` bên TS ghi rõ field này do server tính.

  511 test pass; verify live qua **API + Postgres 17 thật** rồi lái trên trình duyệt thật (Playwright, không chỉ test): tạo một sửa thật (đổi summary, tắt Honors, đẩy Skills lên đầu) → `v2 → v3` trả đúng `rewritten` + `hidden` + `order_changed`, chiều ngược `v3 → v2` trả `"section turned on"`, `base==target` cho `changed=false`, version/scope lạ trả 404, `base=abc` trả 422. Trên UI: card compare hiện đúng, mặc định là hai version mới nhất, bấm Compare gọi đúng `?base=1&target=3`, panel hiện before/after gạch ngang + dải section order, **0 chỗ rò lời văn của tailor**, không lỗi console.

  **Hai bẫy khi verify (đều là bẫy môi trường, không phải code):**
  1. **API đang chạy sẵn ở :8000 là *code cũ*** — `openapi.json` không có route mới. Suýt kết luận "UI không gọi được API". Cùng họ với bẫy `pkill` của Phase 14: **hỏi server đang chạy xem nó có route đó không** (`/openapi.json`) trước khi tin bất cứ kết quả nào từ nó.
  2. **CORS chỉ mở cho `:5173`** (`api/main.py:ALLOWED_ORIGINS`), nên dev server dựng tạm ở cổng khác nhận "Failed to fetch" — trông hệt như lỗi ứng dụng. Đúng cách là chạy trình duyệt test với `--disable-web-security`, **không** nới `ALLOWED_ORIGINS` trong code chỉ để test chạy qua: cổng dev không phải thứ nên nở ra vì một lần verify.

  **Lưu ý dữ liệu:** verify chạy trên Master CV thật nên có thêm `v3` (bản sửa thử) và `v4` (rollback về nội dung `v2`) trong lịch sử. Nội dung hiện tại đã khôi phục **nguyên vẹn** — chính endpoint mới xác nhận điều đó (`v2` vs `v4` → `changed=false`). `cv_versions` là append-only nên hai row đó ở lại; đó là thiết kế, không phải rác.

- ✅ **Phase 17** — Cover letter thành *tài liệu*, không chỉ body email: template riêng `cv/templates/awesome_cv/cover_letter.tex.j2` + `apply/letter_pdf.py` + migration **0006** (`applications.cover_letter_pdf_path`). SKILL.md §2 bước 4 mô tả một `cover_letter.tex` từ đầu, nhưng tới giờ letter chỉ tồn tại dưới dạng text làm body email.

  **Điều đầu tiên phát hiện: `\cvletter` không tồn tại.** SKILL.md bảo "dùng class Awesome-CV `\cvletter` hoặc template riêng", nhưng `awesome-cv.cls` trong repo là **bản trim** — `grep -ci letter` trả về **0**. Không có `\recipient`, `\letteropening`, `\letterclosing`, không có env `cvletter`. Upstream Awesome-CV có đủ; bản vendor ở đây thì không. Nên đi đường "template riêng", dựng bằng đúng những macro class thật sự định nghĩa (`\makecvheader`, `\cvsection`, `cvparagraph`, `\makecvfooter`). Bài học: **đừng tin spec mô tả một macro tồn tại — grep class file trước.**

  **Preamble tách ra dùng chung** (`_preamble.tex.j2`): CV và letter cùng `\documentclass`, cùng `\definecolor{awesome}`, cùng khối `\name/\email/\github`. Nếu copy-paste thì đổi `theme.color` trong CV Studio sẽ đổi màu CV mà letter vẫn màu cũ — hai tài liệu gửi cùng một phong bì lại không khớp nhau. Refactor này được verify là **byte-identical**: render `cv.tex` trước/sau, diff chỉ có đúng mấy dòng comment mới thêm.

  **Bug LaTeX chỉ lộ ra khi đọc PDF thật.** Bản dựng đầu tiên compile sạch, 1 trang, không warning — và in ra `Ha Noi Dear Hiring Team at ACME`. Nguyên nhân: Jinja `trim_blocks=True` **ăn newline sau mỗi `%>`**, nên dòng trống mình đặt cạnh một tag để ngăn đoạn bị nuốt mất; `\vspace` rơi *vào trong* đoạn thay vì nằm giữa hai đoạn. Trong LaTeX dòng trống là thứ **có tải trọng**, mà nó lại vô hình khi review diff. Giờ mọi ngắt đoạn viết bằng `\par` tường minh, không phụ thuộc dòng trống. Test ghim đúng cặp đã hỏng. **Compile thành công không chứng minh layout đúng** — cùng họ với "test xanh không chứng minh parser đúng".

  **`build_cv(entry=...)` trước đây là một lời nói dối.** Image `csmith/awesome-cv-builder` có CMD **hardcode** `xelatex … cv.tex; mv $DIR/cv.pdf .`, mà `build_cv` không hề truyền `entry` cho docker — nó chỉ dùng `entry` để *kiểm tra file tồn tại* và *đoán tên PDF đầu ra*. Gọi `entry="cover_letter.tex"` sẽ build lại CV rồi fail vì không thấy `cover_letter.pdf`. Giờ tự viết command ra, `entry` mới có nghĩa.

  **Và một bug có sẵn phát hiện khi sửa chỗ đó**: command của image là `xelatex …; mv …; rm -rf …` **không có `set -e`**, nên LaTeX lỗi thì container **vẫn exit 0** (mã thoát do `rm` cuối quyết định) — dấu hiệu duy nhất của thất bại là *thiếu PDF*. Mà nếu build trước đó đã để lại `cv.pdf`, file cũ sẽ "trả lời thay": `build_cv` báo **thành công** và đưa về **nội dung cũ**. Đúng dạng "báo cáo thành công" mà repo sợ nhất. Sửa bằng cách xoá PDF đích trước khi chạy. Càng đáng sửa vì từ phase này letter và CV **chung một build dir**.

  **Test suite suýt mất tính hermetic.** Sau khi nối vào dispatcher, `pytest` **thật sự khởi động Docker** và ghi PDF vào `out/cv/itviec_1/` — vì `letter_pdf` tự suy ra build dir bằng `cv.compile.build_dir`, trong khi test chỉ patch `dispatcher.build_dir`. Hai ý kiến về cùng một đường dẫn, và ý kiến sai thắng. Sửa ở thiết kế: **caller truyền `dest` vào**, `letter_pdf` không tự đoán nữa. Cộng thêm stub `compile_letter` trong fixture, suite về lại 29s và không cần Docker.

  **Hai cột thay vì một**: `cover_letter_path` (text) và `cover_letter_pdf_path` (PDF) tách nhau vì chúng **hỏng tách nhau** — text có mà PDF không có (Docker tắt, LaTeX lỗi) là *đơn bị giảm chất lượng*, không phải *đơn thất bại*. Gộp một cột thì "build hỏng" trông y hệt "không có letter nào". Lý do cụ thể nằm ở `meta.letter.pdf_error`, và board hiện nó ra như một ghi chú xám chứ không phải lỗi đỏ. Cùng họ `pages=None` vs `pages=0`.

  **Đơn vẫn gửi khi PDF hỏng** — CV đã build xong rồi, giữ đơn lại vì cái đính kèm phụ không dựng được là phạt nhầm người. Email đính kèm letter PDF **chỉ khi nó thật sự build**, không bao giờ đính file cũ hoặc file hỏng.

  531 test pass. Verify thật: `alembic upgrade head` → **0006** lên Postgres 17 (và `downgrade 0005` → `upgrade` round-trip sạch); build PDF thật qua Docker LaTeX rồi **đọc lại text layer** bằng pdfminer để chắc `&`, `%`, `_`, `#` sống sót đúng; chạy trọn `apply_job` trên **Postgres + Master CV thật** → `awaiting_user`, cả 2 đường dẫn ghi đúng row, `pdf_error=None`. Dữ liệu verify (job `itviec:phase17-verify` + build dir) đã xoá sạch sau khi xong.

- ✅ **Phase 18** — Outcome tracking: cái gì xảy ra **sau** khi nộp. `apply/outcome.py` + migration **0007** (`applications.outcome_stage` + bảng `application_events`). Đây là mở màn của roadmap mở rộng `PLAN.md §9.1`, dựng sau khi khảo sát [ai-job-search](https://github.com/MadsLorentzen/ai-job-search), [career-ops](https://github.com/santifer/career-ops), [jobsync](https://github.com/Gsync/jobsync) — cả ba đều có phần này, còn JobPilot thì pipeline **kết thúc ở `SUBMITTED`**: nộp xong là mù, không biết nguồn nào thực sự ra phỏng vấn, và mọi câu hỏi "cách tìm việc này có hiệu quả không" đều không có dữ liệu để dựa vào.

  **Quyết định 1 — `JobStatus` không thêm giá trị nào.** `job_status` là Postgres enum: thêm value phải `ALTER TYPE … ADD VALUE`, **không chạy được trong transaction block**, và kéo theo `web/src/lib/statuses.ts`, funnel, `StatsOut.by_status`, `slack/events.py:_QUIET_STATUSES`. Về mô hình cũng sai: `JobStatus` là vòng đời *trước khi nộp* của một **job**, outcome là chuyện xảy ra với một **đơn**. Một job `SUBMITTED` vẫn `SUBMITTED` dù sau đó offer hay bị từ chối. Có test ghim `"REJECTED" not in by_status`.

  **Quyết định 2 — vừa cột denormalized vừa bảng event append-only.** `GET /applications` trả tới 200 row và đã join `Job`; bắt mỗi row subquery lịch sử thì 1 JOIN thành 200 correlated subquery. Nên `Application.outcome_stage` phục vụ board với chi phí 0, còn `application_events` là nhật ký không xoá. Đúng pattern `cv_versions` đã dùng.

  **Quyết định 3 — đếm thống kê từ *event*, không từ `outcome_stage`. Đây là chỗ dễ sai một cách im lặng nhất của cả phase.** Một đơn đã phỏng vấn 2 vòng *rồi mới* bị từ chối chỉ hiện ra là `rejected`; đếm interview theo cột đó thì interview rate báo cáo số đơn đang **kẹt** ở vòng phỏng vấn chứ không phải số đơn **đạt tới** vòng phỏng vấn — một con số **tụt xuống khi việc tìm việc đang tiến triển tốt**. Nên `/stats` trả hai bộ: `current` (đếm theo `outcome_stage`, để render) và `reached` (`COUNT(DISTINCT application_id)` trên event chưa retract, để tính tỉ lệ). Có test ở cả tầng unit lẫn HTTP ghim đúng ca này. Thêm một điều chỉnh nhỏ cùng tinh thần: **lời mời phỏng vấn *là* một hồi âm** — không ai gõ "họ trả lời" rồi gõ tiếp "họ mời phỏng vấn" cho cùng một email, nên nếu không gộp thì việc được mời phỏng vấn sẽ **làm tụt** reply rate.

  **`event_type` là `String(32)`, không phải Postgres enum** — tập giá trị sẽ còn nở ra (Phase 19 mang thêm phân loại thư từ inbox), và mỗi value mới sẽ tốn một migration `ALTER TYPE` vụng về. Hợp lệ được ép ở tầng Pydantic (`Literal`), nơi giá trị sai là 422 chứ không phải 500.

  **`occurred_at` tách khỏi `recorded_at`**: time-to-reply (Phase 20) đo từ lúc nhà tuyển dụng *thật sự* trả lời, không phải lúc mình kịp gõ vào — và Phase 19 thì gõ vào muộn vài ngày theo đúng định nghĩa.

  **Ghi outcome = dừng follow-up**, luôn luôn. Cadence sinh ra để đuổi theo sự im lặng; biết được bất cứ điều gì — kể cả một lời từ chối — thì không còn gì để đuổi, và một nhắc nhở đi thúc công ty vừa nói "không" là kiểu prompt làm người ta thôi tin công cụ. **`dry_run`/`failed` bị từ chối bằng 409**: không có gì rời khỏi máy thì không có ai để trả lời, và một outcome bịa ra ở đó làm hỏng đúng cái mẫu số mà dashboard sẽ chia. **`ghosted` do user tự gọi tên**, không suy ra từ bộ đếm ngày — một sự im lặng mình chưa buông không giống một lời từ chối, và chỉ mình biết mình đang ở tình huống nào (cùng lý do follow-up không tự gửi).

  **Bấm nhầm thì *retract*, không xoá**: row ở lại (gạch ngang trên card), `outcome_stage` lùi về event còn sống mới nhất — xếp theo `id` chứ không theo `occurred_at`, vì một chỉnh sửa ghi lùi ngày không nên thắng thứ mình vừa ghi sau đó.

  573 test pass. Verify thật: `alembic upgrade head` → **0007** lên **Postgres 17** (round-trip `downgrade -1` → `upgrade` sạch, kiểm tận `information_schema`), lái trọn bộ endpoint trên API thật, rồi lái **UI thật bằng Playwright** trên board + dashboard. Dữ liệu verify đã xoá sạch khỏi DB thật.

  **Ba thứ chỉ lộ ra khi chạy thật:**
  1. **Guard chống double-click bằng React *state* là vô dụng.** Hai click trong cùng một tick đều đọc `busy === false` vì React chưa kịp re-render giữa hai lần — nên click thứ hai lọt và ghi một event trùng. Phải là `useRef`. Không ảnh hưởng tỉ lệ (chúng đếm *đơn*, không đếm *event*), nhưng một dòng trùng trong cái lịch sử mà toàn bộ giá trị của nó là *đọc được* thì có.
  2. **Ô KPI "Success 100% · 2/2 landed" có sẵn bỗng thành lời nói dối** khi hàng outcome thật nằm ngay dưới nó: nó chỉ đo *dispatch có trót lọt không*, mà lại ngồi trên một đơn vừa bị từ chối. Đổi thành **"Sent OK · left the machine"**. Chữ có sẵn từ trước, nhưng chính thay đổi này làm nó đọc thành sai.
  3. **SQLite đánh rơi offset khi đọc lại `DateTime(timezone=True)`** — cùng họ bẫy `followup._aware` của Phase 15. Test không nới lỏng mà ghim đúng điều phải đúng trên **cả hai** backend: 09:00 gõ vào vẫn là 09:00 đọc ra, không thành 09:00 UTC = 16:00 local.

  **Review gate bắt được 2 lỗi mà 573 test xanh không thấy** (`phase-reviewer` trên diff thật):
  1. **`answered = max(reached[replied], reached[interview], …)` — sai số học.** Các bucket đó đếm **theo loại event**, nên một đơn được trả lời qua email và một đơn khác được gọi điện thẳng mời phỏng vấn cho ra `{replied: 1, interview: 1}`, mà `max` đọc thành **1 đơn có hồi âm** trong khi thật ra là **2** → dashboard báo *reply rate 50%* cho một đợt tìm việc mà **ai cũng đã trả lời**. Lỗi trốn được vì mọi test khác đều dùng **một** đơn duy nhất, nơi `max` tình cờ đúng. Phải là `COUNT(DISTINCT application_id)` riêng trên tập `ANSWERED_BY = {replied, interview, offer, rejected}` (`withdrawn`/`ghosted` không nằm trong đó: **mình** quyết, không phải họ). Đúng họ "báo cáo thành công nhưng sai" mà repo sợ nhất — và là lý do một `max()` trông vô hại đáng bị nhìn kỹ.
  2. **Retract hết outcome thì follow-up kẹt `done` vĩnh viễn.** `record_outcome` đặt `followup_stage=DONE`; `retract_outcome_event` chỉ lùi `outcome_stage`. Bấm nhầm rồi rút lại ⇒ board hỏi "what happened?" nhưng nhắc nhở **tắt luôn**, không route nào bật lại được — mất nhắc cho một đơn **chưa từng được trả lời**. Sửa tận gốc thay vì thêm nút: mỗi event tự nhớ `prev_followup_stage`/`prev_followup_at` (migration 0007 chưa lên `main` nên thêm cột không tốn gì), retract hết thì khôi phục lại đúng chỗ đó.

     **Neo vào đâu là câu hỏi khó hơn nó trông.** Bản đầu neo vào *event đầu tiên* — sai: rút một lần bấm nhầm → nhắc quay lại → **bạn nhắc thật** (`second_nudge`) → ghi một outcome thật → rút nốt ⇒ cadence bị kéo về `first_nudge`, tức bảo bạn đi nhắc lại công ty **bạn đã nhắc rồi**, và tặng thêm một nhịp thứ ba cho một cadence cố tình chỉ có hai. Neo đúng là **event gần nhất thật sự bắt gặp cadence còn sống** (`prev_followup_stage IS DISTINCT FROM 'done'`) — không phải event đầu, cũng không phải event cuối. Dùng `is_distinct_from` chứ không `!= 'done'`: `prev_` có thể `NULL`, mà `NULL != 'done'` trong SQL là `NULL` ⇒ hàng đó bị loại **im lặng**. Ba test ghim: event không tắt gì thì bị bỏ qua, nhắc thật thì sống sót, và rút không theo thứ tự vẫn đúng.

  Cộng một nit: `ApplicationEventOut.occurred_at`/`recorded_at` khai `| None` trong khi cột là `NOT NULL` — mô tả sai contract cho phía tiêu thụ. 581 test pass sau khi sửa; verify lại cả ba trên **Postgres + API thật** (`answered` 1 → **2**, `reply_rate` 0.5 → **1.0**; retract hết ⇒ đơn quay lại danh sách follow-up due; và kịch bản nhắc-thật-rồi-rút giữ đúng `second_nudge`).

- ✅ **Phase 19** — Inbox sync: đọc thư nhà tuyển dụng và **đề xuất** outcome. `apply/inbox.py` + migration **0008** (`inbox_suggestions`) + `crawler/mailbox.py` đọc được thư không biết trước người gửi. Phase 18 cho đơn mang outcome; ghi tay được chừng hai tuần rồi thôi, và con số thành bản ghi về độ chăm chỉ gõ phím chứ không còn về đợt tìm việc. Câu trả lời nằm sẵn trong hộp thư.

  **Thứ tự xử lý CHÍNH LÀ thiết kế riêng tư, không phải tối ưu.** Fetch → ghép **cục bộ bằng Python thuần** → thứ gì không thuộc về đơn nào thì **dừng ngay tại đó** → chỉ phần còn lại mới tới Claude. Thư ngân hàng, thư riêng, newsletter không bao giờ rời khỏi máy. Có test ghim đúng tính chất này (`test_unmatched_mail_is_never_handed_to_the_classifier` assert `engine.seen == ["1"]`), nên nếu ai đảo thứ tự thì test đỏ.

  **Bốn mức tin cậy, hiển thị ra UI chứ không giấu**: `thread` (thư trích đúng `Message-ID` mình gửi — chắc chắn), `address` (đúng địa chỉ đã nộp), `domain` (đồng nghiệp cùng domain trả lời — ca thường gặp nhất), `company` (domain *trông giống* tên công ty — yếu nhất, và là thứ **duy nhất** dùng được cho đơn portal/LinkedIn vì mình chưa từng gửi mail nào để họ reply). Card nói thẳng "guessed from the sender's domain" thay vì để người dùng tự đoán.

  **Để `thread` tồn tại được thì phải tự đóng dấu `Message-ID`** trong `OutgoingEmail.as_message()` và ghi vào `meta.email.message_id` — trước đây để mặc SMTP server sinh, tức là một giá trị mình **không bao giờ nhìn thấy**, nên không thể so. Đóng dấu cả khi dry run, để row nói rõ "không có thread nào để ghép" thay vì để người đọc tự hỏi.

  **Bảng riêng, không nhét vào `application_events`.** Đề xuất không phải là chuyện đã xảy ra. Nếu gắn cờ trong event log thì mọi phép đếm ở `outcome_counts` phải nhớ loại nó ra — mà phase ngay trước đã ship đúng một bug kiểu "một aggregate quên mất một phân biệt".

  **Guardrail: `quote` phải có thật trong thư.** Card hiện nguyên câu để bạn bác được cái nhãn chỉ bằng cách đọc một dòng; một classifier diễn giải lại sẽ khiến phép kiểm tra đó bất khả thi mà vẫn *trông như* bằng chứng. Kèm phòng thủ prompt injection: JD/mail là **dữ liệu, không phải chỉ thị**.

  **Chỉ đề xuất 4 loại** (`replied`/`interview`/`offer`/`rejected`). Nhà tuyển dụng không thể *rút đơn* hộ bạn, và không ai gửi mail báo rằng họ đang ghost bạn — hai cái đó vẫn thuộc quyền bạn tự khai. Thư "chúng tôi đã nhận hồ sơ" là `auto_ack`, **không phải** `replied`: máy trả lời không phải người trả lời.

  612 test pass. Verify thật: `0008` lên **Postgres 17** (round-trip downgrade/upgrade, soi `information_schema` + unique constraint), đọc **hộp thư Gmail thật** qua đường `senders=()` mới (15 thư: 15 có `Message-ID`, 14 có text part), chạy trọn `sync_inbox` trên **Postgres thật + mail thật**, rồi lái UI thật bằng Playwright (accept → outcome + follow-up biến mất; dismiss → không hiện lại). Dữ liệu verify đã xoá sạch.

  **Ba thứ chỉ lộ ra khi chạy thật:**
  1. **Verdict bị loại vì quote không có thật thì không lưu lại gì cả** ⇒ lần sync sau thư đó lại "mới", lại gọi Claude, **trả tiền vô hạn** cho một câu trả lời không bao giờ được hiển thị. Chạy sync hai lần trên hộp thư thật mới thấy: `pass 2` vẫn `classified: 1`. Giờ lưu status `unusable` (không bao giờ đề xuất, nhưng đã biết rồi). Test xanh không thấy vì test chỉ chạy sync **một** lần.
  2. **Danh sách từ nhiễu tên công ty là ASCII, tên công ty Việt Nam thì có dấu** — "Công ty TNHH Beta" giữ lại `công` như thể đó là phần đặc trưng của tên. Mà domain thì **không bao giờ** có dấu, nên phải fold về ASCII trước khi so. Test bắt được ngay lần chạy đầu.
  3. **Card Applications vỡ cả board khi `meta` thiếu một key** (`email.attachments.length` trên `undefined` → React unmount toàn bộ). `meta` là JSONB do bất kỳ phiên bản dispatcher nào ghi; một row thiếu key không được phép làm trắng cả trang. Guard bằng optional chaining, và panel email chỉ vẽ khi thật sự có địa chỉ — trước đó nó hiện một mũi tên "→" rỗng trông như hỏng.

  **Review gate bắt thêm 3 lỗi** (`phase-reviewer`):
  1. **`mail_key` không clamp trước khi ghi vào `String(512)`** — đúng lại bẫy "SQLite không enforce VARCHAR, Postgres có" mà repo đã trả giá ở `normalize._fit()`, chỉ khác tên field. `Message-ID` do máy chủ của người lạ sinh và RFC 2822 cho phép dài gần cả dòng header; reviewer reproduce được id 521 ký tự. Nổ giữa flush ⇒ mất cả batch. **Cắt là sai ở đây** (khác với `label`): hai id trùng 512 ký tự đầu sẽ biến thành *một* thư và một cái không bao giờ được đọc. Nên id quá dài thì **hash** — vẫn duy nhất, vẫn có biên; id bình thường giữ nguyên để bảng còn đọc được.
  2. **`accept_suggestion` có hai commit** — `record_outcome` commit outcome rồi mới tới `found.status = ACCEPTED` + commit lần hai. Crash vào khe giữa ⇒ event đã ghi mà suggestion vẫn `pending`, lần bấm sau ghi event **lần thứ hai**. Sửa bằng cách đánh dấu **trước** rồi để `record_outcome` commit cả hai trong cùng một transaction. Test cũ chỉ cover double-click tự nguyện, không cover crash-and-retry.
  3. **Route `dismiss` trả `SuggestionOut` không kèm job** ⇒ `job_title`/`company` rỗng, cùng một kiểu dữ liệu mà hai endpoint trả khác nhau — thứ không ai nhận ra cho tới lúc có chỗ render trắng.

  Cộng một nit: type `verdict` bên TS chỉ có `OutcomeType`, trong khi cột còn ghi `auto_ack`/`unrelated`. 614 test pass sau khi sửa.

- ✅ **Phase 20** — Chạy model trên chính máy mình: `jobpilot/llm/ollama.py` + engine Ollama cho cả ba lệnh gọi LLM. Xuất phát từ một câu hỏi rất thẳng của user — *"task này có thật sự cần model tốn tiền không?"* — và câu trả lời hoá ra **khác nhau cho từng lệnh gọi**, nên config chọn provider **theo từng việc** chứ không phải một công tắc chung.

  **Lý do thật không phải tiền, mà là riêng tư.** Đo được: một lần tailor ≈ **$0.057**, một email ≈ $0.005 (Opus 4.8, JD ~8.000 ký tự). 100 tailor + 300 email ≈ **$7**. Tiền không phải vấn đề. Vấn đề là input của tailor là **toàn bộ Master CV** — họ tên, số điện thoại, lịch sử làm việc — và điều khoản **free tier** của Gemini cho phép nhà cung cấp train trên input/output. Với một repo mà nguyên tắc 3 là *"không commit thông tin cá nhân"* thì gửi CV lên free tier còn tệ hơn commit vào private repo. Local thì CV **không rời khỏi máy** — nó thắng cả Claude về nguyên tắc 3, và miễn phí chỉ là hệ quả.

  **Constrained decoding là thứ làm chuyện này khả thi.** Ollama nhận JSON Schema ở `format` rồi biến thành *grammar giải mã* — model không thể phát ra token phá schema. Đúng chỗ model nhỏ yếu nhất thì bị loại bỏ về mặt cơ học, còn lại đúng chỗ guardrail đã được xây để canh. `$defs`/`$ref` của Pydantic được **inline trước khi gửi** (`flatten_schema`): reference là góc yếu nhất của schema-to-grammar.

  **Vòng guardrail dùng chung, không fork.** `_GuardedTailor` giữ dựng-prompt + check + một vòng sửa; engine chỉ cung cấp `_parse`. Có test ghim `OllamaTailorEngine.tailor is ClaudeTailorEngine.tailor`. Đây là bài học Phase 16 (*"đừng fork hàm diff"*) áp vào chỗ nguy hiểm hơn: model yếu **cần** vòng retry đó nhiều hơn Claude, nên hai bên bắt buộc phải là **cùng một** vòng retry.

  **Kết quả đo thật trên RTX 3060 Laptop (6 GB VRAM), `qwen2.5:7b`:**

  | Lệnh gọi | Kết quả | Kết luận |
  |---|---|---|
  | **classify** (1 email → 6 nhãn + trích 1 câu) | **5/5 nhãn đúng**, ~2s/thư sau lần nạp đầu (62s) | ✅ bật local |
  | **tailor** (xếp lại index + 1 đoạn summary) | **0/4** sau **ba** vòng vá prompt | ❌ giữ Claude |

  **Tailor thất bại theo một kiểu rất cụ thể, và nó dạy được nhiều thứ.** Vòng 1: `section_order` thiếu key. Vòng 2 (sau khi vá): dùng `item_order` cho section kiểu entries. Vòng 3 (sau khi vá tiếp): **đảo chiều** — dùng `entry_order` cho section kiểu bullets. Nó không hết nhầm mà chỉ **hoán vị** chỗ nhầm ⇒ 7B không giữ nổi ánh xạ *section type → order field*, kể cả khi được liệt kê tường minh từng dòng. Quan trọng: đây **không** phải lỗi "bịa nội dung" — guardrail truthfulness không hề bị chạm tới; nó là lỗi *điều hướng schema*.

  **Hai lỗi prompt tìm ra nhờ chạy model yếu, và cả hai đều có lợi cho Claude:**
  1. `section_order` có cửa thoát "để rỗng = giữ nguyên" **trong schema** nhưng prompt **chưa bao giờ nói**. Model muốn diễn đạt "chỉ mấy mục này quan trọng" nên trả về danh sách một phần — đúng thứ duy nhất không hợp lệ.
  2. **`retry_prompt` không hề sửa cái vừa hỏng.** Nó liệt kê vi phạm rồi khuyên về *index và summary* — trong khi cái vỡ là `section_order`. Vòng "sửa lỗi" trỏ sang luật khác. Claude ít lộ vì nó hiếm khi sai lần đầu, nhưng đây là bug thật của vòng retry. Giờ `_REMEDIES` nhắc lại đúng luật đã vỡ.

  Outline vốn đã in `type=experience` / `type=bullets`, nhưng prompt không giải thích nhãn đó nghĩa là gì — đã bổ sung bảng ánh xạ. Model mạnh suy ra được, model yếu thì không, và việc nói ra không tốn gì.

  **Cũng sửa một luật của chính mình, do chạy thật mới thấy**: `check_verdict` bắt buộc có quote cho **mọi** verdict trừ `unrelated`. Nhưng `auto_ack` cũng **không bao giờ hiện lên card** — nó chỉ được ghi rồi bỏ qua. Model trả lời `auto_ack` **đúng**, không kèm quote, và guard đem câu trả lời đúng đó xếp vào loại "classifier hỏng". Quote tồn tại để user bác cái nhãn *được hiện ra*; không hiện thì không có gì để bác. Giờ chỉ `PROPOSABLE` mới bắt buộc có bằng chứng.

  **Và một test tự phơi mình ra**: `test_missing_tokens_produce_a_readable_error` chỉ ép rỗng **một** trong ba khoá Slack, hai khoá kia rơi xuống `.env` thật — nên nó xanh chỉ vì máy dev *chưa* cấu hình Slack, và đỏ ngay khi user điền token. Test không được phụ thuộc vào việc máy chạy nó có cấu hình gì.

  Mặc định vẫn là `claude` cho cả ba: đổi model của user trong im lặng là đổi nội dung đơn họ gửi đi.

- ✅ **Phase 20b** — Một tầng provider thay cho hai backend rời: `jobpilot/llm/` giờ có `base.py`
  (hợp đồng `StructuredClient`), ba client (`claude` / `openai` / `gemini`), `registry.py`
  (dict `PROVIDERS`), `schema.py`, `pricing.py`, `usage.py`, `stats.py`, `bench.py`.
  **Ollama bị gỡ hẳn** theo yêu cầu user; `classify` chuyển sang cloud.

  **Lý do thật không phải "dọn dead code".** Phase 20 để ngỏ bốn hướng cho tailor local, và
  câu trả lời hoá ra nằm ở một dòng khác trong nợ kỹ thuật: *Anthropic hết credit*. Cộng với
  `tailor` local 0/4 ⇒ **không có backend nào chạy được cho tailor**. Multi-provider là lối
  thoát khỏi tình trạng đó; "rẻ hơn" thì không phải lý do — tổng chi phí là **$7** cho 100
  tailor + 300 email.

  **Cái đã mất, ghi thẳng ra:** `classify` từng chạy local 5/5 và nội dung thư nhà tuyển dụng
  **không rời khỏi máy**. Giờ nó đi qua API của provider. Docstring ở `apply/inbox.py` đã sửa
  cho khớp — để nguyên là để lại một lời hứa không còn đúng. Phần *vẫn* đúng và vẫn phải đứng
  đầu: thư **không khớp đơn nào** dừng lại trong máy, không bao giờ tới API.

  **Sáu class engine → ba.** Trước đó `_get_client()` của Anthropic bị chép nguyên văn **3 lần**
  và `letter.py` giữ **hai bản** vòng retry (Claude / Ollama) gần giống nhau — đúng thứ
  `_GuardedTailor` được viết ra để tránh, nhưng letter không dùng nó. Thêm 2 provider theo lối
  cũ là **6 class + 6 bản copy**. Giờ mỗi task một engine cầm một `StructuredClient`, và bất
  biến "mọi backend đi qua cùng một vòng retry" do **không còn gì để fork** giữ, chứ không phải
  do một test giữ (test cũ `OllamaTailorEngine.tailor is ClaudeTailorEngine.tailor` mất chỗ
  đứng vì lý do tốt).

  **Ba provider không nhận cùng một JSON Schema** — tra tài liệu chính thức, không đoán:
  OpenAI strict **có** hỗ trợ `$ref`/`$defs` (kể cả đệ quy), giới hạn 10 tầng / 5.000 property /
  1.000 enum, không hỗ trợ `allOf`/`not`/`if-then-else`; Gemini chỉ liệt kê một **subset** và
  cảnh báo schema lồng sâu có thể bị từ chối, nên `flatten_schema` (viết cho Ollama) được giữ
  lại và dùng cho Gemini. `strictify` cho OpenAI có một bẫy đáng ghi: "mọi field phải nằm trong
  `required`" **không** có nghĩa bỏ optional — optional phải nới thành **nullable**, nếu không
  model bị *ép bịa* ra `summary`. Đọc sai chỗ này là biến một luật về hình dạng thành một lệnh
  bịa nội dung.

  **SDK đúng tên:** Gemini là `google-genai` (`from google import genai`). `google-generativeai`
  **đã deprecated** (hết hỗ trợ 2025-08-31) và hai cái cách nhau một chữ trong `pip install`.

  **Đo thay vì đoán.** Bảng `llm_calls` (migration 0009), **một row mỗi round** — kể cả round bị
  guard từ chối, kể cả lượt gọi hỏng. Lý do: một backend rẻ mỗi lượt mà phải retry một nửa số
  lần thì **không** rẻ, và một bảng chỉ giữ round được nhận sẽ làm nó trông đẹp nhất ở đúng cột
  người ta sort. `GET /stats/llm` + `jobpilot llm stats` + `jobpilot llm bench`.

  **Hai luật "không biết ≠ hỏng" áp vào số liệu:**
  - `cost_usd` **NULL** khi model không có trong `pricing.PRICES`, không phải `0.00`. Bảng giá cũ
    đi bằng cách nằm yên, nên trường hợp không biết giá là **bình thường**, không phải ngoại lệ —
    và $0.00 sẽ khiến backend ít biết nhất trông rẻ nhất. `unpriced_rounds` đi kèm mọi tổng.
  - Dưới `MIN_SAMPLE = 10` thì **không hiện %**, hiện `n=<count>`. 3 lượt 2 lỗi không phải "33%";
    tỉ lệ mời người ta so hai backend trên 3 lượt mỗi bên. Cùng luật `outcome_counts` đã theo.

  **Cảnh báo dữ liệu phải hẹp mới có người đọc.** Tra terms: Anthropic / OpenAI / Gemini **trả
  tiền** đều không train trên input API. Chỉ **Gemini free tier** là có, và terms ghi thẳng *"Do
  not submit sensitive, confidential, or personal information to the Unpaid Services"* — trong
  khi `tailor`/`letter` gửi **cả Master CV**. Không đọc được tier từ API key ⇒ `llm.gemini_paid_tier`.
  Là **thông báo, không phải cổng chặn** (user chọn "cho hết, cảnh báo rõ").

  **Bug chỉ lộ ra khi chạy thật — và nó lộ ra ở đúng chỗ mỉa mai nhất.** `llm bench` chạy xong,
  in kết quả, và **mất sạch** row telemetry: bench dùng `Applied(0, ...)` (application giả), FK
  `llm_calls.application_id` vỡ, và `record()` *nuốt lỗi theo thiết kế* nên không ai biết. Tức
  là lệnh mà toàn bộ nhiệm vụ là **tạo ra một phép đo** đã lặng lẽ vứt phép đo đi. Sửa hai lớp:
  `ModelClassifier` truyền `app.application_id or None`, và `record()` ghi **hai lần** — có link,
  rồi nếu vỡ thì không link. Mất cái liên kết còn hơn mất con số. Bài học: *"nuốt lỗi để không
  làm hỏng việc chính"* đúng, nhưng nó cũng chính là thứ giấu lỗi khỏi mắt mình.

  **Console Windows là cp1252.** Em dash trong chuỗi `print()` làm `UnicodeEncodeError` và giết
  cả lệnh. Mọi chuỗi in ra terminal giờ ASCII (docstring thì không sao). `cli.py:326` và `:446`
  vẫn còn hai em dash **có sẵn từ trước** — cùng lỗi tiềm ẩn, chưa sửa vì ngoài phạm vi.

  **Hai thứ review gate bắt được, ghi lại vì cả hai đều thuộc loại "chỉ sai một chiều":**
  - `first_try_rate` **tính sai** khi một task retry rồi *vẫn* hỏng. `first_try = successes -
    retries`, nhưng `retries` đếm **mọi** round-2 trong khi `successes` không hề chứa task hỏng
    ⇒ một task hỏng triệt tiêu một task first-try không liên quan. 8 sạch + 1 retry-ok +
    1 retry-fail cho **70%** thay vì 80%; 5 sạch + 5 retry-fail cho **0%** thay vì 50%, và
    `max(..., 0)` **che** lỗi chứ không sửa. Luật rút ra: *hai vế của một phép trừ phải đang đếm
    cùng một tập*. Sai theo hướng làm backend trông tệ hơn thực tế — trong đúng bảng dùng để
    chọn backend. Đã ghim 2 test.
  - `LlmCall.ok` mặc định `True` trong khi `CallLog.accepted` mặc định `False` với lý do đã viết
    rõ ("một row chưa ai set kết quả không phải là một thành công không ai nhận được"). Hai mặc
    định ngược nhau cho cùng một khái niệm. Đổi cả model lẫn `server_default` về `false`.

  **Thay đổi hành vi nhỏ, ghi ra vì nó không tự hiện:** `ClaudeClassifier` cũ **không** truyền
  `thinking`; `ClaudeClient` dùng chung thì có (`adaptive`). Giữ nguyên một call shape thay vì
  thêm một knob theo task vào hợp đồng dùng chung — `adaptive` nghĩa là model tự quyết, và với
  6 nhãn thì nó gần như không nghĩ. Nếu sai thì **chính bảng phase này thêm** sẽ cho thấy:
  `llm stats` đo output token và latency của `classify` tách riêng.

  **Blocker đổi nghĩa:** không còn "ollama serve có chạy không" mà là "provider đang cấu hình đã
  có API key chưa". Nó nằm trong `get_engine()` của route chứ **không** trong route body — để
  test tự cấp engine không bị đòi key, đúng cái bẫy `test_missing_tokens_produce_a_readable_error`
  đã dính ở Phase 20 (xanh/đỏ tuỳ máy chạy có cấu hình gì).

  **Verify thật:** 637 test, ruff + `tsc` sạch; `alembic upgrade head` → `downgrade -1` → `upgrade`
  trên **PostgreSQL 17 local**; `llm bench --task classify` chạy đầu-cuối và ghi 5 row vào
  `llm_calls` thật; `GET /stats/llm` trả đúng (`first_try_rate=None`, `n=5`, `cost_usd=None`,
  `unpriced_rounds=5`); trỏ `llm.tailor: gemini` + `gemini_paid_tier: false` → `POST /jobs/../tailor`
  trả **409** kèm lý do đọc được, và cảnh báo về Master CV hiện đúng.
  **Chưa verify được: một lượt gọi *thành công*.** Anthropic hết credit, `OPENAI_API_KEY` bị từ
  chối 401, chưa có `GOOGLE_API_KEY` — nên **shape request của OpenAI/Gemini chưa đối chiếu với
  API thật** (401 xảy ra trước khi request được validate). Đó là việc đầu tiên khi có key.

- ✅ **Phase 20c** — Quản lý model từ Web, và ba luật user đặt: **(1) không leak key, (2) đổi được
  model + có dashboard đo, (3) mặc định model rẻ nhất mà vẫn hiệu quả.** Trang `/models`
  (`web/src/pages/Models.tsx`) + `llm/redact.py` + `llm/registry.list_models` + `llm.budget_usd`.

  **Cả ba provider đã gọi thật thành công** (trước đó chưa verify được lượt nào). Đo trên bộ 5
  email của Phase 20, **tất cả 5/5**:

  | model | 5 email | p50 |
  |---|---|---|
  | `gpt-4o-mini` | **$0.0005** | 1324ms |
  | `gemini-3.1-flash-lite` | $0.0007 | **705ms** |
  | `gemini-3.5-flash-lite` | $0.0010 | 773ms |
  | `gpt-4.1-mini` | $0.0013 | 1185ms |
  | `claude-haiku-4-5` | $0.0043 | 1256ms |
  | `gemini-3.5-flash` | $0.0187 | 2110ms |

  Rẻ nhất **và** nhanh nhất là `gemini-3.1-flash-lite` ⇒ đã đặt cho `classify` **qua chính cái
  picker trên web**, tức là vừa test tính năng vừa áp dụng luật 3. `tailor` trên
  `claude-opus-4-8` chạy job thật: **2/2 qua guardrail ngay vòng đầu**. Ghi chú: `gemini-3.5-flash`
  đắt gấp ~27× bản lite vì **thinking token tính giá output**.

  **Leak thật, tìm được vì chạy thật.** Key OpenAI sai ⇒ provider trả *"Incorrect API key
  provided: sk-proj-…"*, và chuỗi đó đi thẳng vào `llm_calls.error`, ra CLI, ra API. Nên scrub
  đặt ở **chỗ tạo ra lỗi** (`LlmError.__init__` + `CallLog`), không phải ở từng nơi lỗi đi tới —
  có một chỗ đầu và vô số chỗ sau, và những chỗ thêm sau chính là những chỗ không ai nhớ bảo vệ.
  Hai lớp: **giá trị thật** (mọi secret process đang giữ) + **hình dạng** (`sk-…`, `AIza…`,
  `Bearer …`, password trong DSN) cho key mình không giữ. **Và ngay sau đó lộ thêm một chỗ nữa**:
  `list_models` log exception thô — quên `redact()`. Bài học: mỗi `log.warning` mang exception
  của SDK là một đường rò mới.

  **Biến môi trường đè `.env` — mất một buổi debug.** User test key bằng PowerShell → 200; app
  gửi đi → 401. Cả hai key **dài đúng 164 ký tự, cùng prefix `sk-proj-`**, nên không có gì trông
  sai. Nguyên nhân: pydantic-settings **ưu tiên biến môi trường hơn `.env`**, và máy còn một
  `OPENAI_API_KEY` cũ. Triệu chứng *y hệt* key hỏng, nên mọi bước tiếp theo (chép lại key, kiểm
  tra dấu nháy, đếm độ dài) đều đi soi đúng cái file **không được đọc**. Cách tìm ra: **hash hai
  giá trị rồi so** — không in ra. Giờ `llm providers` và trang `/models` cảnh báo thẳng
  (`redact.shadowed_secrets`).

  **"Credit còn lại" không lấy được từ provider** — đã thử: Anthropic `cost_report` và OpenAI
  `organization/costs` đều đòi **Admin key**, trả 401 với key thường. Nên `llm.budget_usd` là số
  **user tự nhập**, còn "đã dùng" là phần **JobPilot tự đo**; "còn lại" là hiệu hai số đó và UI
  nói rõ **đây là bộ đếm ngân sách, không phải số dư tài khoản**. Không bịa ra một con số trông
  như số dư — đúng luật "sai dữ liệu *trông như đúng* tệ hơn thiếu dữ liệu".

  **Ba bug kiểu "báo cáo thành công nhưng sai", cả ba chỉ lộ khi chạy thật:**
  1. `thinking={"type":"adaptive"}` áp cho mọi model ⇒ Haiku trả 400 *"adaptive thinking is not
     supported on this model"*. Không phải chuyện tốn token — nó **chặn luôn cả tầng model rẻ**,
     tức chặn đúng luật 3. Sửa: registry tắt thinking cho `classify`, và client **tự tắt rồi gọi
     lại một lần** khi gặp đúng lỗi đó — không hardcode danh sách model (danh sách sai ngay tuần
     có model mới).
  2. `models.list()` của Gemini **có** `gemini-2.5-flash`, nhưng `generateContent` trả **404
     "no longer available to new users"**. Danh sách là *menu*, không phải lời hứa.
  3. So id model bằng `==` đánh dấu `claude-haiku-4-5` là "không khả dụng" vì Anthropic liệt kê
     bản có ngày `claude-haiku-4-5-20251001`. Phải so **theo prefix** — và cái bị đánh dấu sai
     lại đúng là model rẻ đạt 5/5, tức bug chỉ đường **tránh xa** câu trả lời mà trang này sinh
     ra để tìm.

  **Một bug do nuốt lỗi, lần thứ hai trong hai phase.** `list_models` trả `[]` cho Gemini; thêm
  log mới thấy *"Cannot send a request, as the client has been closed"* — `genai.Client(...)` viết
  inline trong comprehension bị GC giữa chừng vì pager là lazy. Đọc như lỗi auth mà không phải.

  **Hai test tự phơi mình ra khi config đổi:**
  `test_the_shipped_config_is_what_it_claims_to_be` đọc `get_config()` (đã merge
  `config.local.yaml`) nên đỏ ngay khi user đổi backend — **đúng cái bẫy máy-phụ-thuộc mà Phase
  20 đã sửa một lần**; giờ đọc thẳng `config.yaml`. Và test chống-leak viết theo *snapshot* danh
  sách field thì vỡ mỗi lần thêm tính năng ⇒ đổi thành **luật**: tên giống secret **và** kiểu
  string. Viết luật cũng phải cẩn thận: bản đầu bắt nhầm `has_key` (bool) và `input_tokens` (int) —
  một check hay kêu oan là một check bị người ta tắt.

  **Verify:** 642 test, ruff + `tsc` sạch; trang `/models` chụp thật ở **light + dark**, console
  sạch; đổi provider+model bằng chuột → ghi `config.local.yaml` → `llm bench` chạy đúng backend
  mới. Lưu ý khi verify web: **API chạy bằng uvicorn không `--reload` sẽ giữ code cũ** — hai
  "bug" đầu tiên nhìn thấy trên trang hoá ra chỉ là server chưa restart.

- ✅ **Phase 20c (tiếp)** — Sau khi user gỡ biến môi trường `OPENAI_API_KEY` cũ: `.env` được đọc
  đúng (fingerprint khớp), `shadowed_secrets()` rỗng, cảnh báo biến mất khỏi `llm providers` và
  trang `/models`. **OpenAI chạy thật cho cả hai schema** — `MailVerdict` 5/5 và `TailorPlan`
  **1/1 qua guardrail vòng đầu** dưới strict mode. Tức cả ba provider giờ đã verify trên cả
  schema phẳng lẫn schema lồng; không còn đường nào "chưa bao giờ gọi thật".

  **Và bộ đo lập tức bác bỏ kết luận trước đó của chính mình.** Ở **n=5**, `gemini-3.1-flash-lite`
  là rẻ nhất *và* nhanh nhất (p50 **705ms**). Lên **n=10**: p50 thành **2732ms**, còn `gpt-4o-mini`
  1101ms với giá thấp hơn ⇒ **đảo ngược cả hai tiêu chí**. Đã đổi `classify` sang
  `openai/gpt-4o-mini`. Đây chính xác là thứ `MIN_SAMPLE` được viết ra để ngăn — và nó ngăn được
  người viết ra nó, vì tôi đã đọc con số `n=5` như thể nó là một tỉ lệ. **Luật rút ra: khi cột tỉ
  lệ còn hiện `n=<count>` thì chưa được chốt model.**

  `tailor` trên `gpt-4.1`: 1/1 vòng đầu, ~$0.016 và ~9s so với `claude-opus-4-8` ~$0.10 và ~39s.
  **Chưa đổi** — guardrail chỉ chứng minh *không bịa*, không chứng minh xếp hạng tốt; và n=1 thì
  không phải bằng chứng. Muốn đổi thì phải đọc bản CV thật ở trang CV Review.

  **Review gate (2 subagent, cả hai chạy trên diff thật):** `phase-reviewer` → APPROVE kèm 2
  "nên sửa"; một agent **security review** riêng → 3 finding. Hai bên **độc lập tìm ra cùng một
  lỗ** (`PUT /settings` ghi được secret xuống `config.local.yaml`), điều đó làm nó đáng tin hơn
  hẳn một report đơn lẻ. Đã sửa cả ba trước khi push:
  1. **Traceback rò key** (`orchestrator.py:225`) — nặng nhất, và tinh vi nhất. `LlmError` scrub
     *message* của chính nó, nhưng nó được `raise ... from exc`, và **exception gốc của SDK vẫn
     trích nguyên key**. `str(exc)` sạch, `traceback.format_exc()` thì **không** — mà task hỏng
     nào cũng log cái thứ hai. Bài học tổng quát: scrub theo *chuỗi nguyên nhân*, không chỉ theo
     một object; bất kỳ chỗ nào render traceback là một sink mới.
  2. **`PUT /settings` ghi secret ra `config.local.yaml`** — Pydantic *bỏ qua* field lạ chứ không
     từ chối, nên validate vẫn pass trong khi overlay được ghi từ **dict thô**. Sửa bằng
     `config.prune_to_schema()` đặt **trước** bước merge, và áp cho **mọi** section (`app`,
     `crawl`, `apply`, `cv` cùng dính lỗ này, không riêng `llm`).
  3. **`_offered()` prefix quá lỏng** — `gemini-3.5-flash-lite` "bảo lãnh" cho
     `gemini-3.5-flash`, khiến một model đã bị withdraw hiện ra là dùng được. Prefix chỉ hợp lệ
     khi phần đuôi là **8 chữ số** (date snapshot của Anthropic). Date = cùng model; `-lite` =
     model khác.
  Thêm `ya29.` vào `_SHAPES` (chưa dùng tới, nhưng rẻ), và bỏ `BenchResult.latency_ms` +
  `median_latency_ms` — dead code chưa bao giờ được ghi. 645 test.

- ✅ **Phase 21** — Trang **/market**: nghiên cứu thị trường từ corpus đã crawl. `crawler/salary.py`
  + `crawler/skills.py` + `vietnam.canonical_city` (Phase A: trích dữ liệu), `analytics/market.py`
  + `GET /analytics/market` + `web/src/pages/Market.tsx` (Phase B: đo và vẽ).

  **Đếm dữ liệu trước khi thiết kế, và nó đổi hẳn thứ tự công việc.** Yêu cầu là "nhiều biểu đồ
  thống kê + nghiên cứu thị trường". Đếm thật: `applications` **0**, `application_events` **0**
  ⇒ mọi funnel sau khi nộp trống; `salary` **3/73** mà **2 là bug scraper**; `skills` 24/73 và
  LinkedIn (**57% corpus**) không có tag nào. Vẽ 12 biểu đồ lúc đó = một trang đầy panel trống
  và sai. Nên: **làm dữ liệu trước, biểu đồ sau**.

  **Luật của phase này: mỗi facet tự khai mẫu số.** `Facet.covered/total`, hiện ra UI là
  "18 of 73 jobs" chứ không phải một %. Lý do rất cụ thể: một bảng xếp hạng skill dựng từ 18/73
  job là *sự thật về 18 job* và *hư cấu về thị trường* — chỉ mẫu số phân biệt được hai thứ đó.
  Cùng họ với `MIN_SAMPLE` của `llm/stats.py`, áp cho một kiểu "mỏng" khác.

  **Ba lỗi "trông như đúng", cả ba chỉ thấy khi nhìn biểu đồ thật:**
  1. **Skill**: `+2` (badge tràn của card ITviec), `Vollzeit`, `Backend Developer`,
     `IT Services and IT Consulting`, `India` đứng ngang `Java`. Lọc bằng **pattern**, không
     bằng blocklist: `_ROLE_RE` khớp **danh từ số ít** nên bỏ "software engineer" mà vẫn giữ
     "data engineering" — phân biệt đó chính là lý do nó là regex.
  2. **City**: `Hà Nội` / `Ha Noi` / `Hanoi` ra **ba cột**, mỗi cột 1/3 số thật (4+4+3 → 11).
     `canonical_city` fold ASCII rồi map alias — cùng kỹ thuật `apply/inbox.fold` đã dùng để so
     tên công ty với domain.
  3. **Lương**: `"15tr - 25tr"` ra **15–15**. Unit nằm giữa số và dấu gạch làm vỡ regex range,
     rơi xuống nhánh một-số, trần bị giảm một nửa **không báo gì**.

  **Hai lỗi biểu đồ, phát hiện bằng cách nhìn ảnh chụp chứ không phải bằng test:**
  - Tô 8 màu categorical xuống 15 dòng skill = tô theo **thứ hạng**. Màu phải theo *thực thể*;
    đổi filter là đổi màu, tức là mã hoá một thứ không tồn tại. Một measure ⇒ một màu.
  - `SOURCE_ORDER` có 10 mục nhưng palette có 8 hue ⇒ `lever` (index 8) đội đúng màu xanh của
    `itviec`. Hai board cùng màu **tệ hơn** một board lạ không có màu riêng, vì nó trông như cố ý.

  **Không đoán khi thiếu ký hiệu**: `"20 - 60"` không có currency ⇒ `None` (là triệu VND hay
  USD/giờ tuỳ board — đoán là tung đồng xu rồi trình bày như sự thật). `"Up to 3000"` ⇒
  `min=None`, không bịa 0 (một midpoint tưởng tượng sẽ kéo tụt median cả corpus). Quy đổi USD
  dùng `USD_VND_RATE` kèm `FX_CHECKED_ON`, UI gọi nó là **ước tính** — cùng họ với bảng giá
  `llm/pricing.py`, và nó **sẽ** cũ đi.

  **Sidebar**: `Layout.tsx` **đã có** một sidebar (8 mục). Không thêm cái thứ hai ở tầng Layout —
  sẽ đổi bố cục mọi trang để phục vụ một trang. Section-nav nằm **trong** `Market.tsx`.

  **Verify:** 658 test; `backfill --force` chạy trên **73 job thật** rồi *đọc tay* output (banner
  ITviec → `None`, lương thật → số đúng, city gộp đúng); `/market` chụp thật **light + dark**,
  console sạch. `--force` tồn tại vì một bản vá *parser* phải chạy lại được trên chính những row
  mà nó từng trả lời sai — không có nó thì bug bị đóng băng vào dữ liệu nó làm hỏng.

---

## CV Studio — preview đọc được, và LaTeX sửa được (theo yêu cầu, không phải phase đánh số)

**Ba lời phàn nàn về khung preview, sửa theo đúng thứ tự nó làm phiền.**

- **Mảng đen dưới trang.** Khung ghim `h-[780px]`, mà trang A4 fit theo bề rộng rail 378px chỉ
  cao ~535px ⇒ 245px còn lại là **nền của chính PDF viewer**. Không lấy tỉ lệ A4 trần được: đo
  thật thì viewer chèn ~4px mỗi bên, ~3px trên, và fit trang vào phần *bên trong* padding đó —
  dùng 210/297 thẳng là luôn **ước lượng thừa**. Nay ước lượng **hụt 2px có chủ ý** rồi clip
  phần dư: sai thì mất 2px của lề 1.5cm, không phải hiện một vệt đen.
- **Không đọc nổi.** Rail 378px, CV là một tài liệu. Thêm chế độ toàn màn hình + link mở tab mới.
  Overlay **portal ra `<body>`**: để nguyên tại chỗ thì nó nằm trong subtree `sticky` của rail,
  và header dính của app vẽ đè lên — nút Close **bấm không được**. Không nhìn ảnh nào ra;
  Playwright báo thẳng `<header …> intercepts pointer events`. Đây là lý do drive UI thật khác
  với chụp ảnh UI.
- **Trống trơn tới khi bấm Compile**, dù PDF đã nằm sẵn trên đĩa. Giờ fetch ngay lúc mount.

**Một bug tự lộ ra khi đang sửa:** object URL bị `revokeObjectURL` trong **cleanup** của effect —
tức đúng lúc compile *bắt đầu*. Suốt ~10–30s Docker build, khung trỏ vào blob đã huỷ. Giờ chỉ
revoke bản cũ **sau khi** bản mới về. Bài học cũ dạng mới: dọn dẹp theo vòng đời của *effect*
trong khi thứ được dọn có vòng đời của *màn hình*.

**Raw LaTeX (user chọn phương án "lưu override vào version").**

- JSON **vẫn** là nguồn sự thật cho CV *nói gì*; override chỉ đè lên cách nó *serialize* — đúng
  những thứ editor không có field: `\vspace` kéo dòng mồ côi về trang 1, macro Awesome-CV mà
  schema không mô hình hoá. Lưu ở `cv_versions.meta.tex_override` ⇒ **không cần migration**, và
  mỗi version ghi lại đúng thứ đã build.
- **Đánh đổi một chiều, và UI phải nói ra**: không có gì parse `.tex` ngược về JSON, nên khi
  override còn hiệu lực thì các field **không tới được PDF**. Banner trong tab + dòng dưới tiêu đề
  trang + một cú bấm để revert. Override ghi **đè lên** project đã render, nên sửa `cv.tex` thì
  các file section vẫn bám theo JSON.
- **Hai thứ cố tình KHÔNG làm**: (1) lưu document **không** xoá override — mất `.tex` viết tay chỉ
  vì sửa số điện thoại là không thể bào chữa; xoá có động từ riêng (`DELETE`), và `PUT` với
  `files: {}` trả **422** chứ không lặng lẽ thành delete. (2) **rollback mang override về theo**,
  vì "khôi phục v7" phải nghĩa là *bản PDF mà v7 đã tạo ra* — lấy document mà bỏ `.tex` nó compile
  từ đó là khôi phục một version chưa từng tồn tại.
- Path trong override được validate **trước khi** thành path dưới `out/cv/<scope>/`: tương đối,
  không traversal, không backslash, chỉ `.tex`. Backslash phải chặn riêng: `PurePosixPath` đọc
  `a\b.tex` là **một** segment vô hại, còn Windows thì không.
- Editor là gutter + textarea có bắt phím Tab, **không** Monaco — ~5 MB dependency để tô màu cú
  pháp cho một file hiếm khi mở.

**Verify:** 677 test; `tsc` sạch; chạy thật đầu-cuối trên browser headed + API + Postgres + Docker
LaTeX: sửa `resume/summary.tex` chèn marker → Save → Compile → **đọc lại PDF bằng pypdf thấy
marker** → Revert → Compile → marker biến mất. Cửa sổ read-only lúc save verify bằng cách **giữ
request mở** (route delay), không phải bằng cách đua với nó. Ảnh light + dark.

**Reviewer bắt 4 lỗi, sửa hết trước khi push**: textarea vẫn gõ được trong lúc save (refetch sau đó
ghi đè thứ vừa gõ), `PUT {"files": {}}` ngầm thành `DELETE`, `onClose` inline dựng lại effect phím
Esc mỗi lần parent render, và rollback làm rơi override.

**Ghi chú môi trường:** headless Chrome không có PDF viewer ⇒ mọi kiểm tra preview phải chạy
`headless=False`. Lỗi console duy nhất còn lại là `chrome-extension://…/pdf_embedder.css` — asset
của chính PDF viewer trong Chrome, không phải của app.

---

## /market — biểu đồ đọc được, và một trục thời gian không có thời gian (theo yêu cầu)

Phàn nàn của user, đúng chữ: *"market#source và market#calendar đang giống nhau?? và màu các
biểu đồ xấu, ko có biểu đồ tròn, nhìn ko chuyên nghiệp."* Cả ba đều đúng, và đào xuống thì
dưới hai cái đầu là bug thật chứ không phải chuyện thẩm mỹ.

**"Giống nhau" là thật, và lý do nó xảy ra đáng ghi lại.** Hai card cuối trang cùng là bar
chart, và cùng **một màu xanh lá `#008300`**: `sourceColor("linkedin")` rơi vào slot 3 vì
LinkedIn đứng thứ tư trong `SOURCE_ORDER`, còn calendar thì hardcode `categorical()[3]`. Không
ai chọn cho chúng trùng nhau — một bên đánh số theo *thực thể*, một bên theo *chỉ số palette*,
và hai hệ đánh số đó va vào nhau ở đúng một chỗ. Chọn màu bằng index trần là còn để ngỏ khả
năng này ở mọi biểu đồ khác. Giờ mọi chart đo *số lượng job* dùng chung một hằng `MEASURE`, và
hue chỉ được dùng ở nơi hue mang thông tin.

**`axisColor()` trả về một chuỗi không phải màu — và light mode che mất chuyện đó.**
`--ink-muted` lưu **RGB channels** (`"157 155 144"`) để Tailwind ghép `rgb(var(--x) / <alpha>)`.
`ChartFrame.axisColor()` đọc thẳng chuỗi đó rồi đưa vào `fill` của SVG ⇒ thuộc tính **không
hợp lệ, bị bỏ qua im lặng**, chữ rơi về mặc định gần đen. Trên nền sáng nó trông như một màu
xám hơi đậm và không ai để ý; trên nền tối **mọi nhãn trục biến mất**. Chính `index.css` đã ghi
chú "--grid / --viz-surface stay hex: charts read them back" — biết luật, nhưng `--ink-muted`
thì lọt. Cùng họ với `+2` và `Hiring`: thứ nguy hiểm là cái *báo cáo thành công*.

**Ảnh chụp dark mode đã sai suốt nhiều vòng, và script chụp mới là thứ hỏng.** Script bật
`.dark` bằng JS **sau khi** React mount. CSS repaint ngay nên ảnh *trông* tối, nhưng chart đọc
`isDark()` trong lúc render ⇒ vẫn giữ nguyên palette light. Nghĩa là mấy lượt "verify dark mode"
đầu tiên không verify gì cả. Phải set `localStorage` trong `add_init_script` **trước khi** app
boot (index.html đã đọc key đó sẵn). Đúng bài học "đừng để công cụ đo bịa ra finding", lần này
là công cụ đo *giấu* finding.

**Trục thời gian không có thời gian.** `posting_calendar` phát ra *các ngày có bài đăng* rồi lấy
30 phần tử cuối. Trên corpus thật: `2024-02-21`, `2024-03-12`, `2025-02-25`, `2025-08-07`, rồi
`2026-07-07`… — bốn cái lẻ chiếm bốn ô cạnh nhau, nên **khoảng cách giữa hai điểm liền kề khi
là một ngày, khi là mười tám tháng**. Biểu đồ tự co giãn trục của chính nó mà không nói, và ba
tuần tuyển dụng thật bị nén vào một phần ba bên phải. Nay là **cửa sổ lịch 30 ngày thật,
zero-fill**, và số bài rơi ngoài cửa sổ được **đếm và khai ra** (`covered` phải tiếp tục nghĩa
là "job biểu đồ này thực sự vẽ" — đó là con số cả trang đứng trên). Ba test ghim.

**Biểu đồ tròn: có, nhưng thứ tự lát cắt là do đo mà ra, không phải do thẩm mỹ.** Palette 8 hue
chỉ được validate cho các cặp **kề nhau trong thứ tự slot cố định** — đó là cơ chế an toàn CVD,
không phải trang trí. Donut xếp theo *số lượng* thì hai nguồn nào tình cờ đứng cạnh nhau sẽ
chạm nhau: đo trên corpus này ra **xám cạnh magenta, ΔE 2.1 (deutan)** ở dark mode, tức một
đường biên vô hình. Xếp vòng theo **slot palette** thì cặp tệ nhất là **ΔE 41**. Nên vòng xếp
theo slot, còn *xếp hạng* — thứ người ta thực sự muốn — nằm ở legend, đọc bằng số. Cũng đã thử
sửa bằng cách nhích một hue: **không cứu được**, trần all-pairs của bộ dark chỉ tới ΔE 4.7 (cặp
bị chặn chuyển sang aqua↔magenta, chẳng liên quan gì tới hue vừa sửa). Tối đa 6 lát, đuôi gộp
vào "Other" màu xám — và hàng legend của các nguồn bị gộp **cũng** màu xám, vì xám là lát cắt
chúng đang nằm trong; cho chúng hue riêng là chỉ vào một lát không có trên vòng.

**Màu theo *việc* nó làm, không theo card:** nominal (skill, city) một hue; ordinal (seniority)
ramp một hue đã chạy `validateOrdinal` — và ramp phải **đổi bước theo n**, ép 6 bước vào dải
light thì hai bước giữa thành cùng một xanh (n=6 light: không có bộ nào hợp lệ); histogram đã
có trục mang thứ tự nên **không** ramp (ramp = mã hoá vị trí x lần thứ hai bằng hue); quality là
**trạng thái** nên dùng status scale, kèm icon + chữ như scale đó bắt buộc — `undated` để **xám
trung tính**, vì không có ngày là *không biết*, không phải *hỏng*.

**Lặt vặt nhưng là phần "trông không chuyên nghiệp":** nhãn thô (`no_jd`, `ci/cd`,
`weworkremotely`) rò tên cột ra trục ⇒ `web/src/lib/labels.ts` dịch ở rìa, fallback title-case
để flag mới vẫn đọc được ngày nó xuất hiện; `$1574.8` khoe độ chính xác mà một con số quy đổi
từ tỉ giá có ngày kiểm tra không hề có ⇒ `$1,575`; card "Pay distribution" với **1/83** job là
đúng cái "one-bar bar chart" nên là một con số ⇒ dưới `MIN_SAMPLE` thì hiện số, không hiện lưới
trống; `type="monotone"` vẽ đỉnh vào những ngày không ai đăng ⇒ `linear`.

**Verify:** 681 test; `tsc` sạch; `/market` chụp thật light + dark **có set theme trước khi
boot**, console sạch; `GET /analytics/market` đọc từ Postgres thật (30 row lịch, `covered` 66/83,
note khai 6 bài ngoài cửa sổ). Palette chạy qua `validate_palette.js` của skill `dataviz` cho
đúng surface của app (`#ffffff` / `#1a1a19`), không ước lượng bằng mắt.

**Bẫy môi trường mất 20 phút:** sửa backend xong `--reload` không ăn. Không phải reloader —
lần restart trước để lại một **worker mồ côi** vẫn giữ cổng 8000 (Windows cho hai process bind
cùng cổng), nên request rơi vào bản cũ. `Get-CimInstance Win32_Process` thấy cả `--multiprocessing-fork`
mồ côi lẫn reloader mới. Curl API trả kết quả cũ trong khi `python -c` cùng module trả kết quả
mới ⇒ nghi ngay có hai process, đừng nghi cache.

---

## Phân trang ở backend (theo yêu cầu)

Yêu cầu: *"Các trang, các list đều chưa phân trang -> làm ở BE phân trang (cho
option chọn số item/page)."* Bảy list endpoint, tất cả đang trả **mảng JSON trần**.

**Mảng trần không trả lời được câu hỏi quan trọng nhất.** 25 dòng trên tổng 25 và
25 dòng trên tổng 900 là **cùng một mảng** trên đường truyền. Không có `total` thì
pager hoặc nói dối là đã hết, hoặc đoán bằng `items.length === limit` — sai đúng
vào lúc tổng là bội số của page size. Nên mọi list giờ trả `Page{items, total,
limit, offset}` (`api/schemas.Page`, generic Pydantic). Đây là **breaking change**
với mọi client: Slack, frontend, và 26 test.

**Bẫy thật của phân trang không phải `LIMIT`, mà là thứ tự.** `LIMIT/OFFSET` trên
một `ORDER BY` có **tie** là bug im lặng, không phải bug thẩm mỹ: các dòng bằng
nhau ở khoá sắp xếp có thể ra theo thứ tự khác nhau giữa truy vấn trang 1 và trang
2, nên một job hiện **hai lần** còn một job **không bao giờ** hiện. Không có
exception nào, chỉ là bạn không thấy một tin tuyển dụng. Trong corpus này điều đó
gần như chắc chắn xảy ra: `posted_at` **null** với mọi job từ LinkedIn alert và
giống hệt nhau trong cả một mẻ crawl. Nên mọi thứ tự giờ kết thúc bằng một cột
**unique** (`Job.id`, `Application.id`, `InboxSuggestion.id`, `CvVersion.version`),
và `paging.page_query` **từ chối** một statement không có `ORDER BY` — thà nổ còn
hơn trả về một trang chỉ đúng do may. Test `test_paging.py` seed 12 job **cố ý
bằng nhau ở mọi khoá** rồi đi hết 3 trang và đếm: 12 dòng, không lặp, không thiếu.
Verify thật trên 83 job qua browser: trang 1 và trang 2 giao nhau **0**.

**`total` phải đếm cùng bộ lọc với dòng.** Đếm trên cả bảng trong khi dòng thì đã
lọc ⇒ UI mời người dùng sang trang 4..9 rồi trả về trống. `total_for()` đếm bằng
subquery **của chính statement đã lọc**, không dựng lại `where` bằng tay — dựng
lại là cách `total` trôi khỏi thứ nó đếm khi ai đó thêm filter vào một chỗ mà quên
chỗ kia.

**Board Applications: bốn cột, bốn cửa sổ.** Trước đây trang này lấy *toàn bộ*
application rồi `filter()` trong browser, tức bốn cột **dùng chung một page size**.
Một chuỗi rejection sẽ chiếm hết cửa sổ và **đẩy offer ra khỏi response** — và một
cột "Offers" trống vì `limit` trông y hệt một cột "Offers" trống vì chưa ai mời
bạn. Giờ mỗi cột tự hỏi `?result=<stage>` với offset riêng, và số ở đầu cột là
**total thật của stage đó**. Một page-size cho cả board (dropdown ở góc), vì bốn
dropdown trong bốn cột hẹp là nhiều chrome hơn board.

**Bug thật mà phân trang *tạo ra*, và đã sửa cùng lúc:**
- `slack/events.py` tìm application của một job bằng `[a for a in
  client.applications() if a["job_id"] == job_id]` — quét cả board. Đang lãng phí,
  và **thành sai** ngay khi endpoint có page size: dòng nó cần có thể nằm ở trang
  2, bot báo "không có application" cho chính job vừa nộp. Thêm filter `job_id=`
  phía server + `client.application_for()`.
- `queue.active()` gọi `self.list(kind=...)` với `limit=50` mặc định. Nó là
  **guard** chống chạy hai crawl cùng lúc, không phải một danh sách để hiển thị —
  một task queued rơi khỏi cửa sổ sẽ đọc thành "không có gì đang chạy". Giờ
  `limit=None`. Trang Runs cũng hỏi riêng một request cho việc gate nút Crawl,
  không dùng trang đang xem.
- `/applications` **không hề có cap** trên `limit` (`limit: int = 200` trần, không
  `Query(le=...)`). Một list endpoint không chặn trên là DoS vào chính dashboard
  của mình. Giờ mọi endpoint dùng chung `MAX_PAGE_SIZE=200`, vượt là **422** chứ
  không phải một thành công chậm.

**Ba chỗ UI mà phân trang làm hỏng nếu không để ý:**
1. **Đổi filter mà giữ nguyên page.** Thu hẹp tìm kiếm từ 300 hit xuống 4 rồi vẫn
   đứng ở trang 7 = bảng trống, không manh mối. `usePaging.reset()` gọi khi
   *filter* đổi (không phải khi data refresh).
2. **List co lại dưới chân mình.** Một WS push hay một tab khác xoá dòng có thể
   cắt list ngắn hơn trang đang xem. `useClampPage` kéo về trang cuối hợp lệ —
   không có nó thì màn hình trống với nút "previous" vẫn chạy, về mặt kỹ thuật cứu
   được nhưng đọc như mất dữ liệu.
3. **Dropdown so sánh version trong CV Studio.** Nó liệt kê version để diff; nếu
   nuôi bằng *trang* đang tải thì không còn diff được v1 với v40. Version là
   append-only, đánh số 1..N **không có lỗ**, nên option dựng từ **dải số** chứ
   không từ dòng đã tải — chỉ nhãn "· agent" là cần dòng, và nó vắng mặt ở version
   ngoài trang, thứ chẳng mất gì vì bản diff tự nói ai viết.

**Nhớ *kích thước*, không nhớ *vị trí*.** `usePaging` lưu page size vào
localStorage theo từng list (`jobpilot-page-size:<name>`); `page` thì luôn về 0.
Bạn đang ở đâu trong một list là chuyện của một lần xem; bạn thích nhìn bao nhiêu
dòng một lúc là một preference. Per-list chứ không global: bảng Jobs muốn 100 còn
lịch sử Runs muốn 10. Giá trị đọc ra được **validate lại theo `PAGE_SIZES`** —
một giá trị cũ hoặc bị sửa tay sẽ đi thẳng vào query mà server trả 422.

**`/applications/{id}/events` cố ý KHÔNG phân trang.** Nó là lịch sử của *một* đơn,
dài bằng số lần bạn bấm nút, và một timeline 3 dòng có pager là chrome thuần tuý.
Đây là endpoint list duy nhất còn trả mảng trần — một sự thiếu nhất quán có chủ ý,
ghi ở đây để lần sau không ai "sửa" nó.

**Verify:** 690 test (10 test mới: `test_paging.py` + per-column board + Slack
`job_id`); `tsc` sạch. Chạy thật qua browser trên Postgres thật — Jobs 83 dòng đi
sang trang 2 giao **0**, đổi size về trang 1, size **sống qua reload**; Runs 18;
CV Studio 11 version. Board Applications trong DB thật đang **rỗng**, nên nó được
chụp bằng một **API + vite tạm trên SQLite scratch** (47 đơn: 7/14/23/3) rồi xoá
sạch: cột ≤ page size **không hiện pager**, "Submitted" đi hết 3 trang cho **23
card phân biệt, không lặp không thiếu**. Ảnh light + dark, console sạch.

**Bẫy môi trường (lần thứ hai trong ngày):** `--reload` "không ăn" vì lần restart
trước để lại một **worker mồ côi vẫn giữ cổng 8000** — Windows cho hai process
bind cùng một cổng, nên request rơi vào bản cũ. Dấu hiệu nhận ra: `curl` API trả
kết quả cũ trong khi `python -c` cùng module trả kết quả mới ⇒ nghi hai process,
đừng nghi cache.

- ✅ **Analytics thật** (`PLAN.md §9.1` ô 20) — `jobpilot/analytics/outcomes.py` +
  `GET /stats/outcomes` + khối "Where the answers come from" trên Deck. Trả lời đúng một câu
  hỏi: *tối nay crawl lại board nào?*

  **Số phase: cố ý không phát số nguyên mới.** `PHASES.md` đã mượn 20/20b/20c (model backend)
  và 21 (`/market`) cho việc khác với thứ §9.1 cấp cho các ô đó, nên phase này tham chiếu
  **theo ô §9.1**. Ô 21 (LLM ranking 2 tầng) vẫn chưa ai làm — đừng nhầm với `/market`.

  **Ngưỡng mẫu nằm trong split, không chỉ ở con số tổng.** `outcome_counts` chỉ chặn tỉ lệ khi
  mẫu số bằng 0 — đúng cho **một** con số toàn corpus. Nhưng cắt theo nguồn *chính là* thứ làm
  mẫu bé đi: 80 đơn chia 5 nguồn là 5 nhóm 16 đơn, và "1/3 = 33%" nằm cạnh một tỉ lệ thật thì
  trông cũng đáng tin y hệt. Nên `Bucket.reply_rate = None` khi `sent < MIN_SAMPLE`, UI in
  `n=3 · needs 8`. **Chọn bảng thay vì bar chart chính vì lý do này**: bar chart buộc mọi dòng
  phải có một cái cột, mà nửa số dòng ở đây *không được phép* có số — vẽ 0 thì đọc thành
  "nguồn này chẳng ai trả lời", bỏ dòng đi thì đọc thành "nguồn này không tồn tại".

  **Ngưỡng đang lệch nhau, chưa sửa:** `OutcomeRow` (Phase 18) hardcode `total_real >= 10`, còn
  `analytics/outcomes.MIN_SAMPLE = 8`. Hai ngưỡng "quá ít để tính tỉ lệ" trên **cùng một trang**.
  Không tự sửa vì đó là hành vi của phase khác; nợ này để user quyết.

  **Chưa hồi âm ≠ hồi âm chậm.** Đơn còn im lặng bị **loại khỏi** median và đếm riêng ở
  `still_waiting`. Gộp vào kiểu "đã N ngày" sẽ làm con số xấu đi mỗi ngày **không có gì xảy ra**.
  `submitted_at = NULL` là `undated`, không phải trả lời tức thì.

  **Tin đăng lại là *tín hiệu*, không phải phán quyết.** Gom theo `fold(company) + fold(title)`
  (cùng cách `inbox.fold`), ngưỡng 3 bài. Hai vị trí cùng tên ở một công ty là tuyển dụng bình
  thường — bằng chứng ở đây không phân biệt được với tin không ai lấp, nên module **không** dùng
  chữ "ghost", và có test ghim điều đó. `span_days = None` (không phải 0) khi dưới 2 bài có ngày.

  **Verify thật, và nó bắt được 3 thứ test không bắt:**
  1. **Mutation test trước đã.** 19/19 xanh ngay lần đầu là lúc đáng nghi nhất, nên phá logic
     có chủ đích: bỏ chặn `MIN_SAMPLE` → 2 test đỏ; gộp đơn chưa hồi âm vào median → 1 test đỏ;
     đếm theo kiểu `current` → 1 test đỏ. Đúng test dự định, không phải test khác.
  2. **DB nháp trên Postgres thật** (`jobpilot_acheck`, tạo → seed → đọc → drop; DB thật không
     đụng tới). Test chỉ chạy SQLite, mà SQLite trả datetime **naive** còn Postgres trả **aware**
     — nhánh Postgres của `_aware()` chưa từng chạy. Nó chạy sạch, và mọi con số khớp tay:
     đơn phỏng vấn-rồi-bị-từ-chối vẫn tính `interviewed`, nhóm 2 đơn vẫn `thin`, median 4.5.
  3. **`repeats: 0` trên 83 job thật là ĐÚNG, không phải detector chết.** Kiểm tra riêng: 83 job
     / 68 công ty, **không** cặp (company, title) nào trùng. Nhưng nghĩa là bộ dò **chưa từng
     chạy trên dữ liệu thật có tin lặp** — độ nhiễu tên công ty giữa các nguồn còn là ẩn số.

  **Bug có sẵn từ Phase 4 lộ ra khi chụp ảnh** (đã sửa, 1 dòng, commit riêng): `ApproachFunnel`
  chuẩn hoá mọi thanh theo `by_status.DISCOVERED`, coi đó luôn là đỉnh phễu. Nhưng `by_status`
  đếm theo trạng thái **hiện tại** — job đã nộp thì **rời khỏi** DISCOVERED. Với 24 submitted /
  4 discovered, `width = 24/4*100 = 600%`, thanh tràn khỏi card ra hết chiều ngang trang.
  **Phễu vỡ đúng lúc công cụ chạy tốt.** Giờ `top` lấy max trên mọi chặng.

  **Và một bẫy verify tự dính:** ảnh "dark mode" đầu tiên ra **light**. `add_init_script` đúng
  kỹ thuật như `web/src/CLAUDE.md` dặn, nhưng key là `jobpilot-theme` chứ không phải `theme`.
  Không mở ảnh ra nhìn thì đã báo cáo "đã verify dark" trên một tấm ảnh sáng trưng. Giờ script
  chụp **assert `document.documentElement.classList.contains('dark')`** trước khi chụp.

  **Review gate bắt được một bug tôi tự tạo:** `SplitTable` hardcode header cột đầu là "Source",
  nên bấm tab **Channel** thì bảng hiện `email`/`portal`/`external` dưới một cột ghi "Source" —
  số đúng, nhãn sai, tệ hơn cả hai. Header giờ đi theo tab (`DIMENSIONS`), và verify bằng cách
  **bấm thật từng tab** rồi assert `<th>` khớp — vì đây là bug của *tương tác*, ảnh tĩnh một
  trạng thái không bao giờ lộ ra.

  **Nợ "median âm" đã trả (vòng review thứ hai):** `occurred_at < submitted_at` (backdate tay,
  hoặc Phase 19 lấy timestamp mail lệch múi giờ) từng cho "-2.0 days, typically". Đã chọn
  **loại hẳn cặp đó** và đếm ở `timing.inconsistent`, **không kẹp về 0** — kẹp về 0 biến một
  header mail lệch giờ thành *câu trả lời nhanh nhất corpus*, tức là biến dữ liệu bẩn thành
  một kỷ lục trông rất đẹp. Cùng họ với `undated` và `still_waiting`: không tính được ≠ bằng 0.

  **Hai thứ nữa của vòng review thứ hai:**
  - `repeat_postings` lấy tên hiển thị từ `members[0]` mà query **không có `ORDER BY`** — cùng
    một group có thể ra "Công ty TNHH X" lần này, "CONG TY TNHH X" lần sau. Đã sort theo `job_id`
    trước khi chọn nhãn. Gom nhóm vốn đã đúng; chỉ cái **nhãn** là ngẫu nhiên.
  - Card "Ads that keep coming back" trước đây nấp sau `total_sent > 0`. Nhưng tin đăng lại là
    dữ kiện của **corpus crawl**, không phải của việc nộp đơn — nó đáng giá nhất với đúng người
    mà điều kiện cũ giấu nó đi: crawl nhiều, chưa nộp đơn nào (DB thật lúc kiểm: 83 job / 0 đơn,
    panel ẩn sạch). Giờ Deck hiện riêng card đó khi `repeats.total_groups > 0`.

  **Verify vòng hai:** dựng DB `jobpilot_demo` riêng (42 đơn hư cấu, 4 tin lặp viết 4 kiểu tên)
  rồi trỏ web sang API thứ hai — DB thật không đụng tới. Bảng suppress đúng (`n=5 · needs 8`),
  `covered 39/42` khi thiếu level, 4 cách viết tên gộp làm 1 group, light + dark sạch console.
  Chi tiết: `.env.local` **thắng** biến môi trường `VITE_API_BASE` của shell — lần chụp đầu ra
  đúng dữ liệu DB thật trong khi tưởng đang xem demo. Sửa file rồi restart Vite mới đổi được.


## Dedup của crawler — cửa sổ đo sai mốc (theo yêu cầu, không phải phase đánh số)

Bốn triệu chứng, một nguyên nhân. `_refresh()` không đụng `crawled_at` (đúng), nhưng preload
`seen_keys` lại lọc `WHERE crawled_at >= cutoff` — nên **cửa sổ dedup đếm từ lần ĐẦU thấy
job, không phải lần gần nhất**. Tin vẫn đang sống trên board rớt khỏi cửa sổ của chính mình ở
ngày 15, rồi bản của board khác chui vào thành row trùng.

**Vì sao không cắt scope còn "sửa đúng cửa sổ"** (đã cân nhắc thật, không phải làm cho đủ):
sửa mốc đo **một mình** làm suppression từ *hỏng 14 ngày* thành *hỏng vĩnh viễn*. Row nào còn
được crawl lại thì key của nó nóng mãi ⇒ bản LinkedIn `needs_jd` tới trước sẽ chặn bản ITviec
có JD đầy đủ **không giới hạn thời gian**, và Senior/Junior/Intern collapse thành mất im lặng
vĩnh viễn. Ship mục 1 một mình là ship một regression, nên mục 2–3 đi kèm chứ không tách phase.

- **`last_seen_at`** (migration 0010, backfill = `crawled_at`): bump mỗi `_refresh`. `crawled_at`
  **không được bump** — `/stats` `by_day`, `order=crawled`, `crawled_after` đều đọc nó. Migration
  cố ý đi 3 bước (nullable → UPDATE → NOT NULL): thêm thẳng NOT NULL sẽ nhét `now()` vào mọi row
  cũ và khai mọi job từng thấy là "thấy hôm nay" — đúng cái lỗi cột này sinh ra để chặn.
- **Level chỉ tách khi cả hai phía nói rõ.** Giữ nguyên ý định collapse (board bỏ chữ "Junior"
  không phải job khác), nhưng `title_level` đi cạnh `dedup_key`. Đọc **title thôi** — `infer_level`
  quét cả JD, mà một JD viết "we hire senior engineers" không được quyền quyết định hai tin là
  hai tin.
- **Trace thay cho im lặng**: `payload.dedup.suppressed` trên row sống sót (cap 10, **sống qua
  re-crawl** — `_refresh` ghi đè cả payload nên phải carry sang, không thì trace chỉ tồn tại tới
  lần crawl sau). Bản có JD thắng bản `needs_jd`; row cũ chỉ được **annotate**, không demote —
  nó có thể đã shortlist/apply rồi.
- **`dedup_days` vào `CrawlCfg` + `config.yaml`**; `run_crawl` đọc từ `cfg` (nó vốn đã nhận `cfg`)
  nên cả `orchestrator` lẫn `cli` có ngay, không phải sửa hai chỗ. `0` = tắt hẳn lớp 2, và phải
  tắt thật chứ không phải thu cửa sổ về 0 — row đụng trong **chính batch này** đóng dấu `now`
  nên vẫn che nhau.

**Một luật normalize, không phải ba.** `repeat_postings` gom theo `fold(company)+fold(title)`,
`dedup_key` thì strip level + parens ⇒ **hai luật viết tay đã lệch nhau**. Giờ cả hai gọi
`normalize_company` + `normalize_title(strip_level=)`, khác đúng một tham số. Trên corpus thật
88 job, luật cũ và luật mới cho **kết quả y hệt** (88 group cả hai) — hợp nhất không làm xê dịch
con số nào đang có, chỉ đóng chỗ nứt.

**Bug tự lộ ra khi viết test ghim** (không có test thì không ai thấy): `"Sr. Backend Engineer"`
normalize thành `sr. backend engineer` vì regex giữ dấu `.` cho `.net`/`node.js`. Dấu chấm
**cuối token** là dấu tắt: nó vừa làm `"Sr."` không nhận ra là level, vừa tách hẳn key khỏi
`"Senior Backend Engineer"` — tức là over-split có sẵn từ trước, nằm im trong một hàm ai cũng
tưởng chỉ strip level.

**Verify (không dừng ở test xanh):**
- 733 test pass (713 baseline + 20 mới).
- PostgreSQL 17 thật: `upgrade head` → backfill lệch **0/83 row**, `crawled_at` by_day y nguyên;
  `downgrade -1` → cột + index biến mất, 83 row còn nguyên; `upgrade` lại sạch.
- Replay A–E qua `persist_jobs` thật trong transaction rồi rollback (không đụng corpus): tin còn
  sống chặn được bản board khác ở **ngày 19** (`crawled_at` 08-17 vs `last_seen_at` 09-05); tin
  đã ngừng thấy thì hết chặn ở ngày 40; Senior/Junior/Intern ra **3 in / 2 dup**; ca LinkedIn ra
  `superseded=1` với `status` giữ nguyên `DISCOVERED`.
- Crawl thật 2 lần (8 nguồn): lần 1 `new=5 updated=7`, lần 2 **`new=0 updated=12`** — không row
  mới nào. `crawled_at` by_day giữ đúng 4 bucket cũ, `last_seen_at` mới là cột nhúc nhích.
- Trace trên dữ liệu thật đọc được ngay: Palantir đăng cùng một req dưới nhiều Lever id —
  suppression **đúng**, và giờ nói ra được nó bỏ cái nào.
- `GET /stats` `by_day` khớp DB từng bucket; `/stats/outcomes` `repeats` không đổi.

---

## Phase deploy — VPS Việt Nam + Tailscale, same-origin, CI/CD (2026-08-17)

**Đổi một quyết định đã chốt.** `CLAUDE.md` ghi "Chạy = local, tay hoặc cron nhẹ" và
"bind localhost, không expose ra ngoài". Lý do đổi: muốn dashboard 24/7 mà máy đang chạy là
**laptop** — thứ người ta mang đi, và mang đi thì JobPilot offline. Tinh thần cũ **vẫn giữ**:
Tailscale không phải public, uvicorn vẫn bind `127.0.0.1`, chỉ khác chỗ đặt máy.

Đã cân và **loại**: public + login thật (phải xây session auth + HTTPS + rate-limit, và phơi ra
Internet một service giữ CV + Gmail app password + LLM key — nhiều việc hơn hẳn, rủi ro cao hơn
hẳn, cùng một mức tiền). Đã cân và **loại**: Oracle Cloud free ARM — verify registry thấy
`csmith/awesome-cv-builder` là **manifest đơn, `arch=amd64`**, layer 1.45 GB nén (~3.5 GB đĩa);
chạy ARM phải tự build image TeXLive arm64 rồi verify lại font Awesome-CV.

### Prefix `/api` là bắt buộc, không phải thẩm mỹ

Định serve `web/dist` thẳng ở root, rồi phát hiện **route frontend trùng route API gần như
hoàn toàn**: `/jobs`, `/jobs/:id`, `/cv`, `/cv/:scope`, `/applications`, `/runs`, `/settings`,
`/models` là cả hai. F5 ở `/jobs` sẽ ra mảng JSON thay vì trang. Không có cách né: hoặc API
xuống `/api`, hoặc app xuống `/app`. Chọn `/api` vì đó là quy ước và vì 746 test soi được nó.

Blast radius đúng như dự đoán và **đo được**: 145 test đỏ ngay lần chạy đầu. Sửa bằng
`conftest.api_client()` đặt `base_url` — httpx nối path tương đối vào path của `base_url` nên
700+ assertion `client.get("/jobs")` không phải sửa chữ nào.

**Bẫy đã dính:** `TestClient.websocket_connect` **không** đọc `base_url` — Starlette hardcode
`urljoin("ws://testserver", url)`. Nên helper chỉ lo HTTP; test WS phải tự viết `/api/ws`.
Nếu không biết chuyện này thì triệu chứng là "WS test đỏ một cách vô lý" trong khi HTTP xanh hết.

Ba chỗ khác lộ ra vì cùng lý do: `/health` (thêm cả hai root), `slack/client.DEFAULT_BASE`
(thiếu `/api` là nhận HTML rồi chết ở `json.decode`, không phải 404 dễ đọc), và comment trong
`vite.config.ts` **nói dối** — nó ghi "proxy /api + /ws" mà trong file **không có block proxy
nào**. Giờ có thật, nên dev cũng same-origin như bản deploy.

### Token nằm trong bundle — ghi ra để không ai vô tình phơi nó

`VITE_API_TOKEN` bị Vite thay **tĩnh** lúc build; grep `web/dist/assets/*.js` là thấy token
nguyên vẹn. File tĩnh phải tải được *trước khi* kịp hỏi credential, mà chính nó chứa token ⇒
**ai mở được trang thì đọc được token**. Đây chính là lý do chọn Tailscale: tầng mạng là auth
thật, token chỉ chặn caller lạc cùng máy. Đã ghi vào `jobpilot/api/CLAUDE.md` + `DEPLOY.md §0`
kèm câu cấm rõ ràng: **không `tailscale funnel`, không bind `0.0.0.0`**.

Siết thêm (phòng thủ nhiều lớp, không thay Tailscale):
- Token 8 ký tự → **43 ký tự**. Ngưỡng tối thiểu 20 chọn có lý do: `llm/redact.py` có sàn
  **12 ký tự**, dưới đó token **không được scrub** khỏi log — token cũ rơi đúng vào lỗ đó.
- `hmac.compare_digest` thay `!=`, dùng chung một hàm cho cả REST lẫn WS để hai đường không lệch.
- Guard từ chối khởi động nếu token là placeholder/quá ngắn. Đặt ở **`lifespan`, không phải
  `create_app`**: build app cũng là việc test suite làm, checkout chưa có `.env` vẫn phải chạy
  được test — thứ nó không được phép làm là *lắng nghe*. Lỗi in ra kèm sẵn một token dùng được;
  guard chỉ biết nói không thì người ta đi vòng.
- **Token WS rời query string sang frame đầu tiên.** Query string nằm trong request line nên
  access log ghi thẳng ra đĩa. Có test ghim đường `?token=` cũ **không còn dùng được** — để nó
  chạy song song là vá mà vẫn rò. Socket `accept()` trước (không accept thì không đọc được
  frame) nhưng chỉ `subscribe()` sau khi auth xong, nếu không mọi `job_updated` chảy sang socket
  chưa chứng minh được nó là ai.

### 3 gate email khoá khỏi HTTP

`SettingsIn.apply` là `dict` tự do ⇒ một `PUT /settings` tắt được cả ba gate rồi bắt server gửi
mail thật. Đó là đường **ngắn nhất** từ "token rò" tới "máy nói thay mình". Giờ
`config.LOCKED_SETTINGS` chặn ở route, trả **403**.

Chi tiết quan trọng: **chỉ chặn khi giá trị đổi, không chặn khi chỉ có mặt.** Trang Settings lưu
nguyên cả section nên lần nào cũng gửi kèm ba field này; chặn cả no-op thì card không lưu nổi và
ai cũng học cách đi vòng. `GET /settings` trả thêm `locked` để UI render xám — switch bấm được
rồi mới báo lỗi lúc save dạy user rằng trang này không đáng tin.

### Bug Linux chỉ lộ ra vì đổi OS đích

`tailor/build.py` chạy `docker run` **không có `-u $UID:$GID`**, dù `README.md`/`CLAUDE.md` mang
sẵn cả hai câu lệnh — chỉ câu Windows từng được nối dây. Trên Docker Desktop không sao (dịch
ownership ở tầng mount); trên Linux container ghi `cv.pdf` bằng **root**, và build **lần sau**
chết ở `pdf.unlink()` với EACCES. Đúng kiểu bug của repo này: lần đầu xanh, lần hai mới hỏng.

### CI/CD

`ruff` + `pytest` + `tsc --noEmit` + `vite build`; deploy là **job cùng workflow** với
`needs: [backend, frontend]` nên không thể deploy code đỏ (workflow riêng thì phải bắc
`workflow_run`, và bắc sai thì hỏng im lặng). Runner join tailnet bằng
`tailscale/github-action` rồi ssh chạy `deploy/update.sh` — thay cho việc mở port 22 ra Internet.

`tsc` chạy tách khỏi `vite build` vì **Vite transpile mà không type-check**: build xanh không
chứng minh gì về types.

**Cố ý CHƯA bật `black --check`:** cây code chưa bao giờ được format bằng black ở
`line-length=100` — bật lên là đỏ **19 file** không ai đụng tới. Hai lối ra đều tệ: reformat cả
repo (chôn diff của review kế tiếp) hoặc một step ai cũng học cách bỏ qua. Reformat ở commit
riêng rồi mới bật. (`ruff` thì đã sạch — sửa luôn 1 lỗi `F401` có sẵn ở `ops.py`.)

`update.sh` build lại bundle **trên host** vì token bị nướng vào bundle; bundle build ở CI mang
token placeholder. Nó lấy `VITE_API_TOKEN` từ `JOBPILOT_API_TOKEN` trong `.env` để chỉ có **một**
chỗ ghi token — giữ thêm `web/.env.local` trên server là bản sao thứ hai chờ lệch, cho ra
dashboard 401 với chính backend của nó. Deploy xong **poll `/health`** rồi mới báo xanh:
`systemctl restart` trả về ngay khi process được spawn, nên nó "thành công" kể cả khi app chết
lúc startup — đúng thứ guard token làm khi `.env` sai.

### Rủi ro chưa verify được (nói thẳng)

**Crawl từ IP datacenter có thể bị Cloudflare chặn.** ITviec/TopCV/VietnamWorks đứng sau
Cloudflare; IP datacenter bị challenge nhiều hơn IP dân dụng. Không ai kiểm được trước khi thuê
máy thật. Chọn VPS **VN** để giảm rủi ro, và có đường lui rẻ: crawl chạy ở laptop, DB ở VPS, đổi
đúng một biến `DATABASE_URL` qua tailnet (`DEPLOY.md §7`). Nguồn feed (WeWorkRemotely, Arbeitnow)
và ATS (Greenhouse/Lever) **không** sau Cloudflare nên không ảnh hưởng.

**Verify đã làm:** 746 test pass (734 baseline + 12 mới), `ruff` sạch, `tsc --noEmit` sạch,
`vite build` ra bundle **không còn** `127.0.0.1:8000` hardcode.
**Verify CHƯA làm** (cần máy thật, xem checklist `DEPLOY.md §4`): chạy trên VPS, mở qua 4G,
build PDF hai lần liên tiếp trên Linux, tắt Tailscale để chắc URL chết.

---

## Phase deploy-2 — Chạy thật trên laptop Windows + trang Backup (2026-08-18)

**VPS không thành.** Oracle free tier ARM hết capacity ở `ap-singapore-1` — mà đó là AD *duy nhất*
của region, và home region thì **khoá vĩnh viễn**. Thử retry bằng Resource Manager stack: 4 lần
FAILED rồi đụng `429 TooManyRequests` của cả tenant.

Chốt lại: **chạy trên chính laptop**. Nó đã được set *không bao giờ ngủ* nên gần như là server 24/7
sẵn; và crawl từ **IP dân dụng VN** là thứ không VPS nào mua được — đúng thứ Cloudflare khó chịu
nhất với IP datacenter. Oracle chỉ còn thêm được **một ô**: dashboard sống khi laptop tắt. Đánh đổi
không đáng, đã dừng săn.

### Tailscale — hai chỗ mất thời gian

- **`tailscale serve` treo im, không báo gì** khi tailnet chưa bật HTTPS. Dấu hiệu duy nhất:
  `tailscale status --json` → `CertDomains: None`. Bật ở admin console → *Audience* (giao diện mới
  đổi tên thành **Google Auth Platform**-style, nút publish không còn ở màn hình consent cũ).
  Chẩn đoán được là nhờ thử `serve --http=80` — chạy ngay lập tức, nên biết vấn đề là **cert**
  chứ không phải serve.
- **`cmd.exe` không expand `~`.** `ssh-keygen -f ~/.ssh/x` báo `No such file or directory` mà không
  hề nói lý do. Dùng `%USERPROFILE%`.

### Task Scheduler — ba vòng mới đúng, và bài học đắt nhất phiên

**Vòng 1: `pythonw` trực tiếp → task chết với đúng `0x1`, không log.** Nghi phạm đầu tiên
(`pythonw`, `--workers 1`) **đều vô tội** — cả ba biến thể chạy ngon từ shell. Tái hiện bằng
`Start-Process -UseNewEnvironment` mới ra nguyên nhân thật: `import asyncio` chết trong Winsock
(`WinError 10106`) vì thiếu `%SystemRoot%`. Thông báo không nhắc tới Python lẫn biến thiếu.
⇒ Bọc `.cmd`: vừa chuẩn hoá env, vừa **ghi log** — thứ thiếu nghiêm trọng hơn cả bug.

**Vòng 2: `hidden.vbs` không chờ.** `shell.Run(cmd, 0, False)` khiến task "xong" tức thì. Ba thứ
âm thầm không hoạt động: `RestartCount` không bao giờ kích hoạt (API chết là nằm chết, dù setting
nói ngược lại), `Stop-ScheduledTask` không có gì để dừng, và task backup báo `0x0` kể cả khi hỏng.

**Vòng 3: thử S4U rồi phải quay lại.** S4U cho "chạy nền, không cửa sổ, không lưu mật khẩu" —
và làm server **không quản lý được**: nó ở logon session khác nên `taskkill` trả *Access is denied*,
còn `Get-CimInstance` trả `CommandLine` **rỗng**. Hệ quả: mọi phép đếm process khớp 0 và báo
"không có server nào chạy" trong khi nó đang phục vụ.

> **Bài học lớn nhất:** `Stop-ScheduledTask` giết lớp vỏ và **bỏ lại `python` mồ côi giữ cổng**.
> Lệnh `Start` kế tiếp không bind được rồi chết — nhìn bên ngoài **y hệt một lần restart thành công**.
> Vì thế tôi đã **hai lần "verify" deploy trên chính code cũ**. Chỉ lộ ra khi kiểm *response có
> field mới không* thay vì tin "task chạy + health OK".
> ⇒ `deploy/windows/restart-api.ps1`: dừng theo **chủ sở hữu cổng** (không theo tên tiến trình hay
> command line — cả hai đều nói dối ở đây), chờ cổng giải phóng thật, rồi poll `/health`.

### Backup — một implementation, ba lối vào

Luật backup từng nằm trong PowerShell, nên dashboard chỉ có hai đường: gọi `.ps1` (Linux vô dụng)
hoặc đẻ bản sao thứ hai. **Bản sao luật backup thì thứ trôi trước tiên là phần *verify*** — nên ngày
phát hiện đúng là ngày cần tới nó. Giờ tất cả nằm ở `jobpilot/backup.py`; CLI, scheduled task và
nút bấm cùng gọi vào đó.

**rclone chứ không phải thư mục sync**: thư mục sync đẩy lệnh dọn local lên cloud trong vài giây,
biến bản remote thành *bản sao lỗi lầm của máy này* thay vì bản sao độc lập của dữ liệu. Local giữ
30 ngày, remote 90 — **cố ý khác nhau**.

Ba lỗi của bản đầu, đều tìm ra khi **dùng thật**:
- **Retention chỉ theo ngày.** Bấm nút 5 lần một buổi chiều = 10 file đều trong cửa sổ 30 ngày ⇒
  không xoá gì. Đo trên bản sao thư mục thật: theo ngày xoá **0/14**, thêm `keep_last=3` xoá **8**.
  Đếm **riêng từng loại**, để một lần chạy hỏng nửa chừng (có dump, không có CV) không đẩy file
  loại kia ra ngoài.
- **Không có lịch sử.** Task bị evict sau 50 cái, nên không trả lời được câu duy nhất ai cũng hỏi:
  *"đêm qua nó có chạy không?"*. Quan trọng nhất ở ca file **không** nói được: một lần chạy hỏng
  **trước khi kịp ghi file** không để lại dấu vết, nhìn y hệt lần chưa từng khởi động.
- **Restart chưa bao giờ hoạt động** (ở trên).

### Review gate bắt được 2 lỗi nữa

- **Mật khẩu DB rò khi `pg_dump` timeout.** `subprocess.TimeoutExpired` lưu toàn bộ argv và render
  nó trong `str()` ⇒ DSN kèm mật khẩu chảy vào `Run.stats["error"]` → **lưu xuống DB** → **hiện lên
  dashboard**. Tôi đã viết hẳn comment cẩn thận cho nhánh `returncode != 0` rồi **bỏ sót nhánh
  timeout**. Chi tiết đắt: `raise ... from None` **chỉ ẩn cách hiển thị**, `__context__` vẫn trỏ tới
  exception gốc nên traceback vẫn render mật khẩu — phải `raise` **ngoài** khối `except`. Chính test
  ghim mới lôi ra chuyện này sau khi tưởng đã sửa xong.
- **Scheduled task không ghi Run row.** `run-backup.cmd` gọi CLI → `run_backup()`, mà chỉ
  `backup_body()` mới ghi Run. ⇒ "Recent runs" **luôn trống** sau backup đêm, trong khi dòng chữ
  trên trang khẳng định *"trống nghĩa là job không chạy"*. **Một tính năng giám sát báo ngược sự
  thật còn tệ hơn không có.**

**Verify (chạy thật, không dừng ở test xanh):** 770 test pass; backup chạy từ **cả ba đường**
(CLI, nút bấm, lịch) và `rclone lsl` xác nhận file trên Drive **byte-identical** với local; restore
dump vào DB nháp ra đúng `jobs=88`, `cv_versions=12` rồi xoá; dashboard/deep-link/token/WebSocket
đều qua URL Tailscale; và **tắt Tailscale trên điện thoại thì URL chết** — bài kiểm duy nhất chứng
minh mô hình bảo mật đúng.

**Luồng thật lần đầu:** tailor job Panasonic → **`attempts: 2`** (guardrail **loại kế hoạch đầu**,
bắt làm lại) → PDF 1 trang, `pdfminer` đọc được 2733 ký tự. Hai kỹ năng JD đòi mà CV không có
(`CBOR`, chữ ký số) được đánh `MISSING` với `evidence` rỗng, và grep chính text PDF xác nhận
**không xuất hiện** — match 0.79 chứ không phải 1.0 vì nó không tự nâng điểm bằng cách bịa.
Dừng ở **REVIEW**: bấm Approve là quyết định của user (nguyên tắc 2), không bấm hộ.

**Nợ mới:** parser LinkedIn alert ăn nhầm dòng *"Jobs similar to …"* thành job — 2/88 row có title
và company rác, làm bẩn analytics (`crawler/mailbox.py`).

**Giới hạn còn lại của qualifier (reviewer nêu, cố ý chưa làm):** vendor nhiều chữ như
`Red Hat` không xử lý được bằng set token — tách ra thì `Hat` sẽ bảo lãnh mọi thứ đứng sau nó.
Nên CV có `OpenShift` mà thư viết `Red Hat OpenShift` vẫn bị chặn, đúng loại false positive mà
bản vá này sửa cho `Apache Kafka`. Muốn làm phải match theo **cụm**, không phải theo token —
để lại backlog thay vì nới bằng cách dễ, vì mỗi lần nới guardrail này là một lần mở đường cho
lời khai man tới nhà tuyển dụng.

## Phase cv-A — Template thứ hai (`plain`) + chỗ chọn template trong Studio (2026-08-19)

Việc A trong loạt 3 việc nâng cấp CV. Backend đã sẵn sàng từ Phase 4.5 (`doc.template`,
`template_env()` đọc theo tên thư mục, `GET /cv/templates` đã tồn tại) — thiếu đúng hai thứ:
một template thứ hai, và chỗ chọn nó.

### `plain` là template khác *mục đích*, không phải khác màu

Bỏ hẳn `awesome-cv.cls`, dựng trên `article` + `geometry`/`fontspec`/`enumitem`/`titlesec`/
`hyperref`/`microtype`. Lý do tồn tại: **portal ATS nuốt PDF nhiều cột / nhiều icon rất tệ**,
mà Phase 13 (`cv/ats.py`) đã đo được "máy có đọc được không" — giờ mới có bản để chọn khi câu
trả lời là không. Verify bằng cách **đọc lại text layer**, không phải nhìn PDF: thứ tự đọc
đúng, tiếng Việt nguyên vẹn (`Phạm Đăng Khôi`), và escape LaTeX round-trip (`100%`, `50_50`,
`#hash`, `&`).

### Manifest: thêm template = thêm một thư mục, vẫn đúng sau khi có assets riêng

`ASSETS` trước đây là hằng module-level, copy cứng `awesome-cv.cls` + `fontawesome.sty` +
`fonts` cho **mọi** build. `plain` không cần `.cls`. Nếu để một dict trong Python thì "thêm
template" hoá ra là "thêm thư mục **và** sửa Python" — nên mỗi template tự khai trong
`template.json` (`name`/`description`/`assets`), `list_templates()` đọc manifest. Manifest
thiếu `assets` → fallback về bộ cũ, tức thư mục thả vào không manifest chạy y như trước.

`GET /cv/templates` đổi từ `list[str]` sang `[{id,name,description}]`. Đổi được vì nó có
**0 consumer** — endpoint tồn tại từ Phase 4.5 mà chưa ai gọi. Picker cần *lý do để chọn*,
không phải chỉ một id.

### Bốn cái bẫy — ba trong số đó là công cụ đo tự bịa ra lỗi

1. **Heredoc Bash ăn mất backslash**: `\\[2pt]` tới LaTeX thành `\[2pt]` → "Bad math
   environment delimiter". Đi debug LaTeX 2 vòng trong khi **LaTeX chưa bao giờ sai**. Cùng
   họ với bài `pypdf` ở Phase 13. Từ đó viết file template bằng Write tool.
2. **Git Bash đổi `/query` thành `C:/Program Files/Git/query`** khi gọi `docker run` và
   `schtasks` → lỗi trông như "docker hỏng"/"tham số sai". Cần `MSYS_NO_PATHCONV=1`.
3. **`\begin{itemize}\end{itemize}` là lỗi LaTeX cứng.** `cvitems` của `awesome-cv.cls` dễ
   tính nên chưa bao giờ lộ; `enumitem` thì chết. Mà **DB mới seed CV rỗng** (rule 3) ⇒ đây là
   thứ user mới gặp *đầu tiên*. Đã build thật cả CV rỗng lẫn entry chỉ có title để chứng minh,
   vì test render chỉ chứng minh chuỗi `.tex`, không chứng minh LaTeX chịu nhận.
4. **Bản `plain` đầu tiên tốn 2 trang** cho đúng nội dung `awesome_cv` gói trong 1. "Plain" mà
   dài hơn thì là CV tệ hơn chứ không phải mộc hơn — siết spacing tới khi về 1 trang.

### API chết giữa lúc verify — và nó **không** phải lỗi của phase này

Sau khi restart, server phục vụ được `/api/cv/templates` (200 ×2) rồi **exited rc=3** đúng lúc
`GET /api/cv/master` đang bay. Không có traceback nào trong `logs/api.log`. Event log Windows
mới nói ra: **`python.exe` fault trong `libintl-9.dll` của `C:\Program Files\PostgreSQL\17\bin`,
exception `0x40000015` (fatal app exit)** — crash tầng native trong DLL client của Postgres,
không dính gì tới Jinja/React. Bằng chứng ngược lại: cùng commit, cùng DB, chạy uvicorn tay ở
:8001 thì trang CV Studio load sạch, mọi request 200, server sống. **Chỉ 1 crash python.exe
trong 21 ngày** nên chưa kết luận được là kinh niên hay một lần — ghi lại đây để lần sau thấy
`rc=3` thì đi thẳng tới Event log thay vì đọc `api.log` (nơi hard-crash **không** để lại gì).

**Verify (chạy thật):** 807 test pass; build Docker thật cho `plain` và `awesome_cv` — CV mẫu
1 trang cả hai, cover letter 1 trang cả hai; build dir của `plain` **chỉ có `fonts`**, không
có `.cls`/`fontawesome.sty` (chứng minh assets theo template); CV rỗng + entry thiếu bullet
build được; `GET /api/cv/templates` trả đúng 2 template trên server thật; picker đổi được lựa
chọn trong UI thật và ô "Accent colour" mờ đi kèm chữ *"not used by the plain template"*.
**Không Save** — Master CV thật giữ nguyên v12.

**Quyết định để lại (cv-A):** `plain` dùng Roboto trong `fonts/` qua `fontspec` chứ không dùng font
mặc định của TeX, vì font mặc định thiếu glyph tiếng Việt và chỗ thiếu là **khoảng trắng im
lặng** trong PDF, không phải lỗi build.

## Phase cv-B — Sửa Master CV bằng câu lệnh + guardrail provenance (2026-08-19)

Việc B. Đường instruction đã có nhưng chỉ cho CV tailored theo job; Master CV thì chưa.
Phần khó **không phải** là nối dây, mà là guardrail: nó đang đối chiếu với chính Master CV,
nên áp nguyên vào đây thì **chặn mọi dữ kiện mới**, kể cả dữ kiện thật.

### Đảo ngược câu hỏi, không nới guardrail

Tailor hỏi *"cái này đã có trên CV chưa?"* — đúng, vì lúc tailor thì Master CV **là** toàn bộ
sự thật. Edit hỏi *"dữ kiện này có phải do user nói không?"* — vì đây chính là chỗ sự thật mới
được phép đi vào. Cùng một nguyên tắc 1, hai câu hỏi khác nhau, và **chủ sở hữu sự thật khác
nhau**: user không tự nói dối với chính mình, rủi ro là **model chèn thứ user không nói**.

Cơ chế: **instruction là giấy phép, `source_quote` là trích dẫn**. Op thêm mới bắt buộc có
quote và quote phải xuất hiện thật trong instruction — dùng lại đúng cơ chế `quote` của inbox
sync (Phase 19), gom về `jobpilot/textnorm.py` để **một normaliser, hai bên dùng chung** thay
vì hai bản sẽ lệch.

Bản đầu cấp phép *chỉ theo nội dung quote*: **sai trong thực tế**. Dữ kiện của một entry nằm
rải khắp câu, nên quote vào mệnh đề "a crawler built with FastAPI" làm chính **tên project** bị
từ chối. Sửa: quote là *chứng từ* (bắt buộc có thật, để người đọc diff kiểm được), còn *lời
user nói chung* mới là nguồn cấp phép. Vẫn chặn nguyên vẹn mọi ca nguy hiểm.

### Lỗ hổng metric — thứ guard cũ không thể nhìn thấy

Đo chứ không đoán, trên `unknown_terms` hiện có:

| Câu thêm vào CV | Guard cũ |
|---|---|
| "Also experienced with Kafka and **Terraform**." | 🛑 chặn |
| "Increased throughput by **40%**." | ✅ **lọt** |
| "**Led a team of 12 engineers**." | ✅ **lọt** |
| "Built an engine handling **millions of orders**." | ✅ **lọt** |

`_TOKEN_RE` bắt buộc token bắt đầu bằng **chữ cái** ⇒ `40%` không hề được tokenize; văn xuôi
thường không bao giờ "trông như công nghệ". Ở tailor thì chịu được (schema không cho viết câu
đó). Ở đây model **có** viết văn xuôi ⇒ phải kiểm chữ số riêng, đối chiếu cùng hai nguồn.

### `400 Schema is too complex` — bài học đắt nhất phiên, và test xanh không thấy gì

831 test xanh với `FixtureEditEngine`; gọi thật thì Anthropic **từ chối schema**. Bisect bằng
API thật (chi tiết + số liệu ở `jobpilot/llm/CLAUDE.md`): thủ phạm **không phải kích thước** mà
là **field optional** — `TailorPlan` 4682 byte PASS, schema mới 3153 byte FAIL, tách nhỏ 3291
byte vẫn FAIL, **bỏ hết default → 3260 byte PASS**. Field có default nở thành nhánh
`anyOf`/nullable và làm vỡ ngân sách dù schema đọc rất nhỏ.

Trớ trêu: tôi chọn "một model phẳng, tránh union" *vì* sợ khác biệt giữa provider — và chính
cái phẳng đó là hình dạng bị từ chối. Thiết kế đúng hoá ra cũng là thiết kế an toàn hơn: **mỗi
loại op một list riêng** (`rewrites`/`merges`/`drops`/`new_bullets`/`new_entries`), object nhỏ,
mọi field required. Một `drop` giờ **không thể** mang `title` — sai không biểu diễn được, đúng
tinh thần "đổi sang cấu trúc thay vì thuyết phục model".

### Chạy thật với model thật (2 ca, cả hai vòng đầu)

- **Có chi tiết** → `attempts=1`, guard PASS, quote đúng nguyên văn, `tech_stack` tách đúng.
- **"Add my Kafka project."** (mơ hồ) → model thêm **0 op**, ghi vào `note` rằng thiếu tên,
  thời gian, vai trò, công nghệ. **Không bịa gì** — và không cần tới vòng retry, vì prompt làm
  cho việc từ chối là nước đi tự nhiên.

### Sự cố: test ghi vào DB THẬT

`test_cv_edit_api` bản đầu thiếu fixture `worker_db`. Task body mở session riêng bằng
`session_scope()` nên override `get_db` **không tới nó** ⇒ nó ghi thẳng vào Postgres thật:
**v13 của Master CV là một project "JobPilot" bịa**, do tôi tạo ra. Task vẫn báo **done**.
Hỏng *im lặng*, và chỉ lộ ra vì assert sau đó đọc lại thấy tài liệu không đổi.

Tệ hơn: lần chạy model thật sau đó, chính model **nhìn thấy** entry rác đó và nhắc trong
`note` — tức là nó đã bắt đầu ảnh hưởng hành vi. Đây đúng là rủi ro "rửa lời khai" mà docstring
của chính tính năng này cảnh báo. **v13 vẫn đang nằm đó** (lệnh xoá bị permission chặn) — xem
mục treo ở cuối.

### Bug nguy hiểm nhất phase, chỉ lộ ra lúc verify UI: diff MÙ với nội dung THÊM VÀO

`tailor/diff.py` báo `dropped` và `reordered` nhưng **không hề báo `added`** — vì caller duy
nhất của nó (tailor) không bao giờ thêm được gì. Thêm 1 entry vào `projects` (3→4) mà
`diff.changed == False`. Nghiêm trọng ở chỗ **diff chính là thứ user duyệt**: cả lập luận
"guard chỉ là lexical nên diff bắt buộc là lớp đỡ" sụp đổ nếu diff không hiện thứ vừa thêm —
user sẽ chấp nhận một entry họ chưa từng nhìn thấy.

Lộ ra vì test happy-path **hỏng** ngay sau khi tôi thêm bước "không đổi gì thì không ghi
version", mà bước đó ban đầu hỏi `diff.changed`. Sửa: `_order_note` báo cả `added`, thêm status
`expanded` (nhãn "Added", màu accent để không lướt qua được), và câu hỏi "có đổi gì không"
chuyển sang **so tài liệu** (`documents_differ`) chứ không hỏi diff — diff là *tóm tắt cho
người*, mà tóm tắt được phép bỏ sót.

**Bài học chung:** một hàm dùng chung *an toàn vì caller cũ không làm được điều đó* thành lỗ
hổng ngay khi có caller mới. Sửa ở hàm chung, không viết bản thứ hai.

### Vòng không đổi gì thì không ghi version

Model từ chối làm (instruction mơ hồ) là vòng **thành công** — từ chối là câu trả lời đúng.
Ghi một version giống hệt bản trước là xếp câu trả lời đó vào loại "đã sửa CV", làm lịch sử
đầy row diff rỗng. UI phải **nói ra** ("Nothing changed — no new version"), nếu không nút bấm
trông như không làm gì.

**Verify (chạy thật, đọc output):** 836 test pass; guard chấm bằng 9 ca đối chứng (add hợp lệ /
thiếu quote / quote diễn giải lại / quote thật nhưng thêm tech lạ / bịa metric / rewrite bịa
40% / rewrite có số do user đưa / merge / rewrite từ nội dung master) + ca 2 op tranh cùng 1
bullet; gọi model thật 2 ca; **UI thật trên trình duyệt**: gõ "Add my Kafka project." → model
trả 0 op, UI hiện "Nothing changed — no new version" kèm `note` giải thích thiếu gì, DB xác
nhận **vẫn v15, không ghi version nào**, Run row đóng đúng với `no_op: True`. Master CV thật
không bị đụng vào trong toàn bộ quá trình verify.

### Review gate (`phase-reviewer`) — CHANGES REQUESTED, hai lần lộ

Review độc lập trên diff bắt được 2 blocker và 4 mục nên sửa, cả hai blocker đều là loại lỗi
*trông như đúng* mà nguyên tắc xuyên suốt ở đầu file này đã cảnh báo:

- **`edit_master` âm thầm xoá `tex_override`.** `put_cv` và `rollback` đều mang override theo
  khi ghi version mới; `edit_master` thì không — verify được bằng `FixtureEditEngine`: override
  `True` trước, `False` sau một câu lệnh sửa hoàn toàn không liên quan tới LaTeX. Sửa: mang
  override theo giống hệt `put_cv`, comment nói rõ nó vẫn một chiều (đã ghi ở "Nợ kỹ thuật").
- **Diff của entry mới chỉ có tên, không có nội dung.** Sửa `b09940f` mới đóng được nửa lỗ hổng
  "diff mù với nội dung thêm vào" — `_diff_section` báo được *rằng* có entry mới, nhưng khi
  `original is None` thì `continue` thẳng, bullets/tech_stack của entry đó không bao giờ vào
  `notes`. Đúng chỗ nội dung bịa sẽ nằm nếu guard lexical bỏ sót. Sửa: liệt kê bullets/tech stack
  của entry mới vào notes thay vì bỏ qua.

Bốn mục nên sửa, không chặn nhưng cùng một tinh thần "đo chứ đừng đoán":

- `_check_conflicts` không phủ được `ParagraphSection` — hai rewrite cùng `summary` với
  `entry_index`/`item_index` khác nhau (0 vs -1) không bị coi là tranh chấp, dù `apply_edits` áp
  paragraph rewrite theo `section_key` alone nên bản sau đè bản trước im lặng. Sửa: slot của
  paragraph rewrite chuẩn hoá về `(key, NA, NA)` bất kể model điền gì vào hai field không dùng
  tới.
- Số viết bằng chữ ("twelve", "millions", "half"...) đi vòng qua `_digits` vì regex chỉ bắt chữ
  số. Thêm `_NUMBER_WORDS` — có chủ đích **bỏ qua one..ten** vì chúng là từ đệm quá phổ biến
  trong văn xuôi thường ("one of the two"), thêm vào sẽ tạo false positive tốn hơn cái nó bắt
  được.
- Badge `trimmed` che mất `expanded` khi một section vừa thêm vừa xoá trong cùng một plan — đổi
  thứ tự ưu tiên: `expanded` thắng, vì đó là chỗ rủi ro thật nằm.
- Dán nguyên một JD vào ô instruction cấp phép cho *toàn bộ* danh sách công nghệ trong đó, vì
  giấy phép là cả instruction chứ không phải riêng quote (quyết định có chủ đích, xem "Đảo ngược
  câu hỏi" phía trên). Đây **không** phải bug thực thi — là hệ quả đúng của thiết kế đã chọn.
  Không sửa code (sửa sai sẽ tái phát lỗi quote-vào-sai-mệnh-đề mà thiết kế này đang né), chỉ
  sửa lại câu tuyên bố cho khớp thực tế ở `jobpilot/cv/CLAUDE.md` và ghi rõ vào `TESTCASES.html`
  (`TC-045-13`) rằng đây là giới hạn đã biết, chưa đóng.

Cũng nhân dịp này đóng luôn class lỗi đã gây ra sự cố "ghi vào DB THẬT" ở trên, thay vì chỉ vá
call site đó: thêm fixture `autouse` `_forbid_unrouted_sessions` patch `get_sessionmaker` thành
hàm luôn `raise`; `worker_db` patch lại **sau** nó nên test nào request `worker_db` vẫn chạy
bình thường, còn test nào quên thì lỗi ngay tại chỗ thay vì âm thầm ghi vào `DATABASE_URL`. Chạy
lại toàn bộ suite sau khi thêm guard này để chắc không có test nào đang ngầm dựa vào đường không
được route — không có, 836/836 vẫn xanh.

**Verify vòng 2:** 4 test mới (nội dung entry mới trong diff, `expanded` thắng `trimmed`, xung
đột paragraph rewrite, `tex_override` sống sót qua một edit) + 836 cũ = **840 pass**, `ruff` và
`tsc --noEmit` sạch.

### Review gate vòng 3 — regression thật trong lúc sửa finding của vòng 2

Review lại sau vòng 2 bắt được **blocker mới do chính bản vá vòng 2 gây ra**, cộng 4 mục nhỏ
chưa chặt:

- **`dirtyRef` chặn nhầm cả đường Restore.** Bản vá vòng 2 gắn guard `dirtyRef` vào effect
  "adopt server document" — effect đó phục vụ ba việc (nạp lần đầu, refetch sau save, refetch
  sau edit-task), guard chỉ nên áp cho việc thứ ba. Kết quả: user đang sửa dở (`dirty=true`) mà
  bấm **Restore** — `rollback()` gọi API thật, version tăng, History mọc row mới, nhưng editor
  **không đổi gì** vì effect thấy `dirtyRef.current` rồi bỏ qua. Y hệt lớp lỗi "im lặng bỏ qua
  thứ user vừa yêu cầu" mà chính nguyên tắc 1 cảnh báo — chỉ khác là lần này nạn nhân là thao
  tác Restore chứ không phải nội dung CV. Sửa: bỏ guard khỏi effect chung (nạp lần đầu / save /
  rollback / đổi scope đều phải adopt vô điều kiện — đó là lúc user tự yêu cầu), chuyển
  `dirtyRef` sang đúng một chỗ cần nó — effect edit-task-landing — và khi bị chặn ở đó thì
  **không** im lặng: giữ lại version bị bỏ qua trong state, hiện banner "agent đã lưu vN, bấm
  Load để nạp (mất draft) hoặc Save để ghi đè lên trên", diff panel vẫn mở bình thường vì nó đọc
  từ `cvDiff` API, không đọc từ `draft`.
- Test cho "expanded thắng trimmed" drop nhầm section (`skills`) trong khi add vào `projects`
  nên không ghim được ca nó tuyên bố sửa — sửa test để drop và add cùng rơi vào `projects`, kèm
  assert có mặt note "dropped bullets" để chắc ca đang test đúng là ca tranh chấp thật.
  Bài học lặp lại đúng thứ ở nguyên tắc xuyên suốt đầu file: **test xanh không chứng minh gì**
  nếu test không thật sự đi qua nhánh nó tuyên bố kiểm.
- `_NUMBER_WORDS` hụt dạng động từ quá khứ ("doubled", "halved", "tripled", "quadrupled") — mục
  đích khai báo là "bắt số viết bằng chữ né `_digits`" mà đường né tự nhiên nhất trên một CV
  ("Doubled request throughput.") vẫn lọt. Thêm 4 dạng đó vào set, kèm test ghim cả ca chặn được
  lẫn ca cố tình bỏ qua (`one`..`ten`, để quyết định "loại trừ từ đệm phổ biến" đọc như một lựa
  chọn có chủ đích, không phải một khoảng trống).
- `TC-045-13` khai `pin:'test_cv_edit.py'` cho cả hai ca nhưng ca 2 (dán JD → PASS theo thiết
  kế) chưa có test nào ghim — với một giới hạn **cố ý giữ**, characterization test là thứ duy
  nhất chặn nó đổi hành vi âm thầm khi có ai sửa `_check_text` sau này. Thêm
  `test_a_pasted_jd_licenses_every_technology_it_names`.
- Docstring của `_forbid_unrouted_sessions` khai "No test may reach `DATABASE_URL`" nhưng chỉ
  patch `jobpilot.store.db.get_sessionmaker` — `jobpilot/api/deps.py` import hàm đó **bằng
  tên** lúc module load (`from jobpilot.store.db import get_sessionmaker`) nên patch không tới
  được đường request thật. Không lộ vì mọi test hiện tại đều tự override `get_db` qua
  `dependency_overrides`, nhưng câu tuyên bố cần khớp thực tế — patch thêm
  `jobpilot.api.deps.get_sessionmaker` để đóng nốt lớp phòng thủ đó, phòng khi có test sau này
  quên override.

**Bài học vòng này:** sửa một finding bằng cách thêm guard rộng thì rất dễ mở ra một lỗ mới ở
chính chỗ khác — "diff mù với nội dung thêm" (vòng 1) và "Restore bị `dirtyRef` chặn nhầm"
(vòng 2) là cùng một hình dạng lỗi: một effect/hàm dùng chung phục vụ nhiều mục đích, sửa cho
một mục đích mà quên các mục đích còn lại. Review độc lập trên diff thật — không phải đọc lại
chính code mình vừa viết — là thứ bắt được cả hai lần.

**Verify vòng 3:** 8 test mới (2 word-number, 1 pin cho JD-paste, 1 sửa lại test expanded-vs-
trimmed cho đúng ca, 4 test cho vòng trước vẫn còn) + 836 gốc = **844 pass**, `ruff` và
`tsc --noEmit` sạch. Chưa mở uvicorn + browser thật để xác nhận banner "Load vN" — để lại cho
lúc verify UI trước khi merge.

### Verify UI thật (vite dev + API/Postgres thật) — và vì sao KHÔNG bấm Restore

Mở CV Studio thật trên Master CV production (v16, dữ liệu thật của user). Sửa một field, xác
nhận "unsaved changes" + nút Save bật đúng sau khi refactor `dirtyRef` — verify được phần an
toàn. **Cố ý không** bấm Restore hay chạy edit-task thật lên Master CV production để verify
regression vòng 2: đó là ghi một version thật vào DB thật chỉ để thử, đúng loại việc mà sự cố
"ghi vào DB THẬT" ở trên đã cảnh báo — không lặp lại cùng một lỗi để verify bản vá cho chính lỗi
đó. Phần còn lại verify bằng đọc code + suy luận qua từng effect, ghi rõ là chưa chạy tay.

### Review gate vòng 4 — banner tự nhận "đã lưu" cho một round KHÔNG lưu gì

Review lại bắt được blocker thật ngay trong phần chưa verify tay ở trên: effect edit-landing
gọi `setEditSkippedVersion(version)` chỉ dựa vào `dirtyRef.current`, không hỏi round đó có thật
sự ghi version hay không. Nhánh no-op của `edit_master` trả `version` = version **hiện tại**
(không phải version mới, vì không có version mới), nên `Number(version) || 0` vẫn ra số dương
bình thường. Kịch bản hỏng: user đang dirty, gõ "Add my Kafka project." → guard từ chối đúng
thiết kế, 0 version mới ghi — nhưng banner vẫn hiện "The agent saved vN" + nút "Load vN", và
bấm vào thì `refetch()` nạp lại đúng document cũ, xoá sạch sửa đổi chưa lưu của user để đổi lấy
**không có gì**. Sửa: gate cả nhánh `refetch()` lẫn nhánh `setEditSkippedVersion` bằng
`editTask.result?.changed !== false && version > editBase.current` — cùng điều kiện `changed`
mà `InstructionBox.tsx` đã dùng để tự nó không hiện "Nothing changed" và banner mâu thuẫn nhau
cùng lúc.

Hai mục nên sửa cùng lượt, cùng gốc "sửa nửa đường":

- **Nút "Load vN" gọi `refetch()` = HEAD, không phải vN.** Vô hại lúc không có gì chen giữa,
  nhưng nếu user bấm Save trước khi thấy banner (banner bị `save()` clear, nhưng bản thân banner
  đã hiển thị *trước đó* dựa trên version cũ), hoặc một tab/CLI khác ghi thêm version, bấm "Load
  vN" sẽ nạp một document khác vN mà UI vẫn ghi nhãn vN. Sửa: gọi thẳng
  `api.cvVersion(scope, editSkippedVersion)` rồi `setDraft(detail.document)` — đúng nghĩa đen
  của "Load vN", không phụ thuộc HEAD đang ở đâu.
- **Copy "Save to add yours on top of it" mô tả sai.** `PUT /cv/{scope}` không merge, nó ghi
  đè nguyên `draft` — nên làm đúng lời banner (Save sau khi bấm bỏ qua) sẽ **thay** nội dung
  của agent ở đầu lịch sử bằng bản của user, không phải cộng dồn. Sửa lại câu cho khớp: nói rõ
  Save sẽ thay vN ở head, vN vẫn còn trong History (append-only, không mất).

**Bài học lặp lại lần ba, cùng một hình dạng:** vòng 1 diff mù nội dung thêm vào; vòng 2
`dirtyRef` quên effect khác dùng chung; vòng 3 banner quên phân biệt "có lưu" với "không lưu".
Cả ba đều là **một effect/hàm phục vụ nhiều nhánh, sửa đúng nhánh đang nhìn mà quên nhánh còn
lại đọc chung một biến**. Review độc lập trên diff thật — không phải tự đọc lại code mình vừa
viết — là thứ duy nhất bắt được cả bốn vòng.

**Verify vòng 4:** `ruff check jobpilot` sạch, `tsc --noEmit` sạch, 844 test Python vẫn xanh
(vòng này không đổi code Python, chỉ `CvStudio.tsx`). Không có test frontend tự động cho
`CvStudio.tsx` (`web/src` chưa có `*.test.tsx` nào) — banner + "Load vN" verify bằng đọc code
qua ba vòng review độc lập, không phải chạy tay, vì lý do đã nói ở trên (không muốn ghi version
thử nghiệm vào Master CV production để verify).

### Review gate vòng 5 — chính bản vá "Load vN chính xác" của vòng 4 lại là bug nặng hơn

`loadSkippedEdit` đổi từ `refetch()` sang `api.cvVersion(scope, editSkippedVersion)` +
`setDraft()` để tránh nạp nhầm HEAD trong ca hiếm (tab khác ghi thêm version giữa lúc banner
hiện và lúc user bấm Load). Review vòng 5 chỉ ra: cách đó đổi một sai **hiếm** lấy một sai
**chắc chắn xảy ra mỗi lần bấm Load**. `setDraft` một mình không đụng `data`/`savedVersion`, mà
`dirty` so `draft` với `data.document` — nên ngay sau Load, `dirty` vẫn `true` (draft = nội dung
vN, data vẫn là bản trước đó vì không có gì gọi `refetch()`). Header tiếp tục ghi "vN cũ ·
unsaved changes" dù editor đang hiện *đúng* nội dung agent vừa lưu, và nếu user tin theo badge
đó mà bấm Save thì `PUT` **luôn append** (không dedupe) → ghi thêm một version giống hệt bản agent
vừa lưu — đúng thứ mà chính round 3 sửa `edit_master` để tránh (history đầy row trùng lặp), giờ
tái diễn từ phía UI. `savedVersion` kẹt lại còn kéo lệch `editBase.current` của round edit tiếp
theo.

Sửa: quay lại `refetch()` cho `loadSkippedEdit` — refetch nuôi effect "adopt server document"
(đã unconditional từ vòng 3) nên `draft`+`savedVersion` được set **cùng nhau**, `dirty` về đúng
`false`. Ca hiếm (HEAD đã bị tab khác đẩy qua vN) thì đơn giản là nạp bản mới hơn thật — một sự
thật, không phải một lỗi hiển thị. Bài học: giữa "chính xác tuyệt đối ở ca hiếm" và "đúng luôn ở
ca thường", chọn cái sau nếu ca hiếm không phải mất dữ liệu, chỉ là kém tối ưu.

Ba mục nhỏ sửa cùng lượt (đọc ra khi review vòng 5 truy hết toàn bộ writer của `data`/`draft` để
xác nhận blocker trên):

- Effect edit-landing không gate theo `scope` — instruction chỉ sửa Master, nhưng effect đọc
  `scope` **lúc nó chạy**, không phải lúc task được gửi đi; user gửi instruction rồi chuyển
  sang xem CV tailored của một job trước khi task xong sẽ khiến effect refetch/mở diff/hiện
  banner nhắm vào scope sai. Thêm `if (scope !== "master") return;` và `scope` vào dependency
  array.
- Lưu raw LaTeX (tab LaTeX) không xoá `editSkippedVersion` — banner "Your edits were kept" có
  thể vẫn đứng đó sau khi một save khác (từ tab LaTeX) đã ghi đè đúng draft mà nó tuyên bố giữ.
  Thêm `setEditSkippedVersion(null)` vào `onSaved` của `RawLatexEditor`.
- (Không cần sửa riêng: bỏ nhánh `try/catch` quanh `api.cvVersion` cùng lúc với việc bỏ chính
  lệnh gọi đó — `refetch()` của `useApi` không throw, tự lưu lỗi vào `error` state đã có sẵn
  đường hiển thị ở đầu component.)

**Verify vòng 5:** `tsc --noEmit` sạch, `ruff check jobpilot` sạch, 844 test Python không đổi
(vòng này chỉ sửa `CvStudio.tsx`).


---

## Phase i18n — dashboard song ngữ Việt/Anh (mặc định Tiếng Việt)

**Mục tiêu:** toàn bộ 10 trang web đọc được bằng tiếng Việt, giữ English là ngôn ngữ hạng nhất,
đổi qua lại bằng một nút trên header. Không thêm dependency runtime nào.

### Vì sao không dùng `react-i18next`

App cố ý chỉ có 7 dependency runtime; bảng chữ là **2 ngôn ngữ cố định**; tiếng Việt **không
biến cách số nhiều** nên không có luật plural nào đáng mô hình hoá. Đổi lại, một `Record` có
type cho **key check lúc biên dịch** — thứ mà tra cứu bằng string thuần không cho. Cụ thể helper
`ns({en, vi})` khai `vi` là mapped type trên `keyof en`, nên **thiếu một chuỗi tiếng Việt hoặc
thừa một key lạ = lỗi `tsc`**, mà `npm run build` vốn đã chạy `tsc --noEmit`. Không cần lint riêng.
Kết quả: **17 namespace, 751 key**, parity verify bằng script — 0 lệch.

### Quyết định: ba helper thành hook, bản không-ngôn-ngữ bị xoá hẳn

`relativeTime()` / `qualityLabel()` / `STATUS_INFO` cũ **đã bị xoá**, thay bằng `useFormat()` /
`useLabels()` / `useStatuses()`. Hai lý do, lý do sau mới là chính:

1. Một hàm thuần đọc biến "ngôn ngữ hiện tại" ở module scope sẽ **không re-render** khi user bấm
   đổi ngôn ngữ — bảng "3h ago" đứng nguyên tiếng Anh tới khi có thứ khác tình cờ invalidate nó.
2. **Xoá hẳn bản cũ biến mọi call-site sót thành lỗi biên dịch.** Nếu chỉ *thêm* bản mới, chuỗi
   sót lại sẽ lặng lẽ hiện tiếng Anh giữa trang tiếng Việt — đúng loại "sai mà trông như đúng"
   mà repo này đã trả giá nhiều lần. 14 lỗi `tsc` ngay sau khi xoá chính là danh sách việc phải làm.

### Cách chạy: 1 spine + 11 agent song song

Tự viết phần xương (provider, `ns`, `common`/`nav`/`labels`/`format`/`statuses`/`task`, Layout,
Pagination, StatusPill, TaskProgress), rồi **fan out 11 agent, mỗi agent sở hữu đúng 1 file
dictionary + các file page của nó**. `dict/index.ts` được viết sẵn đầy đủ 17 namespace và các
file namespace được tạo sẵn dạng stub rỗng hợp lệ, nên **không agent nào phải sửa file chung** —
zero conflict. Component dùng chung bởi nhiều agent (`TaskProgress`, `Pagination`, `StatusPill`,
`ui.tsx`) tự làm trước để không ai giẫm chân.

**Bẫy các agent tự phát hiện, đáng ghi lại:** `tsc` gặp **lỗi cú pháp** ở một file thì **bỏ luôn
semantic check của mọi file khác**. Giữa lúc 11 agent cùng sửa, `npx tsc --noEmit | grep <file của tôi>`
trả về rỗng **không** có nghĩa là sạch — nó rỗng vì một agent khác đang viết dở. Vài agent tự
dựng `tsconfig` tạm chỉ include slice của mình, và **verify chính công cụ verify** bằng cách cắm
một key sai rồi xem nó có báo không. Đúng bài học "đừng để công cụ đo bịa ra finding".

### Ba bug chỉ lộ ra khi chạy thật (test + tsc đều xanh trước đó)

1. **Pill trạng thái vỡ 3 dòng.** Mọi state tiếng Anh là **một từ** (`discovered`) nên pill chưa
   bao giờ có cơ hội wrap; `mới tìm thấy` là **ba từ**, trong ô bảng nó xuống 3 dòng và đội cao
   toàn bộ row. Thêm `whitespace-nowrap` vào `StatusPill` — pill là *nhãn*, nó phải nong cột ra
   chứ không được reflow bên trong.
2. **Nút vỡ đôi.** `Bỏ qua` tách thành `Bỏ` / `qua` và tràn khỏi viền, vì `Button` cao cố định
   không có chỗ cho dòng thứ hai. Thêm `whitespace-nowrap` vào `Button` gốc — nhãn tiếng Việt
   phần lớn 2 từ trong khi tiếng Anh 1 từ, nên đây là lỗi sẽ còn tái diễn nếu vá lẻ từng chỗ.
3. **`titleCase` bịa ra tên board.** `BySourceChart` và `SourceScorecard` title-case key thô →
   `Itviec`, `Wework remotely`, `Topcv`. `sourceLabel` tồn tại đúng để tránh chuyện này. Đây là
   bug **có sẵn từ trước**, chỉ lộ ra vì agent trang Jobs sửa còn agent trang Dashboard không —
   hai trang cạnh nhau viết tên khác nhau mới thành thứ nhìn là thấy. *Viết hoa không phải là
   dịch*: `sourceLabel` cho dim source, `levelLabel` cho dim level, `titleCase` cho channel.

### Quyết định có chủ ý: ba chip gợi ý trong InstructionBox **giữ tiếng Anh** ở cả 2 ngôn ngữ

Bấm chip là đổ text vào textarea, và text đó **không phải chrome** — nó đi thẳng tới model làm
instruction, mà với `add_entry` thì `source_quote` **buộc phải xuất hiện nguyên văn trong đó**,
nên câu chữ của user đáp xuống CV nguyên si. Chip tiếng Việt + Master CV tiếng Anh = một bullet
tiếng Việt nằm giữa tài liệu tiếng Anh.

Đào thêm thì thấy: `textnorm.quote_appears_in` **xử lý tiếng Việt đúng** và fail-closed (mất dấu
là trượt) — guardrail provenance vẫn nguyên. Nhưng **`edit_guard._NUMBER_WORDS` chỉ có tiếng
Anh**, và `_WORD_RE` của nó là `[a-zA-Z]+` nên **không match nổi "mười hai" hay "gấp đôi"** — một
con số bịa viết bằng **chữ số** vẫn bị bắt, viết bằng **chữ tiếng Việt** thì lọt. Lỗ này có sẵn
từ trước; đẩy user sang viết instruction tiếng Việt chỉ làm nó **dễ chạm tới hơn nhiều**.
Kết luận: dịch chrome, **không** dịch thứ trở thành input cho model viết CV. Không có gì chặn
user tự gõ tiếng Việt — chỉ là UI không đi mời.

### Còn lại tiếng Anh (biết, và cố ý)

- **Câu do backend soạn** — `facet.note` (Market), `split.note` (Dashboard), `llm.blocker()` /
  `llm.warnings()` (Models), các `*_hint` (Applications), `description` của template (CV Studio).
  Đây là **dữ liệu**, không phải copy; dịch ở frontend nghĩa là pattern-match câu tiếng Anh của
  chính mình — mong manh và sai chỗ. Muốn phủ hết thì phải sửa backend (trả key + số, hoặc nhận
  tham số ngôn ngữ), là một phase riêng.
- **Danh từ riêng** (`ITviec`, `PostgreSQL`), **bậc seniority** (thị trường VN rao tin bằng đúng
  thang tiếng Anh), **config key / CLI / đường dẫn**, và **nội dung CV của user**.

### Verify

`npm run build` xanh (tsc + vite), **844 test Python** vẫn xanh, script parity 17/17 namespace
không lệch, **0 console error**. Chạy thật trên Postgres 180 job: đi qua Deck / Jobs / CV Studio /
Guide / Market / Settings ở cả VI và EN, `1920×1080`. Đổi ngôn ngữ lật đúng cả **định dạng ngày**
(`2/8/2026` ⇄ `8/2/2026`). Ba font (Inter, Space Grotesk, JetBrains Mono) đều **đã kiểm** là có
subset `vietnamese` trên Google Fonts — không phải đoán, `curl` lấy CSS ra đọc `unicode-range`.

## Bỏ Docker khi build CV PDF — engine tectonic, Docker thành đường lui (2026-09-01)

**Vấn đề không phải tốc độ.** Docker đã chạy sẵn thì build hết 3.9s — chấp nhận được. Vấn đề là
**3.18 GB ảnh**, là phải nhớ bật Docker Desktop, và là ba bước provisioning thừa trên VPS
~100k/tháng (`apt install docker.io` + `usermod -aG docker` + pull 3.5 GB). Đo lại trên Linux:
tectonic là **9.7 MB** tarball tĩnh + ~50 MB cache ⇒ nhẹ hơn ~50 lần, không daemon, không nhóm
user, chạy được cả ARM64 (ảnh docker **chỉ có amd64**).

### Spike trước, code sau — và spike suýt fail

Luật đã đặt ra: 4 câu hỏi, fail câu nào thì giữ Docker. Câu 1 (`awesome_cv` có compile không)
**fail ngay**, và fail theo kiểu chỉ lộ ra khi chạy thật:

1. `fontawesome.sty:12` nạp font **theo tên** (`\newfontfamily{\FA}{FontAwesome}`). Tên chỉ
   resolve được khi font **cài ở mức hệ thống** — ảnh docker có sẵn, nên đường này chạy suốt
   nhiều tháng, và `fonts/FontAwesome.ttf` **trong repo chưa bao giờ được dùng**. Engine trần thì
   chết: `The font "FontAwesome" cannot be found`. Đây đúng dạng "phụ thuộc ẩn vào môi trường" mà
   refactor này sinh ra để giết. Sửa: ưu tiên `Path=fonts/`, giữ nhánh theo tên làm dự phòng.
2. Sửa xong lộ lỗi thứ hai: `awesome-cv.cls:159` định nghĩa **lại** `\FA`. fontspec cũ (TeX Live
   trong ảnh docker) cho ghi đè im lặng; fontspec mới (bundle tectonic) báo
   `Command '\FA' already defined` và chết cả build.
3. **`\renewfontfamily` là cái bẫy.** Nó là fix hiển nhiên, và nó **đổi lỗi tectonic lấy lỗi
   docker** — TeX Live trong ảnh không có lệnh đó (`! Undefined control sequence`). Chỉ biết vì
   ràng buộc "Docker vẫn phải chạy được" bắt build lại bằng cả hai. Cuối cùng dùng
   `\let\FA\relax` trước `\newfontfamily`: cả fontspec cũ lẫn mới đều đọc là "chưa định nghĩa".

⇒ Bài học: **hai file vendor này giờ phải build bằng CẢ HAI engine mới biết đúng**, vì mỗi engine
chỉ bắt được một nửa số lỗi.

### Output có giống hệt không — đo, không đoán

Đọc lại **text layer** bằng pdfminer (không nhìn PDF bằng mắt: `cv/CLAUDE.md` ghi rõ thiếu glyph
là khoảng trắng **im lặng**), trên **Master CV thật** *và* sample có tiêm tiếng Việt đủ dấu, cả
hai template:

| | awesome_cv | plain |
|---|---|---|
| Số trang | 1 = 1 | 1 = 1 |
| Glyph tiếng Việt | đủ ở cả hai engine | đủ ở cả hai engine |
| Tập từ (chuẩn hoá) | **trùng khít** | **trùng khít** |
| Verdict `ats.py` | **trùng** | **KHÁC** — xem dưới |

Khác biệt còn lại, nói thẳng:

- **20 token khác nhau ở text layer của `awesome_cv`**, hết. 14 token là chữ `I` hoa trong đoạn
  small-caps bị trích ra thành `i` thường (`ENGINEER` → `ENGiNEER`); 6 token là dấu nối
  U+002D ⇄ U+2010 (`real-time` → `real‐time`). **Không ảnh hưởng tìm kiếm**: `ats.py` hạ chữ
  thường và `_WORD_RE` cắt ở dấu nối — và verdict trùng nhau đã chứng minh điều đó bằng thực
  nghiệm, không phải bằng suy luận.
- **`plain` build bằng docker nhả ra 2 ligature `ﬁ`, tectonic thì không** ⇒ finding `ligatures`
  **biến mất** khi đổi engine. Đây là *tốt hơn* (recruiter search "office" không khớp "oﬃce"),
  nhưng nó có nghĩa **báo cáo ATS của cùng một CV phụ thuộc engine đã build nó**. Ghi lại vì đúng
  loại khác biệt sẽ làm người ta đi sửa nhầm template.
- Thứ tự đọc của pdfminer khác nhau ở khối header và khối projects. Cả hai đều xáo; không mất chữ.

Và kiểm ngược lại chiều còn lại: build docker với `.cls`/`.sty` lấy từ `HEAD` so với bản đã sửa —
**cùng số trang, text layer giống hệt**. Hai file vendor sửa xong không đổi output của Docker.

### Bẫy tự tay dẫm phải

- **`config.local.yaml` nằm ở `jobpilot/`, không phải repo root.** Đặt nhầm chỗ ⇒ file bị bỏ qua
  **im lặng**, `cv.engine` vẫn là `auto`, và lệnh `jobpilot cv build` báo "Built ... [OK: 1 page]"
  bằng **Docker** trong khi mình tưởng đang verify tectonic. Suýt kết luận "tectonic chạy rồi"
  từ một lần chạy không hề đụng tectonic. Đúng loại "báo cáo thành công" mà `CLAUDE.md` cảnh báo.
- **Log của tectonic ghi `Output written on cv.xdv`, KHÔNG phải `cv.pdf`.** `_pages_from_log` khớp
  được chỉ vì phần tên file là wildcard — đã thêm test ghim, đừng "dọn" regex chặt lại.
- **Chỉ tectonic để lại `.log`; docker thì không.** Build dir dùng chung theo scope ⇒ log của lần
  build tectonic trước còn nằm đó khi sau này build bằng docker, và nếu thiếu pypdf thì
  `_pages_from_log` đọc log cũ rồi báo số trang của **một PDF đã không còn tồn tại**. Nên
  `build_cv()` xoá `.log` cùng lúc với `.pdf` (có test).

### Hai bug chỉ lộ ra ở review gate — cả hai đều "chạy được trên máy mình"

Verify ở trên **không bắt được** hai lỗi này, vì nó build vào thư mục sạch trên một máy đã có
Docker. Cả hai chỉ nổ **sau khi merge**, ở máy người khác:

1. **`sync_assets()` ghim asset cũ vào build dir vĩnh viễn.** Nó `skip-if-exists`, mà
   `out/cv/<scope>/` thì **sống lâu và dùng lại** ⇒ mỗi scope bị khoá vào bản `awesome-cv.cls` /
   `fontawesome.sty` của lần build **đầu tiên**. Bản vá cho tectonic vì thế chỉ tới được scope
   build mới; build lại một CV cũ chết ngay với `The font "FontAwesome" cannot be found` **trong
   khi repo đã có fix** — nên thông báo lỗi trỏ sai hướng hoàn toàn. Tệ hơn: `build_cv()` xoá
   `.pdf` trước khi build, nên scope đó **mất luôn PDF cũ**. Đã dựng lại đúng lỗi này trên
   `out/cv/itviec_2156537` trước khi sửa.
   ⚠️ **Đừng "tối ưu" `sync_assets` về skip-if-exists.** Nó so **nội dung** (`filecmp`,
   `shallow=False`), kể cả file **bên trong** thư mục asset như `fonts/` — bản cũ chỉ copy khi cả
   thư mục vắng mặt, nên một file font cũ là không bao giờ với tới được. Không dùng mtime:
   `git checkout` đóng dấu lại mtime ⇒ báo "đã đổi" cho file không đổi, và **bỏ sót** file vendor
   được restore từ commit cũ hơn.
2. **`deploy/jobpilot-api.service` vẫn `Requires=docker.service`** sau khi DEPLOY.md bỏ cài Docker.
   systemd **từ chối start** một unit có `Requires=` trỏ tới unit không tồn tại ⇒ làm đúng theo
   hướng dẫn mới thì **cả API lẫn dashboard chết**, không phải chỉ build PDF. Hạ xuống `Wants=`
   (giữ trong `After=` để ai cố ý chạy `cv.engine: docker` vẫn được thứ tự đúng).

Và một bug thứ ba của chính vòng sửa: **test xanh vì nó ghim cái mock.** `resolve_engine` được
sửa để trả path đã resolve, nhưng `shutil.which("./tools/tectonic")` **trả nguyên chuỗi tương
đối** — nó chỉ check path đó có chạy được không, không đổi thành absolute. Test đầu tiên
monkeypatch `which` trả sẵn `/opt/bin/tectonic` nên xanh mà **không chứng minh gì**. Đã thay bằng
test đặt **file thật ở path tương đối thật**, và kiểm lại rằng nó **fail** khi gỡ `os.path.abspath`.

### Verify

**858 test xanh** (844 + 14 mới). Chạy thật, không dừng ở test: build Master CV thật + sample
tiếng Việt × 2 template × 2 engine, cover letter (`cover_letter.tex`, entry khác `cv.tex`) × 2
engine — 1 trang, dấu tiếng Việt đủ. `jobpilot cv build` qua CLI ra `[OK: 1 page]` bằng tectonic.
Build lần đầu ~3 phút (tải gói TeX về cache), lần sau **~1–2.5s offline** (`-C` không cần mạng).

## Parser lương — nhánh một-số nuốt mất cái trần, ba lần nữa (2026-09-01)

Cùng một hình dạng bug với ca `"15tr - 25tr"` ở Phase 21, và nó **tái phát ba lần**. Gốc chung:
khi `_RANGE` không khớp, `parse()` **rơi xuống nhánh `_ANY_NUM`** và báo **sàn thành cả hai đầu**.
Không có lỗi, không có cảnh báo — chỉ là một cái trần bị thay bằng cái sàn.

| Nhãn | Trước | Sau |
|---|---|---|
| `2000～3000 USD` | 2000–2000 | 2000–3000 |
| `$2,000 - $3,000` | 2000–2000 | 2000–3000 |
| `160 triệu+` | 160tr–160tr | 160tr–**None** |
| `Lương admin 5 triệu` | sàn mở 5tr | 5tr–5tr |

1. **Tilde.** Dấu ngăn không chỉ là gạch ngang: board ghi `~`, và bộ gõ CJK biến nó thành
   full-width `～` hoặc wave dash `〜`. `_SEP` giờ gồm `- – — − ~ ～ 〜 to đến` (thêm cả **dấu trừ
   thật** U+2212, khác hyphen ASCII).
2. **Ký hiệu tiền ở đầu số thứ hai.** Unit được cho phép *sau* số thứ nhất (`15tr - 25tr`) nhưng
   không có gì được phép *trước* số thứ hai, trong khi board Mỹ ghi `$` ở **cả hai** đầu. Đúng
   một bug với ca `15tr`, chỉ khác đầu.
3. **Sàn mở bịa ra trần.** `160 triệu+` ra `min=max=160tr` — **khẳng định một cái trần mà tin
   không hề nói**. Đối xứng với luật "up to 3000 ⇒ min=None" đã có sẵn: bound không được nói thì
   để `None`. ⚠️ Nói cho đúng mức: ca này **không đổi con số nào hôm nay**, vì `usd_month` lấy
   trung bình các bound *đã biết* nên cả hai cách đều ra 6299.21, và `market.py` chỉ đọc
   `usd_month`. Sửa vì mô hình hoá sai, **không** vì biểu đồ đang sai — hai ca range ở trên mới
   là chỗ con số thật sự đổi.
4. **Bug thứ tư tự tìm thấy khi đang sửa**: `_MIN_ONLY` không có `\b` nên `min` khớp vào giữa chữ
   "ad**min**" ⇒ `"Lương admin 5 triệu"` thành sàn mở 5tr. Đã thêm `\b` cho mọi keyword.

**Bug do CHÍNH lần sửa này đẻ ra — review gate bắt, và phải vá BẢY VÒNG mới kín.** Hàng rào
"con số chỉ là tiền khi được viết như tiền" lắp thiếu chỗ ba lần liên tiếp, mỗi lần đều là **đúng
cái lỗi đang đi diệt**:

1. Thêm `trên`/`dưới` vào `_MIN_ONLY`/`_MAX_ONLY` mà **không đòi con số dính đơn vị tiền**. Hai
   từ đó phổ biến bậc nhất trong boilerplate tin Việt ⇒ `"Lương 20 triệu, trên 2 năm kinh
   nghiệm"` báo sàn **2 triệu** (job 20tr rơi vào band `<$500`), `"20 triệu, dưới 30 tuổi"` lấy
   **tuổi** làm trần lương. **Tệ hơn** nhánh một-số nó thay thế — nhánh đó lấy số đầu tiên, mà
   label lương luôn dẫn bằng lương.
2. Bản vá đầu của hàng rào lại nhận **"số nằm cuối label"** là đủ ⇒ đúng câu đó **đảo trật tự
   chữ** là lọt lại: `"Lương 20 triệu, tuổi dưới 30"` → trần 30tr. **Một cái neo không phải là
   một đơn vị.**
3. `_MIN_SUFFIX` — nhánh **mới nhất, do chính lần sửa này thêm vào** — bị bỏ quên ngoài hàng rào,
   nên mọi `<số>+` vẫn thành sàn mở: `"20 triệu, 3+ năm kinh nghiệm"` báo sàn **3 triệu**. Mà số
   năm kinh nghiệm chính là thứ hay đi kèm dấu `+` nhất trong một tin tuyển dụng.
4. `_RANGE` cũng bị bỏ ngoài hàng rào, mà lần sửa này lại **nới `_SEP` thêm `~ ～ 〜 −`** ⇒
   `"Lương 20 triệu, 2 ~ 3 năm kinh nghiệm"` ra `2tr–3tr`. **Khoảng số năm kinh nghiệm được viết
   y hệt khoảng lương**, chỉ khác cái đơn vị — nới separator mà không có hàng rào là mở cửa cho
   đúng thứ đó, và lần này nó làm **hỏng những nhãn `main` đọc đúng**.

Cộng một ca cùng gốc: **bảng ký hiệu tiền bị chép ra ba bản, và ba bản đã lệch nhau.** `$` là ký
hiệu hợp lệ **sau** con số ở bản này mà không ở bản kia ⇒ `"Up to 2000$"` bịa ra sàn 2000 trong
khi `"Up to 2000 USD"` thì không — vi phạm chính cái luật ghi trong docstring của module. Giờ chỉ
còn **một** `_MONEY` dùng chung. (Cùng bài học với `normalize_title` ở `crawler/CLAUDE.md`: hai bộ
luật song song sẽ lệch, chỉ là lúc nào.)

Và marker **đứng trước** thì lệch thêm một lần nữa: `US$` là tiền ở `_RANGE` (có test ghim hẳn)
nhưng không phải tiền ở `_MAX_ONLY`, nên `"Thưởng 2 tháng, up to 3000 US$"` rơi xuống `_ANY_NUM`
và báo lương = **2** (số của "2 tháng"). Lệch **ngay trong chính commit tuyên bố đã gộp bảng**.

**Luật cuối**: con số là tiền khi có **ký hiệu đứng trước** (`$2000`, `USD 2000`, `US$ 2000`)
**hoặc marker đứng sau** (`2000 USD`, `2000 (USD)`, `20 triệu`, `2000$`). Marker đứng trước nằm ở
**một** hằng `_LEAD`, marker đứng sau ở **một** hằng `_MONEY`, và **cả bốn** nhánh
(`_RANGE`/`_MIN_ONLY`/`_MAX_ONLY`/`_MIN_SUFFIX`) dựng từ hai hằng đó. Nhánh thứ năm `_ANY_NUM`
**cố ý** không có hàng rào — nó là chỗ mọi nhãn "không phải tiền" rơi xuống, và ở đó lấy **số đầu
tiên** mới là câu trả lời đúng.

⚠️ **Thêm keyword / separator / hình dạng mới mà không đi qua `_LEAD`/`_TRAIL` là cách cả bốn
regression trên lọt vào.** Không có ngoại lệ nào đáng.

**Regression thứ NĂM — và lần này câu trả lời đúng là REVERT, không phải sửa tiếp.** Tôi tự ý
thêm `k` = nghìn (không nằm trong bug được báo; nhặt từ một gợi ý của reviewer). Cờ `thousands`
làm **toàn nhãn** giống `millions`, nên nó nhân ×1000 cả những bound **vốn đã đúng**:
`"$800 - $900/month, 401k"` → 800.000–900.000/tháng; `"800 - 1200 USD + thưởng 500k"` còn tệ hơn
— chỉ bound thấp bị scale, rồi guard `low > high` **đảo hai đầu**, giấu luôn dấu hiệu bất thường.
`401k` là chữ chuẩn của board Mỹ, `"thưởng 500k"` là boilerplate tin Việt.

`millions` sống được như cờ toàn nhãn **chỉ vì** tin VN có quy ước "số trần cạnh *triệu* là
triệu". `k` không có quy ước đó. Làm đúng = gắn scale vào **chính figure mang chữ `k`** — một
thay đổi riêng, cho một bug **có sẵn trên `main`** và **không** nằm trong phạm vi được giao. Nên:
revert, ghi vào docstring của module như **giới hạn đã biết**, và có test ghim để không ai thử
lại lối tắt.

Kèm một bài học về test: test tôi viết cho guard của `k` là **test rỗng** — nó assert trên
`"1,500 - 2,500 USD"`, nhãn **không hề có chữ `k`**, nên `thousands` không bao giờ bật và assert
pass bất kể guard đúng hay sai. Đúng loại "test xanh không chứng minh gì" mà `CLAUDE.md` cảnh báo,
lần thứ hai trong cùng một task (lần trước là test ghim cái mock của `shutil.which`).

**Regression thứ SÁU**: `_MIN_SUFFIX` vẫn nhận `|\s*$` — "hết label" làm marker tiền — tức đúng
cái mà banner comment ngay phía trên nó **cấm**, và đúng bài học đã ghi ở vòng 2 ("một cái neo
không phải là một đơn vị"). Bỏ mấy chữ đuôi đi là bug vòng 3 lọt lại: `"20 triệu, 3+"` → sàn
3 triệu, `"2000 USD, 5+"` → sàn 5 USD. Bằng chứng nó là **dead weight** chứ không phải đánh đổi:
xoá nhánh đó rồi chạy lại `test_market.py` → **0 test fail**. Đã xoá + ghim test.

### Chỗ QUYẾT ĐỊNH KHÔNG SỬA, và lý do là số đo chứ không phải sự thận trọng

Còn một họ nhãn branch **tệ hơn `main`**: marker tiền **tách rời cả hai bound** —
`"Lương USD, 1,500 - 2,500"` ra `1500–1500` (main: `1500–2500`). Fence đòi marker **dính** vào
một trong hai bound, mà cái này nằm tách phía trước cả cụm.

Đã **thử sửa**: cho phép dấu câu giữa marker và số (`_GAP = [\s:,)\]]*`). Kết quả đo được:
sửa đúng 3 ca detached-marker, **và đẻ ra một false positive mới** —
`"Lương USD, 2 - 3 năm kinh nghiệm"` → `2–3`. Tức là **đổi một lỗi lấy một lỗi khác**, đúng cái
trade đã thua sáu lần trong chính task này. ⇒ **Revert, giữ fence chặt, ghi thành giới hạn thứ
ba** trong docstring của module. Tin ghi currency **cạnh** con số — gần như toàn bộ, và **tất cả**
nguồn JSON-LD — không bị ảnh hưởng.

**Regression thứ BẢY**: hàng rào chỉ hỏi *"đây có phải tiền không"*, **không bao giờ hỏi *"đây có
phải TIỀN LƯƠNG không"***. `_MIN_SUFFIX` (nhánh mới của branch này) vì thế bám vào **tiền thưởng**:
`"Lương 20 triệu, thưởng 500k+"` → sàn **500 triệu** — đẩy job 20tr lên gần **đỉnh** biểu đồ, tệ
hơn mọi ca trước (các ca trước chỉ đẩy xuống đáy). Và ở chiều ngược lại, `"Lương USD, up to 3000"`
→ `3000|3000`: keyword trượt fence rồi rơi xuống `_ANY_NUM`, mà nhánh đó trả `min == max` ⇒ **bịa
ra đúng cái bound mà tin tuyên bố là mở** — gương ngược của chính fix headline (`160 triệu+`).

Sửa: (1) `_MIN_SUFFIX` chỉ thắng khi **không có figure NÀO viết-như-tiền đứng trước nó**. (2)
Keyword bound đã xuất hiện mà không đọc được figure tiền ⇒ trả `None` ("không biết"), **không** để
`_ANY_NUM` trả lời thay bằng một mốc bịa.

⚠️ Cách phân biệt **theo vị trí** ("floor phải là số đầu tiên") là **sai và đã bị bỏ**: nó sửa 4 ca
`thưởng 500k+` nhưng **làm hỏng 12 ca** kiểu `"Thưởng 2 tháng, 160 triệu+"` (ở đó floor **chính là**
lương). Tín hiệu đúng không phải vị trí mà là **figure đứng trước có phải tiền hay không**:
`"20 triệu"` là tiền, `"2 tháng"` / `"tháng 13"` / `"85%"` thì không.

### Sai sót về PHƯƠNG PHÁP ĐO — tự phát hiện, phải ghi lại

Ba vòng đầu tôi chạy differential bằng `git stash` rồi copy `salary.py` ra so sánh. **`git stash`
chỉ cất phần CHƯA COMMIT** — mà lúc đó đã có 3–5 commit trên branch ⇒ cái tôi gọi là "main" thực
ra là **HEAD trừ đi mấy sửa đang dở**. Nên con số *"230 nhãn, 25 ca đổi, toàn cải thiện"* ở các
vòng trước **không phải** so với `main`; nó chỉ so với chính branch vài phút trước đó. Lấy `main`
thật phải là `git show main:jobpilot/crawler/salary.py`.

Đo lại cho đúng, với oracle "**nhiễu không được làm đổi đáp án**" (parse riêng phần lương sạch rồi
so với khi có nhiễu bao quanh) trên 289 nhãn:

| | khớp đáp án sạch |
|---|---|
| `main` | 141/289 — **49%** |
| branch | 283/289 — **98%** |

**142 ca tốt hơn, 0 ca tệ hơn.** 6 ca còn lại đều là giới hạn #2 đã ghi (`"Thưởng 2 tháng, 2000
USD"` → 2), và `main` cũng sai y hệt.

**Giới hạn còn lại, nói thẳng**: fence không cứu được nhãn **dẫn đầu bằng số không-phải-tiền** —
`"2 - 3 năm KN, 20 triệu"` vẫn ra 2 triệu, vì `_ANY_NUM` (cố ý không fence, phải có ai đó trả lời)
lấy số đầu tiên. `main` cũng sai ca này. "Lấy số đầu tiên" đúng nhiều hơn sai, nhưng là
**heuristic, không phải bảo đảm**.

**Chỗ tinh tế, và bản đầu sửa NGƯỢC**: `"2000 USD + phụ cấp"` **không** phải sàn mở — dấu `+` đó
giới thiệu một khoản cộng thêm, rất phổ biến trong tin Việt. Đọc nó thành "2000 trở lên" là **đổi
một con số sai lấy một con số sai khác**.

⚠️ Regex đúng là **`(?<!\s)\+`** — tín hiệu nằm ở **khoảng trắng ĐỨNG TRƯỚC** dấu `+`: dính số
là sàn mở, rời ra là khoản cộng thêm. Bản đầu viết `\+(?!\s*\w)` (**SAI, đừng copy**), key vào
thứ **đứng sau** dấu `+`, nên đọc ngược `"15tr+ gross"` và `"2000+ USD"`: cả hai đều là sàn mở mà
vẫn bị bịa trần.

### Verify

**+18 test mới** (878 tổng). Verify qua **đường production `derived_facets()`**, không chỉ gọi
`parse()` — vì thứ đi vào `payload` là hàm đó. `usd_month` của ca range sửa từ **2000 → 2500**,
tức **+25%** vào đúng con số dựng nên median của `/market`.

### Vòng review thứ 7 (sau merge) — mất độ phủ, và một bài học ngược

Chạy `phase-reviewer` một vòng nữa **sau khi merge**. Verdict: `main` **an toàn, không blocker**,
nhưng bắt được một **hồi quy về ĐỘ PHỦ** do chính guard tôi thêm ở vòng 6:

`_bound_word_owns_the_only_figure` bail ra `None` khi **có keyword nào đứng trước chữ số đầu
tiên** — không hỏi keyword đó có **dính** vào chữ số đó không. Hậu quả:

| nhãn | trước 2 PR | sau vòng 6 |
|---|---|---|
| `Up to: 3000 USD` | `3000\|3000`, usd 3000 | **`None`** |
| `Up to (3000 USD)` | `3000\|3000`, usd 3000 | **`None`** |
| `Từ Hà Nội: 20 triệu` | `20tr`, usd 787 | **`None`** |

**Bài học ngược với trực giác**: `usd_month` lấy trung bình **các bound đã biết**, nên
`min=3000,max=3000` và `min=None,max=3000` ra **cùng một số**. Tức cái "sàn bịa" mà guard đi dẹp
**chưa bao giờ đổi con số trên `/market`** — còn cái `None` nó trả về **thì có**: job **rơi hẳn**
khỏi `salary_bands` và khỏi mẫu số `covered/total`. Đổi một lỗi mô hình hoá **vô hại** lấy một
mất mát **đo được**. `None` không phải lúc nào cũng là "câu trả lời thật thà".

Sửa: (1) keyword phải **dính** figure (`_KEYWORD_GAP` = chỉ dấu câu + space, không phải `.*`);
(2) khi nhãn **không có figure nào viết-như-tiền**, lấy figure của keyword làm bound đơn —
**chính keyword đã nói đó là đầu nào** (`_unfenced_bound`); (3) gộp keyword về **một** cặp hằng
`_MAX_WORDS`/`_MIN_WORDS` (trước đó `_BOUND_WORD` là **bản thứ tư** chép tay, thiếu `đến`), tiện
thể thêm `tối đa`/`không quá`/`tối thiểu` vốn thiếu ở mọi bản ⇒ `"tối đa 30 triệu"` từng ra
`30|30`.

Đo lại bằng oracle so với `main` **trước cả hai PR** trên 506 nhãn: **44% → 98%, 0 ca tệ hơn,
0 ca mất độ phủ**.

### Verify trên DỮ LIỆU THẬT (chạy crawl mới, không chỉ nhãn tự bịa)

Cả 6 vòng review đều chỉ đo trên **nhãn tổng hợp** — đúng bẫy #1 của repo. Nên đã **crawl thật**
thêm (ITviec/VietnamWorks/LinkedIn/Arbeitnow/Greenhouse; TopCV bị 403 như đã biết) → 196 job.

Nhãn lương **thật** thu được, cộng chuỗi lương nằm trong **title** (moi từ `payload`):

| Nhãn thật | nguồn | `main` | branch |
|---|---|---|---|
| `20 - 60 triệu` | TopCV | 20tr–60tr | 20tr–60tr |
| `$ 1,500-2,500 /tháng` | VietnamWorks | 1500–2500 | 1500–2500 |
| `IT Salary Report 2024-2025` | ITviec | `None` | `None` |
| `$42/hr` | WWR (title) | 42, hour | 42, hour |
| **`Up to $3500`** | **ITviec (title `SA Java - Up to $3500`)** | **3500–3500** ❌ | **None–3500** ✅ |

⚠️ **Chú ý về `$42/hr` và `Up to $3500`: hai chuỗi đó nằm ở TITLE, không phải field `salary`.**
Production chỉ gọi `salary.parse` trên `salary_raw` (`normalize.derived_facets`), **chưa bao giờ**
trên title — nên ca dưới đây là *format có thật ngoài đời*, nhưng **hôm nay chưa có đường nào dẫn
nó vào parser**. Đừng đọc thành "đã sửa một chart đang sai".

⇒ **Có một ca thật sự sai trên `main` và branch sửa đúng**: `$` nằm **giữa keyword và con số**, mà
pattern cũ đòi ngay sau `up to` phải là chữ số ⇒ rơi xuống nhánh một-số và **bịa ra một cái sàn**
cho tin vốn không hề nói sàn — vi phạm chính luật ghi ở đầu module. Đây là **format có thật**, không
phải nhãn tôi nghĩ ra. Đã thêm test `test_salary_shapes_seen_in_the_live_database` ghim đúng 4 nhãn
thật này, có ghi rõ xuất xứ.

Bốn nhãn còn lại **giống hệt nhau** ở hai bên ⇒ branch **không phá** nhãn thật nào.

**Nói thẳng về mức độ ảnh hưởng thực tế**: corpus local hiện chỉ có **2 nhãn lương parse được**
trên **196 job** (57% là LinkedIn — không có lương; ITviec giấu lương sau login; TopCV 403), và
cả hai nhãn đó **không dính** bug nào trong bảng trên. Nên `/market` ở máy này **chưa hề vẽ sai** —
guardrail `covered/total` đang báo đúng *"Only 2 job(s) list a parsable salary"*. Phần lớn bug đã
sửa vẫn **đang tiềm ẩn**; chỉ ca `Up to $3500` là đã quan sát được ngoài đời. Không có chuyện
"chart đang sai và giờ đã đúng".

⚠️ **`salary_range` là dữ liệu đã ghi trong `payload`, không tính lại lúc đọc.** Sửa parser xong
**bắt buộc `backfill --force`** (đã chạy: 181 job), nếu không `/market` vẫn vẽ bằng số cũ và mọi
verify đều "xanh" một cách vô nghĩa.

---

## Phase intake — dán JD vào, AI đọc + chấm, rồi mới tailor

**Xuất phát**: form "Add job" đã có từ Phase 9, nhưng nó bắt gõ tay 5 ô. User muốn: nhặt JD ở đâu
đó, dán một phát, AI đọc giúp, chấm giúp, rồi tự quyết có tailor không.

### Ba bước, cố ý tách rời

`POST /jobs/intake` (đọc → điền form, **không lưu**) → `POST /jobs` (như cũ) →
`POST /jobs/{id}/fit` (chấm CV vs tin). Nút tailor vẫn là nút riêng, user bấm — human-in-the-loop.

### Bug đã có sẵn trên `main`, lộ ra khi làm cái này

**Job thêm tay không hề được enrich.** `create_job` bỏ qua toàn bộ `normalize()`: không `quality`,
không `salary_range`/`skills_canonical`/`city`/`is_remote`, không suy ra `level`, và
`match_score = 0.0`. Hệ quả: job dán tay **vô hình với `/market`** và **luôn xếp bét** trong list
sort theo độ khớp — mà trên màn hình **không có gì giải thích tại sao**. Không phải "sai số", mà là
một job cả app không nhìn thấy đúng. Đã tách `crawler/normalize.enrich()` (nhận giá trị thuần,
trả `Enrichment`) và gọi từ cả `POST /jobs` lẫn `PATCH /jobs`. Verify thật: job dán tay giờ ra
`match_score 1.0`, `matched: [Java, Spring Boot, Backend, Microservices]`.

`PATCH` cũng cần nó: dán JD vào một tin LinkedIn alert là **đúng mục đích tồn tại** của endpoint đó,
mà cờ `no_jd` vẫn nằm nguyên sau khi user đã sửa đúng cái mà cờ đó phàn nàn.

### Ba luật của vùng này (chi tiết ở `jobpilot/intake/CLAUDE.md`)

1. **JD lưu xuống là bản dán của user, không bao giờ là bản model kể lại.** `JdExtract` **không có**
   field `description_md`. Mọi guardrail phía sau đọc field đó như *bằng chứng*; để model viết lại
   là để nó bịa ra bằng chứng cho chính nó, và không guard nào bắt được.
2. **Fit report chỉ advisory** — không ghi vào CV, không vào cover letter, không vào prompt tailor.
   Chính ranh giới đó cho phép `intake/engine.py` **không có** vòng retry: không có luật máy móc
   nào phân biệt ý kiến đúng với ý kiến sai.
3. **`assess_fit` không đụng cột `jobs.match_score`.** Ba con số khác nhau cùng tên — bảng ở
   `intake/CLAUDE.md`. `PATCH` cũng giữ cột lại khi job đã qua tailor.

### Đo được, không đoán

- **`match_score` của fit bị TÍNH LẠI từ list, không lấy của model.** Cùng prompt, cùng job, ba
  backend: **0.50 / 0.32 / 0.31** — chênh gần như hoàn toàn vì *bao nhiêu requirement bị xếp
  `must_have`*, không phải vì bất đồng về CV có gì. `soft` trọng số **0** (CV không chứng minh được
  "high growth drive"); tin toàn `soft` → **0.5 chứ không phải 0.0**; `verdict` derive từ điểm và
  dealbreaker ép về `weak`. Sau khi tính lại, ba backend cùng ra verdict `weak`.
- **`llm bench --task intake`** (mới): 3 tin có đáp án, chấm theo **field** (11 field), và nửa số
  đáp án là **ô trống** — vì hỏng kiểu của call này là điền vào chỗ tin không hề nói.
- **Default model KHÔNG phải cái rẻ nhất qua bench**, và đó là chủ ý. gpt-4o-mini 55/55 field, rẻ
  hơn 3 lần; nhưng hỏi 4 lần "CV có `Java, Spring Boot` thì có đáp ứng `working JVM knowledge`
  không" thì trả HAVE / MISSING / PARTIAL / MISSING. gpt-4.1-mini: HAVE cả 4 lần, 54/55 field.
  ⇒ bench chỉ đo **nửa** việc này. Lý do ghi thẳng trong `config.yaml`.

### Verify trên môi trường thật

Postgres thật + trình duyệt thật, 0 console error. Dán một tin tiếng Việt có **panel "Việc làm
tương tự"** (2 mức lương của tin khác): cả 3 model đều lấy đúng `45 - 65 triệu`, **không** dính bẫy.
Lấy đúng `careers@…`, level `senior`, `language vi`. Extract ~3s, fit ~7s. Fit ra `Khớp yếu · Phủ
39%` với dealbreaker `Không đủ 4 năm kinh nghiệm backend với Java`, evidence trỏ đúng entry có thật
trong Master CV.

### Bẫy đã trả giá

- **`clean_text` phá JD.** Nó gộp mọi khoảng trắng **kể cả `\n`** — đúng cho title/location, hỏng
  cho body: JD phần lớn là gạch đầu dòng, gộp hết thành một đoạn là ném đi cấu trúc. `clean_paste`
  làm sạch **theo từng dòng**. Chỉ thấy được khi mở trình duyệt và nhìn bullet list render.
- **`job.status` là `None` cho tới khi flush** (default của cột do DB áp, không phải constructor),
  nên guard `job.status in _EARLY` trên row vừa `db.add()` cho `False` ⇒ **mọi job thêm tay vẫn
  score 0.0** — đúng cái bug đang đi sửa. Test bắt được.
- **`from jobpilot.crawler import normalize` bind vào *hàm*, không phải module** (package re-export
  cả hai tên) ⇒ `AttributeError` lúc **chạy**, không phải lúc import.
- **`posted_at` từ DB naive, `vn_now()` aware** — SQLite naive / Postgres aware, nên `flags_for`
  raise trên một backend chứ không phải cả hai. `enrich()` gọi `as_aware` một lần cho mọi caller.
- **`model_copy(update=...)` bỏ qua validator** ⇒ test "level lạ bị drop" viết bằng nó là test
  không kiểm gì cả.
- **Prompt nói ngôn ngữ ở đâu thì model nghe ở đó.** Luật "viết bằng ngôn ngữ của tin đăng" nằm
  lẫn trong danh sách field thì bị bỏ qua — tin tiếng Việt ra summary tiếng Anh, giữa dashboard
  tiếng Việt. Đưa lên **mục riêng đầu system prompt** thì đúng ngay lần đầu.
- **`llm.TASKS`**: tuple task vốn được chép tay ở 3 chỗ. Thêm task thứ 4 mà chỉ sửa 2 chỗ thì
  trang `/models` lặng lẽ không cấu hình được thứ CLI cấu hình được. Giờ một tuple, mọi nơi đọc nó.

### Review gate — findings đã sửa

`phase-reviewer` trả **CHANGES REQUESTED**, một blocker + 6 mục. Đã sửa hết:

- **Blocker: 500 trên Postgres.** Prompt bảo model *chép nguyên văn* nhãn lương, nên tin ghi lương
  thành cả câu cho ra `salary` 148 ký tự → `VARCHAR(128)` → `StringDataRightTruncation` giữa flush,
  **500 không nói field nào sai**, sau khi user đã trả tiền cho lượt gọi model. Lỗ này **có sẵn trên
  `main`**, nhưng trước đây phải tự gõ 148 ký tự vào ô lương mới chạm tới; giờ có model điền hộ.
  `_fit()` thành `fit_column(field, value)` public + `COLUMN_WIDTHS`, áp cho cả `POST` lẫn `PATCH`.
  Đã tái hiện **và** verify lại trên Postgres thật: 500 → 201, cắt đúng 128/256.
- **Card fit tự mâu thuẫn**: `counts` đếm cả `soft` trong khi điểm cho `soft` trọng số 0 ⇒
  "Khớp tốt · Phủ 100%" nằm cạnh "2 có · 4 thiếu". Giờ chỉ đếm requirement **được chấm**, `soft`
  tách riêng ("4 kỹ năng mềm (không tính điểm)").
- **`skills` bị form vứt đi**: `IntakeOut` trả skills, UI không map → job dán tay vào DB với
  `skills_canonical: []` ⇒ **không đóng góp gì cho facet skill của `/market`**, đúng cái lý do
  `enrich()` được viết ra. Test cũ xanh chỉ vì `_save()` tự gửi skills — **đường mà UI thật không
  bao giờ đi**, bẫy #1 của repo ở dạng nhẹ. Giờ skills hiện thành chip xoá được.
- **`SENDS_MASTER_CV` thành hằng chết** sau khi `warnings()` chuyển sang dict có default ⇒ task thứ
  5 *không* gửi CV mà quên khai sẽ bị cảnh báo **sai**. Giờ `PROMPT_CONTENTS` là bảng gốc,
  `SENDS_MASTER_CV` phái sinh từ nó, và thiếu entry thì **raise**, không đoán.
- **Câu "cùng công thức với tailor nên so được với nhau" là sai**: `TailorPlan.match_score` lấy
  nguyên số của model, `FitReport` thì tính lại. Đã bỏ mệnh đề đó ở cả tooltip lẫn docstring.
- **`clean_paste` làm phẳng bullet lồng nhau** trong khi module tự nhận "byte-for-byte". Giữ indent
  (cap 8 cột), sửa luôn docstring cho đúng sự thật.
- **`intake: openai` hard-code**: checkout mới chỉ có `ANTHROPIC_API_KEY` sẽ ăn 409 ở đúng tính năng
  chính của phase. Đổi về `""` (theo `llm.provider`) + `task_models.intake: claude-haiku-4-5` —
  haiku 44/44 field **và** trả lời đúng nửa fit cả 4 lần.
- **Nit**: `undated` bật ở preview rồi bị chính bước lưu xoá (save stamp `posted_at = now`) ⇒ chip
  mà lần dán nào cũng bật và lần lưu nào cũng tắt chỉ dạy user bỏ qua chip; `notes` từ dead payload
  thành tooltip của chip; `read()` đổi sang `useRef` guard theo `web/src/CLAUDE.md`; `TASKS` ở
  `Models.tsx` giờ **fail biên dịch** nếu thiếu một `LlmTask` (đã thử: bỏ `intake` ra → `error
  TS2322 ... ["missing from TASKS:", "intake"]`).

Reviewer cũng nêu **CV rỗng** là nợ có sẵn (tailor cũng không guard). Đã guard cho `assess_fit`:
gửi skeleton đi sẽ nhận "weak, 0%" — phán quyết tự tin về sự nghiệp user trong khi sự thật là
"bạn chưa điền CV". Ngưỡng **đo từ chính skeleton**, vì skeleton ra **đúng 200** ký tự và một hằng
200 gõ tay sẽ nằm ngay trên ranh giới rồi cho lọt.

**Cố ý không sửa**: `assess_fit` không `manager.broadcast`. `broadcast` là `async`, đổi route thành
`async def` là đem lượt gọi model ~7s lên **event loop** — chặn cả app để đổi lấy việc tab thứ hai
thấy fit mới. Lý do đầy đủ ở `jobpilot/intake/CLAUDE.md`.

---

## Phase intake-2 — JD có cấu trúc, lương 4 dạng, tỉnh/thành, hình thức làm việc

Đợt 1 của yêu cầu mở rộng (đợt 2: company + HR + migration, chưa làm).

### JD có cấu trúc — hai lượt gọi song song

`extract` (fact đầu tin) + `sections` (thân tin chia 8 bucket: vai trò, nhiệm vụ, yêu cầu chuyên
môn, ưu tiên, kỹ năng mềm, kết quả mong đợi, quyền lợi, cách ứng tuyển). Hai schema nhỏ thay vì một
schema 18 field / 7 array — đúng hình dạng mà `llm/CLAUDE.md` ghi là bị provider từ chối. Chạy
**đồng thời**: đo thật, cả cặp ≈ lượt chậm hơn (~3s khi cache, ~8s lần đầu), không phải tổng.

**Đã đo schema trước khi chọn**, không đoán: `JdSections` raw 2703 / strict 2703 / flat 2703 — dưới
`TailorPlan` (4682/4994) vốn đã PASS cả 3 provider. Rồi **gọi thật cả 3**: claude-haiku, gpt-4.1-mini,
gemini-3.5-flash đều nhận, đều xếp `"Docker, Kubernetes là một lợi thế"` vào `nice_to_have` và đều
bỏ qua panel "Việc làm tương tự".

**Bucket là mục lục CỦA `description_md`, không thay nó.** Cả hai cùng lưu; UI là toggle
"Có cấu trúc / Nguyên văn" **trong** card JD, không phải card thứ hai — bản gốc cách một click là
điều duy nhất khiến hiển thị bản sắp xếp của model là an toàn.

### Bug đã dính (và đây là lần thứ HAI của cùng một bài học)

**Model dịch tin tiếng Việt sang tiếng Anh.** Mọi dòng đúng nội dung, nhưng không còn là dòng của
tin đăng — phá đúng luật cốt lõi của tính năng. Luật "giữ nguyên ngôn ngữ" nằm **lẫn trong một
đoạn văn** thì bị bỏ qua. Nâng thành **mục riêng, viết hoa, ở đầu system prompt** → 4/4 lượt trên
2 backend trả tiếng Việt nguyên văn. Y hệt ca `summary` của fit report ở đợt trước, trong cùng file
prompt. ⇒ **Luật về ngôn ngữ đặt trong danh sách field thì model không nghe.**

### Lương: 4 dạng chứ không phải 3

Yêu cầu nói 3 (fix / up to / range). Parser **vốn đã** sinh ra dạng thứ 4: **sàn không trần**
(`Từ 15 triệu`, `trên 20 triệu`). Gộp nó vào `range` là bịa ra một cái trần; gộp vào `fixed` là bịa
ra một mức lương. `Salary.kind` **suy ra** từ `min`/`max` (không lưu) nên không thể lệch khỏi con số
nó mô tả.

### Tỉnh/thành: hai lỗ đo được trên corpus thật

- **`"Ho Chi Minh City, Vietnam"`** — dạng **mọi** LinkedIn alert dùng, mà LinkedIn >½ corpus —
  tách thành `["Ho Chi Minh City", "Vietnam"]`; `"Vietnam"` không phải city ⇒ trượt cửa "mọi phần
  đều là city" ⇒ **rớt cả nhãn**. `city=None`, job biến mất khỏi chart city của `/market`, **không
  một lỗi nào hiện ra**.
- **`"TP.HCM"`** fold thành `"tp hcm"`, không có trong alias ⇒ cũng `None`.
- **`(On-site)` / `(Hybrid)` là chú thích của NHÃN** (`"Hanoi Capital Region (On-site)"`), cùng họ
  với `(mới)` của TopCV. Strip rồi đọc lại thành `work_mode` — một chuỗi, hai thông tin.

**Đo sau `backfill --force`**: có location mà không ra tỉnh **160 → 119**. Phần còn lại là thành phố
**nước ngoài** (Berlin ×10, London ×7, Bangalore ×6…) — `None` ở đó *đúng*, `CITIES` chỉ có 34 tỉnh
VN. `work_mode` phủ **105/216** job (36 remote / 22 hybrid / 47 onsite), trước đó là 0.

⚠️ **`is_remote` và `work_mode` từng mâu thuẫn.** 8 job ghi `"Anywhere in the World"`: `_REMOTE_RE`
biết, pattern viết tay song song thì không ⇒ `is_remote=true` mà `work_mode=null`, **cùng một dòng,
cùng một câu hỏi**. Nhánh remote giờ dùng lại `_REMOTE_RE.pattern`; có test ghim; sau backfill
**0 mâu thuẫn**. Hai field suy ra từ một nhãn thì không được có hai bộ luật — bài học cũ, chỗ mới.

⚠️ Đây là lý do `backfill --force` **bắt buộc** sau khi sửa parser: `city`/`salary_range`/`work_mode`
là dữ liệu **đã ghi**, không tính lại lúc đọc.

### Review gate (intake-2) — findings đã sửa

`phase-reviewer` trả **CHANGES REQUESTED**, 2 blocker + 4 mục + 3 nit. Đã sửa hết.

**Blocker 1 — `backfill --force` XOÁ SẠCH facet của mọi job dán tay.** `backfill_facets` đọc input
từ `payload["location"]` / `payload["salary"]`, mà hai key đó **chỉ `normalize()` ghi** — job vào
qua `POST /jobs` chưa bao giờ có. Nên nó gọi `derived_facets(None, ..., None)` và null hoá
`city`/`salary_range`/`is_remote`/`work_mode`. Không crash, không log: **một cú xoá im lặng, do
chính lệnh mà tài liệu bảo BẮT BUỘC chạy sau khi sửa parser**. Đã có thật trong Postgres: row
`manual:selftest-backend` (`location='Ha Noi, Vietnam'`) đang mang `city=NULL`, tức đang vắng mặt
khỏi chart city của `/market`. Sửa: đọc từ **cột** (`job.location`/`job.salary`) — nguồn duy nhất cả
hai đường ghi đều có — payload chỉ còn là fallback. Chạy lại backfill: row đó về `city='Hà Nội'`,
`no-city` **119 → 114**, `city` **94 → 99**.

**Blocker 2 — `PATCH /jobs` vứt `work_mode`.** `{**payload, **signals.payload}` mà `signals.payload`
**luôn** có key `work_mode` (derive từ nhãn location) ⇒ đè lên cả giá trị user vừa PATCH lẫn giá trị
đã lưu. `create_job` đặt ngược lại nên **giữ** — hai endpoint hai luật, và đó đúng là lý do test
không bắt được (mỗi endpoint chỉ test theo thứ tự của chính nó). Hệ quả thật: job remote lưu từ
intake, user **sửa JD trong card Job description** → chip work_mode biến mất vĩnh viễn. Sửa bằng
**một helper `_merged_payload` dùng chung**: ai *nói ra* thì thắng, nhãn location chỉ là fallback.

**Còn lại:**
- `sections` hỏng thì **không** làm hỏng cả lượt intake nữa — `JdSections` là schema lớn hơn, dễ bị
  provider từ chối hơn; fail cả form là ném đi một `extract` user đã trả tiền. Giờ degrade về bucket
  rỗng (UI hiện tab "Nguyên văn"), có log.
- **`level` không được clamp** — `String(32)`, tới thẳng từ request body ⇒ đúng cái bẫy
  `StringDataRightTruncation` mà batch trước viết `fit_column` để đóng, chỉ đóng cho 4 cột. Thêm
  `level` vào `COLUMN_WIDTHS` và clamp **trong `enrich()`** (một chỗ quyết định cho cả hai writer).
- **`work_mode` chưa đóng vocabulary ở biên API** — `JobIn.work_mode: str` nhận mọi chuỗi, ra màn
  hình thành chip title-case vô nghĩa. Giờ là `Literal`, **derive từ `WORK_MODES`** kèm assert để
  hai bên không thể biết hai bộ từ khác nhau.
- **`Salary.kind` tính ra rồi chôn vào JSONB** — user hỏi "lương 3 dạng" mà không dạng nào lên màn
  hình. Giờ có `JobDetailOut.salary_kind` và chip cạnh mức lương ("40 - 60 triệu · khoảng").
- **Claim "một chuỗi, hai thông tin, không mất cái nào" chỉ đúng với LinkedIn**: ITviec/TopCV/
  VietnamWorks cho location qua `clean_city` **trước khi lưu**, nên hậu tố `(Hybrid)` đã mất trước
  khi `parse_work_mode` kịp đọc. Chưa gây sai dữ liệu (board VN không viết hậu tố đó) nhưng comment
  đang nói sai — đã sửa lại cho đúng.

**Nit:** `looks_like_city("Ha Noi, 2025")` **thành True** sau thay đổi (trước là False) — vì
`_fold_city` xoá cả chữ số nên phần "2025" fold ra rỗng rồi bị bỏ qua, **nới đúng cái cửa mà scar
"remote debugging" sinh ra để giữ**. Sửa: chỉ bỏ qua phần **toàn từ trang trí** (`_is_only_filler`
= có chữ cái, nhưng hết sạch sau khi bỏ filler), nên "2025" và "..." vẫn phải tự chứng minh là city.
Bỏ một dòng no-op trong validator `work_mode`.

**Reviewer nói đúng một chỗ khó chịu**: lúc review, `select count(*) where payload ? 'sections'` = 0
— tức đường ghi `sections` qua `POST /jobs` **chưa từng chạy thật**, dù summary ghi "verified live".
Thật ra nó *đã* chạy trong trình duyệt, nhưng tôi **xoá row test sau mỗi lần verify**, nên trạng thái
còn lại không chứng minh được gì. Đã chạy lại end-to-end sau khi sửa: intake 6.1s → save
(`salary_kind='from'`, `work_mode='hybrid'`, sections tiếng Việt nguyên văn) → PATCH lương
(`salary_kind` đổi thành `range`, `work_mode` **giữ nguyên**, sections **không** bị drop vì JD không
đổi). Bài học: **xoá dữ liệu verify xong thì lời khai "đã verify" không còn kiểm chứng được** —
lần sau giữ lại row cho tới khi review xong.

---

## Phase companies — nhà tuyển dụng thành bảng, HR thành người, và một quyết định không sống qua đêm

Đợt 2 của yêu cầu mở rộng intake (đợt 1 = `intake-2`). `companies` + `hr_contacts` là bảng thật
(migration `0011`), `jobs.company_id` là FK, `/companies` liệt kê công ty · HR · số job đã nộp,
và email HR **được mời** làm `apply_target` — mời, không bao giờ tự áp.

### Ba quyết định sản phẩm (user chốt trước khi viết code)

1. **Row công ty tự sinh + backfill cả 160 tên đang có**, không phải "chỉ tạo khi thêm HR".
   `/companies` vì thế có nội dung ngay, và mọi job đều có `company_id`. Đổi lại ~150 row chưa
   có HR nào — nên **thứ tự mặc định là "nộp nhiều nhất"**, để số ít công ty đang thực sự làm
   việc nổi lên trên.
2. **Gộp theo key đã fold**, không phải so chuỗi thô. `jobs.company` giữ nguyên chính tả gốc.
3. **Chỗ mời email HR: trang job**, không phải form Add-job hay bước xác nhận apply.

### Fold: đo trên 160 tên thật TRƯỚC khi chốt

`normalize_company(strip_legal=)` — **tham số của hàm sẵn có**, không phải normalize thứ ba
(cùng luật với `normalize_title(strip_level=)`). Dedup vẫn `False`, `companies` bật `True`.

Kết quả trên corpus thật: **160 chuỗi → 158 key**, gộp đúng **2 cặp** (`GitLab`/`gitlab`,
`JetBrains`/`jetbrains`), **0 gộp sai**, **0 key rỗng**. Hướng nguy hiểm là hướng **gộp nhầm** —
hai công ty chung một row nghĩa là một bên được mời email HR của bên kia — nên: từ pháp nhân
tiếng Anh **chỉ cắt ở đuôi** (`"SA Group"`, `"Co-op Bank"` là tên thật), tiếng Việt **chỉ cắt ở
đầu** (`Công ty TNHH`), cụm 2 từ khớp **nguyên cụm** (`cổ phần` — `"phan"` đứng một mình là họ
người Việt), hậu tố **quốc gia không phải pháp nhân** (`DXC Technology Vietnam` ≠ `DXC
Technology`), và **không bao giờ cắt tới rỗng**.

Tên hiển thị = chính tả **phổ biến nhất** trong job của công ty đó (11 `GitLab` thắng 3
`gitlab`), hoà thì alphabet. Chỉ áp cho row backfill **tạo mới** — row đã có không bao giờ bị
đổi tên, vì tới lúc đó nó có thể đã được sửa tay.

### Bug chỉ lộ ra khi chạy thật — và nó là bug của chính tính năng này

**Chọn email HR làm `apply_target` giữ được đúng tới lượt crawl tiếp theo.** `persist._refresh`
ghi đè cột bằng URL của board. Âm thầm, vài ngày sau, không gì trên màn hình cho thấy một quyết
định đã bị xoá. Mà job crawl là gần như **mọi** job ⇒ nếu không sửa thì "mời làm nơi nộp"
**không sống qua một đêm**.

Phát hiện bằng cách nhìn DB thật sau khi crawl lại `arbeitnow`, **không phải** bằng test: 988
test xanh suốt trong lúc lỗi này đang tồn tại, vì không test nào ghép "user sửa" với "crawl lại".

Sửa bằng đúng luật `_merged_payload` đã dùng cho `work_mode` — **ai nói ra thì thắng, bản
scrape là fallback**: `PATCH` ghi `payload["apply_target_source"] = "user"`, `_refresh` đọc rồi
không đụng cột nữa. Và key đó **phải** vào `_ROW_OWNED_KEYS` (`_carry_dedup_trace` đổi tên
thành `_carry_row_keys`), vì `_refresh` thay **cả** payload — không carry thì nó lại chỉ sống
tới lượt crawl kế, y hệt lý do `dedup` phải được carry. Verify lại trên Postgres thật: đặt
`hr@camunda.example` → crawl lại `arbeitnow` → `last_seen_at` bump, `apply_target` **giữ nguyên**.

### Verify trên môi trường thật (không chỉ test)

- `alembic upgrade head` trên **PostgreSQL 17 thật**: tạo 2 bảng + 1 cột, backfill in ra
  `created 158, linked 216`. **0 job unlinked.** Chạy `cli backfill` lần nữa: `created 0,
  linked 0` — idempotent.
- **Trình duyệt thật**, VI và EN, **0 console error**: thêm HR (`Nguyễn Thị Hằng`, có dấu, kèm
  ghi chú tiếng Việt) → số `1 liên hệ` trên dòng cập nhật ngay → mở job GitLab → bấm "Dùng làm
  nơi nộp" → `apply_target` đổi trong DB, nút thành dấu tick.
- **Crawl thật cả hai nhánh**: `arbeitnow` insert 3 job mới (link + tạo 2 công ty mới), và một
  job `company='jetbrains'` **refresh** vào đúng row `JetBrains` đã có — fold chạy đúng trên dữ
  liệu thật, không phải trên fixture.
- **Kiểm mất dữ liệu có chủ đích**: `PATCH {apply_target}` lên một job đang mang `fit`, `city`,
  `work_mode`, `skills_canonical`, `quality`, `is_remote` — so payload trước/sau, **không mất
  key nào**, `match_score`/`level`/`company_id` không đổi. Đây là đúng loại lỗi hai đợt trước
  đã dính.
- **Nulls 62 link của `arbeitnow` rồi chạy `backfill`**: `linked 59` (3 job đã được crawl relink
  trước đó), về **0 unlinked**.

### Bẫy đã trả giá

- **Import vòng.** `companies.service` cần `crawler.text`; import bất kỳ submodule nào của
  `jobpilot.crawler` cũng chạy `__init__`, mà `__init__` import thẳng `persist`. Import ở module
  scope của `persist.py` **chỉ chạy khi crawler tình cờ được import trước** — migration 0011
  chạm `companies.service` trực tiếp và nổ `ImportError`. Đã chuyển vào trong `persist_jobs`,
  có comment; đừng "dọn" lên đầu file.
- **`status_code=204` + `-> None` làm FastAPI assert lúc dựng app** ⇒ **11 file test fail ở
  bước collect**, không phải một test đỏ. Đổi `DELETE contact` sang trả `CompanyDetailOut` —
  hợp với `DELETE /cv/{scope}/tex` sẵn có, và tiết kiệm một round-trip vì client luôn vẽ lại
  đúng cái card vừa đổi.
- **`_require_contact` phải kiểm cả `company_id`**, nếu không id liên hệ của công ty A sửa được
  qua URL công ty B.
- **`ORDER BY` kết thúc bằng `Company.id`**: gần như mọi công ty hoà ở 0 đơn đã nộp, nên tie là
  **mặc định** chứ không phải ngoại lệ.
- **`applied_count` đếm JOB, không đếm row `applications`**: gửi lại sau một lần bounce là một
  job đã nộp, không phải hai; `dry_run` chưa rời khỏi máy.
- **`{count} contacts` ra "1 contacts" trong tiếng Anh.** Repo đã có sẵn quy ước `…One`
  (`inboxFoundOne`, `followupsTitleOne`) — dùng nó, đừng dựng máy plural.
- **Clamp field text của contact**: dán nguyên chữ ký mail vào ô "Tên" là đầu vào 400 ký tự,
  và Postgres trả `StringDataRightTruncation` giữa flush. Scar cũ, chỗ mới.

### Review gate (companies) — findings đã sửa

`phase-reviewer` trả **CHANGES REQUESTED**, 2 blocker + 5 mục + 3 nit. Đã sửa hết.

**Blocker 1 — tính năng chính không thật sự chạy với job crawl.** Ghi `apply_target` là **chưa
đủ**: mọi scraper hard-code `apply_channel` là `portal`/`external`, **không nguồn nào** sinh
`email`, và `resolve_channel` **ưu tiên cột đã khai**. Nên chọn email HR xong bấm nộp rơi vào
`_apply_handoff` — *"mở link và tự nộp"*, với `hr@example.com` ở vai trò cái link, và
`--open-portal` lái browser `goto()` vào đó. **Không email nào được dựng**, mà app báo handoff
thành công. Chứng minh trên chính row verify trong Postgres: `resolve_channel(...) -> 'external'`.
Job thêm tay **cũng dính** (`JobIn.apply_channel` mặc định `"external"`, form Add-job không gửi
field đó) ⇒ lời mời `apply_email` của JD ở đợt `intake` **vốn đã hỏng** theo đúng cách này, chưa ai
phát hiện. Sửa: `_note_stated_target` đổi luôn `apply_channel` sang `email` khi địa chỉ user nói ra
parse được thành email (một chiều; caller tự khai kênh thì thắng), `_refresh` giữ **cả hai** cột,
và `offerHint` **nói ra** rằng nút này đổi kênh — im lặng đổi nghĩa của nút Nộp là thứ nguyên tắc 2
cấm.

**Blocker 2 — `applied_count` khai lại `SENT_RESULTS` thay vì import nó.** `apply/outcome.py` ghi
thẳng luật *"`SENT_RESULTS` is imported rather than restated"*, và đây đúng là ca nó đề phòng. Đơn
portal/external nằm ở `awaiting_user`, mà board / follow-up / inbox sync / `/analytics` **đều** coi
đó là đã gửi. Đếm mỗi `success` cho ra **`0 đã nộp`** ở đúng những công ty đang theo đuổi — và vì
`order=applied` là mặc định, nó **dìm họ xuống đáy 160 dòng**, đúng thứ trang này sinh ra để đẩy
lên. DB thật lúc review có 0 row `awaiting_user` nên không lộ; test cũng chỉ dùng `success`.

**Còn lại:**
- **`POST /companies` không clamp `name`** → `StringDataRightTruncation` trên Postgres (reviewer
  tái hiện thật). Nhưng chỗ đúng để clamp là **`company_key`**, không phải lúc insert: key là thứ
  mọi lookup select trên đó, clamp muộn nghĩa là SELECT bằng fold đầy đủ (không khớp) → INSERT bản
  cắt → đụng unique → re-read lại bằng fold đầy đủ → **trả `None` cho một công ty đang tồn tại**.
- **Migration 0011 dùng `select(Job)`** ⇒ phát ra **mọi cột model có hôm nay** (đo: **17 cột**).
  Ngay khi có 0012 thêm cột vào `jobs`, một máy mới chạy `alembic upgrade head` sẽ chết **tại
  0011** với `UndefinedColumn`. `link_all_jobs` giờ core-select **3 cột tường minh** + Core UPDATE
  (nên phải `expire_all()`). ⚠️ Lần mô phỏng đầu của tôi (`append_column` lúc runtime) **không
  chứng minh được gì** — nó không tới được mapper nên bản cũ cũng "pass"; bằng chứng thật là so
  **SQL compile ra**: 17 cột vs 3 cột.
- **`POST /jobs` là writer duy nhất phớt lờ cờ nó vừa đẻ ra**: dán lại đúng tin đó chạy nhánh
  fallback `body.url` và **xoá** lựa chọn của user, trong khi payload vẫn khai `"user"`.
- **Assertion luôn đúng** trong chính test bảo vệ bug vừa sửa: `A and B or title == "Backend"` —
  vế phải luôn đúng nên mệnh đề không bao giờ fail. Ghim lại bằng `title` **đổi thật** giữa hai
  lượt persist.
- **Tên hiển thị hoà phiếu chọn nhầm bản có pháp nhân**: alphabet thôi làm `"Cong ty TNHH Foo"`
  thắng `"Foo"` khi mỗi bên 1 job. Giờ ưu tiên bản **ngắn hơn**.

**Nit đã sửa:** `q` escape `%`/`_` trước `ilike` (không thì `100%` khớp `1000 …`); debounce 250ms
cho ô tìm kiếm; **`mtv` chỉ là pháp nhân khi đã cắt được gì đó trước nó** — đứng đầu thì
`MTV Networks` → `networks`, chung chung đủ để đụng nhà tuyển dụng khác, tức **hướng nguy hiểm**.

**Reviewer nói đúng một chỗ về chính lời khai của tôi**: nhánh race `IntegrityError` trong
`resolve_company` (`begin_nested` + re-read) **chưa có test nào** và không dựng được điều kiện đua
thật — nó vẫn là nợ, không phải thứ đã verify.

997 test pass sau khi sửa.

---

## Phase deploy-mac — Mac mini thay laptop Windows, chạy khi máy bật (2026-10-04)

**User chốt:** miễn phí + nhẹ máy ⇒ Mac mini ở nhà (IP dân dụng VN, idle ~5–7 W). **Không cần chạy
khi tắt máy** — bật nguồn + đăng nhập là lên. **Bỏ DB Windows**, dựng mới (DB thử trên Mac giữ lại,
bản dump cất ở `~/JobPilotBackups/mac-testdb-before-restore-20261004.dump`).

- 3 **LaunchAgent** (`deploy/macos/install.sh`): api (KeepAlive), crawl 08:30/18:30, backup lúc
  login + 03:00. LaunchAgent chứ không phải Daemon: FileVault bật ⇒ màn hình mở khoá lúc boot
  **chính là** login; Postgres (brew services) + Tailscale cũng ở tầng này.
- **Mọi agent qua `run.sh`** vì PATH của launchd là `/usr/bin:/bin:/usr/sbin:/sbin` — không có
  tectonic, không có `pg_dump` (keg-only). Keg `postgresql@NN` đặt **trước** `/opt/homebrew/bin`.
- **Bug chỉ lộ khi chạy thật:** (1) crawl.log trống 2 phút dù đang chạy → `PYTHONUNBUFFERED=1`;
  (2) `bootout` trả về trước khi gỡ xong ⇒ `bootstrap` ngay sau đó lỗi `5: Input/output error` →
  chờ `launchctl print` fail; (3) build CV **rỗng** lỗi LaTeX `There's no line here to end` ở
  `\makecvheader` — **chưa sửa** (nợ: DB mới bấm build trước khi điền tên là gặp).
- **Review gate:** APPROVE + 4 nên sửa, đã sửa: crawl watchdog 45 phút (launchd không chạy bản thứ
  hai của job đang chạy ⇒ crawl treo nuốt mọi slot sau); `update.sh` đọc token qua
  `get_secrets()` chứ không `grep|cut` (token có ngoặc kép → bundle 401 mà `/health` vẫn xanh);
  `healthcheck.sh` so PID giữ port với PID agent (dev server `--reload` ở :8000 trả 200 thay agent).

## Phase crawl-fix — id 134 ký tự làm đỏ cả 6 nguồn (2026-10-04)

Crawl thật đầu tiên qua launchd: ITviec để nguyên tên pháp nhân trong slug → id 134 > `VARCHAR(128)`
→ `StringDataRightTruncation` giữa flush → session `PendingRollbackError` → **mọi site sau đó** fail.

- `types.make_job_id()`: giữ đầu id + `-<sha1[:12]>` của **cả** id khi dài quá ⇒ deterministic, không
  cần migration, id cũ không đổi. Test ghim width = mọi cột FK `job_id`.
- Savepoint **mỗi job** (`persist_jobs`) + **mỗi site** (`run_crawl`). Row hỏng → `rejected` (tách khỏi
  `errors` = site fail), CLI in `PART`, Runs có cột riêng.
- **Review gate:** APPROVE; 2 nên sửa đã sửa. Bài học: test "index chỉ add sau savepoint" **lần đầu
  pass cả khi có mutation** — vì `_Index` dựng lại **mỗi site**, row ma chỉ hại job sau nó *trong
  cùng site*. Viết lại test trong một site, mutation mới fail. **Test phải được thấy fail.**
- Thật: crawl rc=0, 11 job mới, 5/6 nguồn (LinkedIn thiếu IMAP — cô lập đúng).

## Phase claude_cli — chạy LLM trên gói Claude của user (2026-10-04)

User: gói Max dùng không hết, app host ở máy mình ⇒ dùng nó thay API. Chi tiết + luật:
`jobpilot/llm/CLAUDE.md` § Provider `claude_cli`.

- Đo thật: system prompt mặc định của Claude Code = **32.198** token/lượt; thay bằng prompt riêng
  → **~1.200**. classify 5/5, intake 11/11, tailor Opus qua guardrail ở lượt 2 (71 s). p50 6–8 s.
- **Tôi đoán sai một lần**: bắt `CLAUDE_CODE_OAUTH_TOKEN` vì nghĩ launchd không đọc được keychain.
  User hỏi "sao không chạy claude như terminal?" → thử từ một LaunchAgent thật: login dùng được.
  Token thành tuỳ chọn. **Thử trước khi thêm bước cho user.**
- **Review gate:** APPROVE + 3 nên sửa, đã sửa: system prompt (= Master CV) ra khỏi argv
  (`--system-prompt-file`, đã thử thật); `encoding="utf-8"`; **$0 chỉ đúng với login gói** ⇒
  `subscription_problem()` đọc `claude auth status`, chặn Console/Bedrock/chưa login.

1018 test pass.

## Phase multi-kw — nhiều từ khoá một lượt crawl + crawl lại y hệt (2026-10-04)

User hỏi gõ nhiều keyword thì sao — trước đó cả ô là **một** cụm tìm, nhiều từ ⇒ ít kết quả hơn
(board hiểu là AND) và TopCV ra 0 vì query thành slug. Thêm: dấu phẩy = nhiều lượt tìm trong một
run; và "crawl lại y hệt" 3 cấu hình gần nhất. Luật + bẫy: `jobpilot/crawler/CLAUDE.md` § Nhiều từ khoá.

- Thật: `java, react` × itviec+arbeitnow × 5/site → java +1, react +2, trùng giữa hai từ đếm
  `updated`. Bấm crawl lại → Run 178 ghi `request` **giống hệt** Run 177; `/crawl/recent` gộp hai
  lượt đó làm một. 9 từ khoá → 422; UI chặn nút + báo. Run cũ (trước tính năng) đọc ngược được.
- Bẫy React đã tránh: guard "Crawl lại" là `useRef`, không phải state (`web/src/CLAUDE.md`).

## Fix guard-numbers — con số bịa lọt qua guard của tailor và cover letter (2026-10-12)

Lộ ra khi rà tài liệu để public repo: `SKILL.md` viết luật không bịa "được ép bằng hình dạng dữ
liệu", reviewer thử thật và `check_plan` trả `ok` cho một `summary` viết "improved throughput by
40% and led a team of 12 engineers". Lớp lexical bắt đầu mọi token bằng chữ cái nên **không bao
giờ nhìn thấy một con số**. Docstring của `edit_guard` còn ghi lỗ này "survivable in tailoring,
where the schema forbids writing such a sentence at all" — sai, vì `summary` là chữ tự do. Cover
letter (300 từ văn xuôi, gửi cho nhà tuyển dụng) có đúng lỗ đó.

- **Sửa:** phần kiểm con số của `edit_guard` chuyển lên `tailor/guard.py` thành `numbers_in` /
  `master_text` / `unknown_numbers`, dùng chung cho ba nơi: edit Master, `summary` của tailor,
  và cover letter. Một cách đếm, không fork — hai bản song song sẽ lệch nhau.
- **Nguồn được phép:** tailor = con số Master CV có ghi (section, ngày tháng, chức danh + quote
  ở header). Letter = thêm số trong **tên công ty**; `learning_note` thêm số trong requirement
  `MISSING`.
- **Review gate bắt một lỗ trong chính bản sửa:** bản đầu cho letter dùng cả số trong `job.title`
  và `job.location`. Title "Java Developer (5+ years)" ⇒ thư viết "5+ years" qua guard; địa chỉ
  "12 Ton Dan" ⇒ "a team of 12" qua guard. Và đường email là nơi không ai đọc thư trước khi gửi.
  Lý do mình ghi trong comment còn sai cả hai ví dụ: "Engineer II" không có chữ số nào, còn "Web3"
  vẫn bị lớp lexical chặn. **Một ngoại lệ thêm vào guard thì phải thử bằng input ác ý trước.**
- Cùng lượt review: retry của tailor nhắc luật *công nghệ* cho vi phạm *con số* (cả hai câu đều
  bắt đầu bằng "summary") ⇒ tách key `_REMEDIES`; prompt của letter đưa nguyên "3+ years of Java"
  làm bằng chứng ⇒ thêm câu nói số trong requirement là lời nhà tuyển dụng; và "over one year" là
  cách model viết lại "1+ years" sau khi bị chặn ⇒ *one..ten* trước đơn vị giờ được tính là số.
- **Thử trên dữ liệu thật (chỉ đọc):** 2 plan tailor đang lưu, 1 cái bị luật mới từ chối vì
  "1+ years" — thâm niên model **tự tính từ ngày tháng**, CV không ghi số
  đó. Giữ luật chặt: đây đúng là suy diễn, và muốn có câu đó thì ghi vào Master. Prompt giờ nói rõ
  điều này để khỏi tốn một vòng retry.
- **Chạy thật:** `llm bench --task tailor --limit 2` trên `claude_cli` / Opus → 2/2 qua guardrail
  ngay vòng đầu.
- **Giới hạn còn lại** (ghi ở `SKILL.md §0`): luật kiểm *có mặt*, không kiểm *ngữ cảnh* (CV có
  "5 members" thì "5 years" vẫn qua); *one..ten* viết bằng chữ chỉ được kiểm khi đứng trước đơn
  vị; số viết bằng chữ tiếng Việt và **tên tháng** không được kiểm; văn xuôi không số thì không
  lớp nào kiểm.
- **Letter chạy thật** (4 lượt sinh thư trên 2 job có plan, `claude_cli` / Opus, không lưu gì
  ngoài `llm_calls`): luật con số **không từ chối lượt nào**; mọi con số trong thư cuối đều là số
  CV có ghi. Thứ từ chối lại là lớp lexical **cũ**: một thư bị chặn hai lần vì chữ **"December"**
  — viết hoa giữa câu nên heuristic coi là tên sản phẩm, trong khi CV ghi "Dec. 2024". Lỗi có từ
  trước, và trên đường email nó làm hỏng cả đơn. Thêm **tháng** vào `_ALLOWED_TERMS` (thứ thì
  không: review chỉ ra "Monday" là monday.com, một sản phẩm có thật trên CV); chạy lại:
  một thư qua vòng đầu, một thư qua sau một retry (vì nhắc Kotlin — đúng việc của guard).
- **Vẫn chưa có bench cho letter.** 4 lượt trên là chạy tay; `llm_calls` không ghi *lý do* một
  vòng bị từ chối, nên muốn biết luật nào chặn phải bọc `check_letter` như lần này.

1046 test pass.
