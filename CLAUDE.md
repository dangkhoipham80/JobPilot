# CLAUDE.md

Hướng dẫn cho Claude Code khi làm việc trong repo này.

## Repo là gì

Hai lớp:
1. **CV Template** — bộ khung LaTeX [Awesome-CV](https://github.com/posquit0/Awesome-CV) (`awesome-cv.cls`, `fontawesome.sty`, `fonts/`), build bằng tectonic. Repo **chỉ chứa khung**, không chứa CV nào.
2. **JobPilot (đang xây)** — agent crawl job (ITviec/TopCV/VietnamWorks) → quản lý qua **Web Dashboard local** (control plane chính; Slack là kênh phụ) → tailor CV → duyệt/sửa → apply hybrid. Stack: FastAPI + React + PostgreSQL. Xem `PLAN.md` (kiến trúc) và `SKILL.md` (logic tailor).

## Đọc trước khi làm

- `PLAN.md` — kiến trúc, data model, roadmap, quyết định đã chốt.
- `SKILL.md` — quy tắc tailor CV, **guardrail chống bịa**.
- `PHASES.md` — nhật ký từng phase (quyết định + bug chỉ lộ ra khi chạy thật). Đọc
  phần của vùng code mình sắp đụng, không cần đọc hết.
- File này — commands + conventions + luật xuyên suốt.

**Luật theo vùng code nằm ở `CLAUDE.md` trong chính thư mục đó** — Claude Code nạp chúng
**on-demand** khi đọc file trong thư mục, nên chúng không tốn context của mọi session:

| File | Nội dung |
|---|---|
| `jobpilot/crawler/CLAUDE.md` | thêm site mới, robots, nguồn tier-2 đã loại, LinkedIn alerts, bẫy selector/fetch |
| `jobpilot/cv/CLAUDE.md` | thêm template mới (thư mục + `template.json`), macro bắt buộc, bẫy Jinja/LaTeX; nhập CV từ ảnh/PDF (không tự lưu, 3 trạng thái kiểm) |
| `jobpilot/intake/CLAUDE.md` | dán JD → AI đọc + chấm độ khớp; JD lưu là bản của user, 3 loại `match_score` |
| `jobpilot/companies/CLAUDE.md` | fold tên nhà tuyển dụng (hướng gộp nhầm là hướng nguy hiểm), HR contact, `apply_target` ai nói ra thì thắng |
| `jobpilot/llm/CLAUDE.md` | chọn provider/model theo việc, schema từng provider, đo chi phí, scrub key |
| `jobpilot/api/CLAUDE.md` | hợp đồng phân trang `Page{items,total,…}`, `ORDER BY` unique, cap 200 |
| `jobpilot/apply/CLAUDE.md` | outcome (`current` vs `reached`), inbox sync, cover letter PDF |
| `jobpilot/analytics/CLAUDE.md` | facet + `covered`/`total`, parse lương, `posting_calendar` |
| `web/src/CLAUDE.md` | màu/chart, bẫy React (`useRef` guard, JSONB optional-chain), phân trang FE |

⚠️ Sau `/compact`, file gốc được nạp lại nhưng **file lồng thì không** — chúng chỉ quay lại khi
Claude đọc lại file trong thư mục đó. Session dài đụng nhiều vùng thì mở lại file tương ứng.

## Nguyên tắc bắt buộc (đọc kỹ)

1. **Truthfulness**: khi tailor CV, KHÔNG bịa skill/kinh nghiệm/metric. Chỉ nhấn mạnh/diễn đạt lại dữ kiện có thật. Chi tiết: `SKILL.md §0`.
2. **Human-in-the-loop**: mọi hành động gửi ra ngoài cần user Approve, trừ kênh **email** đã bật rõ. **Không** auto-apply LinkedIn. **Không** scrape LinkedIn.
3. **Không commit thông tin cá nhân** (repo **public**): Master CV sống trong bảng `cv_versions` của Postgres, ra/vào qua API (`GET/PUT /cv/{scope}`). Repo không chứa CV nào — DB mới thì `ensure_master()` tạo **CV rỗng** (`cv/skeleton.py`), user tự điền trong CV Studio, nhập từ ảnh/PDF ở đó, hoặc `jobpilot cv import <file.json>`. `cv/sample.py` là CV **hư cấu** chỉ dùng cho test + demo, app không bao giờ seed từ đó.
4. **Không ghi đè Master CV**: bản tailored sinh ra ở `out/cv/<scope>/`, Master trong DB giữ nguyên.
5. **Tôn trọng ToS/robots.txt/rate-limit** khi crawl. Site nào fail thì log + chạy tiếp, không retry vô hạn.
6. **Secrets**: mọi token (Slack, Claude API, email) đặt trong `.env` (đã gitignore). Không log, không commit token, không commit `jobpilot.db`.

## Quy trình triển khai (phase-by-phase + Review gate)

Triển khai theo phase trong `PLAN.md §9`. **Mỗi phase là một vòng khép kín:**

1. **Implement** trọn vẹn 1 phase (theo scope PLAN.md), verify chạy được (không chỉ dựa test).
2. **Summary for review** — *Scope* (phase nào, mục tiêu) / *Changes* (file thêm/sửa + vai trò) /
   *Key decisions* (quyết định + lý do) / *How to verify* (lệnh + kết quả kỳ vọng) /
   *Risks / follow-ups*.
3. **Review gate** — chạy subagent `phase-reviewer` trên diff, kèm summary bước 2 làm context.
   Nó review **độc lập** trên `git diff` thật, không chỉ đọc summary, và **không tự sửa code,
   không tự push** — chỉ ra verdict, quyền quyết định vẫn ở user.
   ✅ **APPROVE** → sang bước 4. ❌ **CHANGES REQUESTED** → sửa theo finding, quay lại bước 2.
4. **Push git** — commit (Conventional Commits) + push nhánh + mở **pull request** vào `main`. Chỉ push **sau khi review approve và user đồng ý**. `main` được bảo vệ: không push thẳng được, PR chỉ merge khi check `backend` + `frontend` xanh.
5. **Tiếp phase sau.**

Ràng buộc:
- **Không tự merge/nhảy phase** khi chưa có approve.
- Mỗi phase = 1 (hoặc vài) commit gọn, message rõ; kết thúc phase mới push.
- Branch làm việc: **nhánh riêng từ `main`** cho mỗi việc (`feat/…`, `fix/…`, `docs/…`, `chore/…`), vào `main` qua PR. Không commit lên `main`.
- **Repo public (2026-10-12).** Mọi thứ push lên — commit, nhánh, nội dung PR, log Actions — ai cũng đọc được. Soát nguyên tắc 3 và 6 **trước** khi commit, không phải trước khi push.
- Sau mỗi phase: ghi chi tiết vào `PHASES.md`, thêm 1 dòng vào bảng "Trạng thái hiện
  tại" bên dưới, cập nhật "Nợ kỹ thuật" nếu có gì đổi.
- **Luật mới thuộc về một vùng code thì viết vào `CLAUDE.md` của vùng đó**, không viết vào
  file gốc. File gốc chỉ giữ thứ cần biết *trước khi* biết mình sẽ đụng thư mục nào: nguyên
  tắc, quy trình, commands, conventions, bài học xuyên suốt. **Giữ file gốc dưới 40k ký tự**
  — `/doctor` đếm CRLF là 2 ký tự nên nó luôn báo cao hơn `wc -m`; lấy số của `/doctor`.

## Commands

### Build CV (Master hoặc tailored)
```bash
# Engine duy nhất: tectonic (một binary tĩnh, không cần daemon). Tại thư mục chứa cv.tex:
tectonic -X compile cv.tex
# Output: cv.pdf
```
**Engine Docker đã gỡ (2026-10-04)** — `cv.engine: docker` còn sót trong config sẽ ra `BuildError`
nói rõ điều đó. Tìm tectonic theo thứ tự **PATH → `tools/` trong repo** (thư mục này đã gitignore),
nên **thả binary vào `tools/` là xong, không cần config gì**. `cv.tectonic_bin` vẫn dùng được nhưng
một đường dẫn tuyệt đối chỉ đúng trên một máy. Luật + bẫy ở `jobpilot/cv/CLAUDE.md`.

### JobPilot (khi đã scaffold — xem cấu trúc ở PLAN.md §8)
```bash
# --- Postgres: dùng bản cài sẵn trên máy (PostgreSQL 17 + pgAdmin 4) ---
# Tạo DB một lần:  psql -U postgres -c "CREATE DATABASE jobpilot;"
# rồi đặt trong .env:  DATABASE_URL=postgresql+psycopg://postgres:<pass>@127.0.0.1:5432/jobpilot
# (Hoặc `docker-compose up -d postgres` nếu muốn chạy Postgres trong Docker.)
alembic upgrade head                # migrate DB — tạo schema `jobpilot`
uvicorn jobpilot.api.main:app --reload   # API + dashboard đã build, tại :8000
                                    # MỌI route REST/WS nằm dưới /api — xem api/CLAUDE.md.
                                    # Đã `npm run build` thì mở thẳng :8000 là ra dashboard.
cd web && npm run dev               # Vite tại :5173 — chỉ khi đang sửa UI; nó proxy /api
                                    # sang :8000 nên dev cũng same-origin như bản deploy.
python -m jobpilot.cli crawl        # crawl các nguồn đang bật → Postgres
python -m jobpilot.cli crawl --query "java, spring boot" --limit 50   # scope 1 lần chạy
                                    # dấu phẩy = nhiều lượt tìm (tối đa 8), mỗi từ
                                    # NGẮN thôi: nó thành slug ở từng site,
                                    # "java spring boot backend" → TopCV 0 job.
                                    # Lịch tự động đọc `crawl.queries` (Cài đặt).
                                    # `crawl.max_pages` (mặc định 5) quyết định đi thêm
                                    # bao nhiêu trang. Hoặc dùng card "Crawl setup" ở trang Runs.
python -m jobpilot.cli backfill     # gắn quality signal + facet phân tích + link công ty cho job cũ (idempotent)
python -m jobpilot.cli backfill --force   # tính lại cả row đã có — dùng sau khi SỬA parser
python -m jobpilot.cli cv seed      # tạo Master CV rỗng nếu chưa có (idempotent)
python -m jobpilot.cli cv read scan.png -o my-cv.local.json   # AI đọc ảnh/PDF → bản nháp JSON, KHÔNG lưu
python -m jobpilot.cli cv import my-cv.local.json   # nạp CV có sẵn vào DB
python -m jobpilot.cli cv export my-cv.local.json   # backup CV từ DB ra file (gitignored)
python -m jobpilot.cli cv build     # render JSON → .tex → PDF ở out/cv/master/
python -m jobpilot.cli tailor <job_id>            # tailor CV cho 1 job (cần key của provider đang chọn)
python -m jobpilot.cli tailor <job_id> --no-build # chỉ ra plan, không build PDF
python -m jobpilot.cli apply <job_id>             # nộp theo kênh (email/portal/external)
python -m jobpilot.cli apply <job_id> --open-portal   # portal: mở browser pre-fill (không tự submit)
python -m jobpilot.cli confirm-submit <job_id>    # xác nhận đã tự nộp xong (portal/external)
python -m jobpilot.cli llm providers # provider nào đang chạy việc gì, có key chưa, terms ra sao
python -m jobpilot.cli llm stats    # chi phí / tỉ lệ qua guardrail lần đầu / độ trễ, theo backend
python -m jobpilot.cli llm bench --task classify  # chấm trên 5 email có đáp án
python -m jobpilot.cli llm bench --task tailor    # chạy 4 job thật, đếm plan qua guardrail
python -m jobpilot.cli llm bench --task intake    # 3 tin có đáp án, chấm theo FIELD (11 field)
                                    # chỉ đo nửa "trích field", KHÔNG đo nửa "chấm độ khớp"
python -m jobpilot.cli slack        # (tùy chọn) Slack Bolt — kênh phụ; cần API đang chạy
pytest jobpilot/tests               # test
# tất cả trong 1 lệnh:
make dev
```

## Conventions

- **Ngôn ngữ code/comment**: English. Docs cho user (PLAN/SKILL/PHASES) có thể tiếng Việt.
  **Mọi thứ đẩy lên GitHub thì English**: commit message, PR title, PR description, issue.
  Ranh giới là *ai đọc*: `PHASES.md` là nhật ký cho mình, PR là thứ public.
  `README.md` ↔ `README.vi.md` và `CONTRIBUTING.md` ↔ `CONTRIBUTING.vi.md` là **cặp song ngữ**:
  sửa một bên thì sửa luôn bên kia trong cùng commit, không thì hai bản lệch nhau.
- **Python**: 3.11+, type hints, `ruff`/`black` nếu có. Mỗi scraper kế thừa `crawler/base.py:BaseScraper`.
- **LaTeX**: giữ cú pháp Awesome-CV; dùng macro có sẵn `\tech{}`, `\techfe{}`, `\cvsimpleentry`, `\cvitems`. Đổi màu chủ đạo trong CV Studio (`theme.color`), không sửa `.tex` tay.
- **Job schema**: mọi scraper phải normalize về `Job` schema chung (PLAN.md §3.1) để dedup theo `id = "<source>:<native_id>"`.
- **State**: **Postgres là nguồn sự thật duy nhất**; mọi thay đổi trạng thái đi qua API backend (Web và Slack cùng gọi API → không lệch state). Orchestrator idempotent (chạy lại không hỏng). Đẩy update realtime qua WebSocket (web) + update message (Slack).
- **Web/Frontend**: React + Vite + TS + TailwindCSS + shadcn/ui; charts theo skill `dataviz`, UI theo skill `frontend-design` (palette nhất quán light/dark, có cá tính riêng). **uvicorn luôn bind `127.0.0.1`** — ra ngoài chỉ qua `tailscale serve` proxy vào loopback, **không bao giờ** bind `0.0.0.0`, không mở port firewall, không `tailscale funnel`. Bundle chứa token nên tầng mạng mới là auth thật (`jobpilot/api/CLAUDE.md`). DB migrations bằng Alembic — đổi schema phải tạo migration, không sửa tay.
- **Chạy service thì `--workers 1`, không `--reload`.** `TaskQueue` là ThreadPoolExecutor **trong tiến trình** (`orchestrator.py`, bind ở lifespan), nên worker thứ hai = hàng đợi thứ hai + WS manager thứ hai: guard "1 task/1 job" thôi giữ, và progress của task chạy ở worker A không tới dashboard đang nối worker B. Cả hai đều hỏng **im lặng** — `cli serve` vì thế **từ chối** `--workers > 1` thay vì cảnh báo.
- **CV inline markup**: text trong `CvDocument` **không bao giờ** chứa LaTeX thô. Dùng subset markdown: `**bold**` → `\textbf`, `` `x` `` → `\tech`, `~x~` → `\techfe`, `[label](url)` → `\hreficon`. Mọi thứ còn lại được escape (`jobpilot/cv/latex.py`). Agent tailor (Phase 5) phải xuất đúng subset này.
- **CV data flow (quan trọng)**: nguồn sự thật là **JSON structured** (CV Studio + agent tailor cùng dùng) → serialize ra `.tex` qua Jinja2 → LaTeX build PDF (`cv.engine`). Không sửa `.tex` tailored bằng tay ngoài luồng này (trừ raw-mode trong Studio, có cảnh báo mất round-trip). Mọi lần save = 1 row `cv_versions` (author = user|agent).
- **Verify thay đổi runtime**: sau khi sửa scraper/tailor/apply, chạy thử flow tương ứng và quan sát output thật, đừng chỉ dựa vào test. Sau khi sửa template Jinja2 hoặc `cv/latex.py` phải build lại PDF để chắc không lỗi LaTeX.

## Trạng thái hiện tại

Roadmap `PLAN.md §9` **đã xong** (Phase 0 → 17); roadmap mở rộng **§9.1 (Phase 18 → 25)** đang
chạy. Nhật ký chi tiết từng phase nằm ở **`PHASES.md`**: đọc phần tương ứng trước khi đụng vào
một vùng code lần đầu. Mục "Nợ kỹ thuật" bên dưới là phần **còn đang áp dụng**.

⚠️ **Số phase bị trùng — đọc kỹ trước khi kết luận "phase nào tiếp".** Bảng bên dưới ghi theo
`PHASES.md`, mà `PHASES.md` đã **mượn** số 20/20b/20c (model backend) và 21 (trang `/market`)
cho việc khác với thứ `PLAN.md §9.1` cấp cho các ô đó. Đối chiếu thật với code:

| Ô §9.1 | Việc | Tình trạng |
|---|---|---|
| 18, 19 | outcome tracking, inbox sync | ✅ xong |
| **20** | **Analytics thật** — reply/interview rate theo **nguồn·kênh·level**, time-to-first-reply, tin đăng lại | ✅ xong (`analytics/outcomes.py`) |
| **21** | **LLM ranking 2 tầng + dealbreaker** | ❌ **chưa ai làm** — đừng nhầm với `/market` |
| 22–25 | drafter–reviewer, cắt CV 2 trang, interview prep, upskill | ❌ chưa |

`/market` (bảng dưới ghi "21") mô tả **thị trường từ corpus đã crawl**; ô 20 của §9.1 đo **hiệu
quả nộp đơn theo nguồn** — hai thứ khác nhau, đừng gộp. Phase mới thì **tham chiếu theo ô §9.1**,
đừng phát thêm số nguyên mới.

| Phase | Nội dung | Code |
|---|---|---|
| 0–2 | scaffold; build wrapper LaTeX; models + Alembic + FastAPI skeleton | `store/`, `api/`, `store/migrations/` |
| 3 | crawler framework (pure `search_url`/`parse_*`, robots, rate-limit, dedup) + ITviec | `crawler/base.py`, `pipeline.py`, `persist.py` |
| 4 | Web Dashboard: jobs/funnel/charts + realtime WS | `web/`, `api/main.py` |
| 4.5 | CV Studio: JSON `CvDocument` → Jinja2 `.tex` → PDF, `cv_versions` append-only | `cv/` |
| 5 | Tailor engine **index-based** + guardrail chống bịa (structural + lexical; numeric thêm 2026-10-12) + CV Review | `tailor/` |
| 6 | Apply dispatcher (email 3 gate / portal / external) + Applications board | `apply/` |
| 7 | Slack — **client thuần của REST API**, backend không biết gì về Slack | `slack/` |
| 8 | `TaskQueue` 1 worker + trang Runs/Settings (`config.local.yaml` overlay) | `orchestrator.py`, `config.py` |
| 9 | TopCV + VietnamWorks chạy thật; JSON-LD `JobPosting` + nhận diện theo giá trị dùng chung | `crawler/jsonld.py`, `vietnam.py` |
| 10 | Tailor/apply rời request path → **202 + task**; guard 1 task/1 job nằm trong `submit()` | `orchestrator.py`, `tailor/service.py` |
| 11 | Phân trang nhiều trang + `FeedScraper` (RSS/JSON) + WeWorkRemotely/Arbeitnow | `crawler/base.py`, `feed.py` |
| 12 | ATS adapter tier-3 — 1 adapter phủ mọi công ty dùng Greenhouse/Lever | `crawler/ats.py` |
| 13 | Máy đọc được PDF không (text layer, **không chấm điểm**) | `cv/ats.py` |
| 14 | Giải thích `match_score` + cờ chất lượng tin (`no_jd`/`thin_jd`/`stale`/`undated`) | `crawler/quality.py` |
| 15 | Nhắc follow-up sau khi nộp — hiện trên board, **không tự gửi** | `apply/followup.py` |
| 16 | Diff giữa 2 version CV bất kỳ trong CV Studio (dùng lại diff của tailor) | `tailor/diff.py`, `api/routes/cv.py` |
| 17 | Cover letter ra `.tex` → PDF, đính kèm email; text vẫn là bản chính | `apply/letter_pdf.py`, migration 0006 |
| 18 | Chuyện gì xảy ra **sau** khi nộp: replied/interview/offer/rejected + lịch sử | `apply/outcome.py`, migration 0007 |
| 19 | Đọc thư NTD → **đề xuất** outcome, user bấm mới ghi | `apply/inbox.py`, migration 0008 |
| 20 | Thử model chạy local — **đã gỡ ở 20b**, chỉ còn là lịch sử trong `PHASES.md` | — |
| 20b | Một tầng provider: claude/openai/gemini, cảnh báo dữ liệu, **đo chi phí + chất lượng** | `llm/`, migration 0009, `llm/stats.py` |
| 21 | Trang **/market**: nghiên cứu thị trường từ corpus đã crawl + trích lương/skill/city | `analytics/`, `crawler/salary.py`, `skills.py` |
| 20c | Trang **/models**: chọn model theo việc, dashboard giá + credit đã dùng/còn, scrub key | `web/src/pages/Models.tsx`, `llm/redact.py` |
| deploy | FastAPI serve `web/dist` **same-origin** (API xuống `/api`), siết token + khoá gate email, systemd/timer + backup, CI/CD | `api/static.py`, `api/security.py`, `deploy/`, `.github/workflows/ci.yml`, `DEPLOY.md` |
| cv-A | Template thứ hai **`plain`** (ATS-first, bỏ `.cls`) + picker trong Studio; template tự khai `template.json` | `cv/templates/plain/`, `cv/render.py`, `web/src/components/cv/TemplatePicker.tsx` |
| cv-B | Sửa **Master CV** bằng câu lệnh tự nhiên trong CV Studio, guardrail provenance (`source_quote` bắt buộc cho op thêm mới) dùng chung normaliser với inbox sync | `tailor/edit.py`, `tailor/edit_guard.py`, `web/src/components/cv/InstructionBox.tsx` |
| salary | Parser lương: sàn không còn bị báo thành cả hai đầu; hàng rào **"số chỉ là tiền khi được viết như tiền"** (`_LEAD`/`_TRAIL`) áp cho cả 4 nhánh match | `crawler/salary.py`, `analytics/CLAUDE.md` |
| cv-C | Build PDF bỏ phụ thuộc Docker: engine **tectonic** (Docker lúc đó còn là đường lui, gỡ hẳn 2026-10-04); sửa 2 file vendor để tectonic compile được `awesome_cv` | `tailor/build.py`, `fontawesome.sty`, `awesome-cv.cls` |
| i18n | Dashboard **song ngữ Việt/Anh, mặc định Tiếng Việt** — 18 namespace / 796 key, `vi` type theo `keyof en` nên thiếu chuỗi là lỗi `tsc`; ngày giờ + nhãn + trạng thái qua `useFormat()`/`useLabels()`/`useStatuses()` | `web/src/i18n/`, `web/src/i18n/CLAUDE.md` |
| intake | **Dán JD vào → AI đọc + chấm độ khớp.** Task LLM thứ 4 (`intake`); `POST /jobs/intake` điền form (không lưu), `POST /jobs/{id}/fit` chấm CV vs tin (advisory, không đụng CV). Job thêm tay giờ có quality + facet + `match_score` như job crawl | `jobpilot/intake/`, `api/routes/intake.py`, `web/src/components/FitCard.tsx` |
| companies | **Nhà tuyển dụng thành bảng** + `hr_contacts` (migration 0011), `jobs.company_id`, trang `/companies`; email HR **được mời** làm `apply_target` **và đổi luôn `apply_channel` sang email** — cả hai cột **sống qua lượt crawl sau** (`apply_target_source`) | `jobpilot/companies/`, `api/routes/companies.py`, `web/src/pages/Companies.tsx` |
| intake-2 | **JD có cấu trúc** (8 bucket: vai trò/nhiệm vụ/yêu cầu/ưu tiên/soft skill/output/quyền lợi/cách ứng tuyển) — 2 lượt gọi chạy song song, bucket là *mục lục* của JD gốc chứ không thay nó; **lương 4 dạng** (`Salary.kind`); **tỉnh/thành** hết rớt vì hậu tố quốc gia (160→119 job thiếu city); **onsite/hybrid/remote** phủ 105/216 | `intake/schema.py`, `crawler/vietnam.py`, `crawler/salary.py`, `web/src/components/JdSectionsView.tsx` |
| deploy-mac | **Mac mini** thay laptop Windows: 3 LaunchAgent qua `run.sh` (PATH launchd), chạy khi máy bật, DB dựng mới | `deploy/macos/`, `DEPLOY.md §M` |
| crawl-fix | id > 128 ký tự làm đỏ cả crawl → `make_job_id()` + savepoint mỗi job/site, row hỏng = `rejected` | `crawler/types.py`, `persist.py`, `pipeline.py` |
| claude_cli | Provider LLM chạy trên **gói Claude** của user qua `claude -p` (0đ/lượt, chặn nếu login không phải gói) | `llm/claude_cli.py`, `jobpilot/llm/CLAUDE.md` |
| public | **Repo public + MIT** (2026-10-12): `LICENSE` + license của phần vendor, `README.vi.md`, `CONTRIBUTING(.vi).md`, `CODEOWNERS`; `main` được bảo vệ, CI của PR từ fork chờ duyệt | `LICENSE`, `CONTRIBUTING.md`, `.github/CODEOWNERS` |
| cv-import | **Nhập CV từ ảnh/PDF**: model chép file thành bản nháp trong CV Studio, **không tự lưu**; PDF có text layer thì đối chiếu con số; tầng LLM nhận file đính kèm (`Attachment`) ở cả 4 provider | `cv/reader.py`, `cv/importer.py`, `llm/base.py`, `web/src/components/cv/ImportBox.tsx` |
| ats-scope | **Board công ty lọc theo địa điểm** (`ats.locations`, nguyên từ, trước `limit`) + miễn cổng stack cho board đã khoanh vùng (`stack_gated`) | `crawler/ats.py`, `crawler/pipeline.py`, `jobpilot/crawler/CLAUDE.md` |
| multi-kw | **Nhiều từ khoá / 1 crawl** (dấu phẩy, mỗi site chạy hết rồi mới đóng) + **Crawl lại y hệt** 3 cấu hình gần nhất (`Run.stats.request`, `GET /crawl/recent`) | `crawler/pipeline.py`, `components/RecentCrawls.tsx` |

1177 test pass. Đã verify trên môi trường thật: Alembic lên **PostgreSQL 17 local**, 11 trang web,
build PDF bằng **tectonic** (Master + tailored, cả 2 template; Docker từng verify, đã gỡ), crawl 6+ nguồn qua API + Postgres, `llm_calls` +
`GET /stats/llm` + `llm bench`. **Cả ba provider API (claude/openai/gemini) đã gọi thật thành công** cho cả schema phẳng
(`MailVerdict`) lẫn schema lồng (`TailorPlan`), kể cả OpenAI strict mode — classify 5/5 trên
6 model, tailor 2/2 qua guardrail vòng đầu. Trang `/models` đổi model từ UI ghi xuống
`config.local.yaml` và CLI chạy đúng backend mới. UI song ngữ đã đi thật qua Deck/Jobs/CV Studio/
Guide/Market/Settings ở cả VI lẫn EN trên 180 job thật, 0 console error.

**Bài học xuyên suốt** (ca cụ thể ở `PHASES.md`):
- **Test xanh không chứng minh parser đúng.** Mỗi phase crawl đều có bug chỉ lộ ra khi
  chạy thật. Verify qua **Postgres + API thật** rồi *đọc output*, không dừng ở test.
- **Sai dữ liệu *trông như đúng* tệ hơn thiếu dữ liệu.** Param bị site lặng lẽ bỏ qua,
  trang 403 parse thành "hết kết quả", `"remote" in "remote debugging"`, `intern` nằm
  trong `internal`. Cái nguy hiểm luôn là thứ báo cáo thành công.
- ***Không biết* ≠ *hỏng*.** `pages=None` vs `pages=0`, `undated` vs `stale`,
  `spacing_reliable=False` thay vì kết luận PDF lỗi.
- **Đừng để công cụ đo bịa ra finding.** `pypdf` đọc mất dấu cách rồi kết luận CV hỏng —
  PDF chưa bao giờ hỏng, công cụ đo mới hỏng.

### Nợ kỹ thuật còn lại (roadmap PLAN.md §9 đã xong)

> Nợ theo vùng code nằm ở `CLAUDE.md` của vùng đó — crawler (nguồn, robots, selector, fetch)
> ở `jobpilot/crawler/CLAUDE.md`, model backend ở `jobpilot/llm/CLAUDE.md`. Dưới đây là phần
> cắt ngang nhiều vùng.

- **Crawler**: ITviec + TopCV + VietnamWorks + LinkedIn(alerts) + WeWorkRemotely + Arbeitnow chạy thật; chỉ TopDev chưa có scraper. Cần `pip install -e '.[crawler]' && playwright install chromium` (2 nguồn tier-2 **không cần** Playwright). Chi tiết + bẫy: `jobpilot/crawler/CLAUDE.md`.
- **Raw LaTeX đã có** (bẫy preview ở `PHASES.md`): `cv_versions.meta.tex_override` đè cách JSON *serialize*, không thay JSON. **Một chiều** — không gì parse `.tex` về JSON — nên khi nó còn hiệu lực thì sửa field **không tới được PDF**, UI phải nói ra. Lưu document không xoá nó; `rollback` mang nó theo.
- **CV Studio còn thiếu**: HTML live preview, theme gallery. Template thì **đã có 2** (`awesome_cv`,
  `plain`) và thêm cái nữa = thêm một thư mục — luật + bẫy ở `jobpilot/cv/CLAUDE.md`. Diff 2 version bất kỳ **đã có** (Phase 16) — dùng chung `tailor/diff.py` với CV Review, chỉ khác bộ chữ (`VERSION_LABELS` vs `TAILOR_LABELS`). Thêm loại so sánh mới = thêm một `DiffLabels`, **đừng fork hàm diff**: hai bộ luật song song sẽ lệch nhau lúc nào không biết.
- **Build PDF cần `tectonic` trên máy** (một binary tĩnh ~10 MB, không daemon). Không có thì
  `BuildError` chỉ cách cài; `cv.tectonic_bin` trỏ tới binary để ngoài PATH. Engine Docker đã gỡ
  (2026-10-04): image 3.18 GB, chỉ x86-64, và máy chạy thật không có Docker nên đường đó không còn
  ai kiểm. Chi tiết + bẫy khi sửa `.cls`/`.sty`: `jobpilot/cv/CLAUDE.md`.
- **Cần `pip install -e '.[cv]'`** cho `pypdf`, nếu không page count trả `None` (badge "1 trang" biến mất, không còn cảnh báo CV tràn 2 trang). Build PDF vẫn chạy bình thường — chỉ mất phần đếm trang.
- **Queue vẫn 1 worker**: tailor xếp sau một crawl đang chạy sẽ đứng `queued` vài phút. Đúng nghĩa "queued", nhưng nếu thấy vướng thì nâng `max_workers` — task body đã mở session riêng nên an toàn về mặt DB.
- **Slack đã verify thật** (2026-08-08): cần đúng **một** scope `chat:write`, Socket Mode +
  app-level token `connections:write`, bật **Interactivity** (quên thì tin nhắn vẫn hiện mà bấm
  nút im lặng), và `/invite @jobpilot` vào channel. Lỗi hay gặp: channel **riêng tư** mà bot chưa
  được mời trả `channel_not_found`, không phải `not_in_channel` — hai lỗi đó phân biệt public/private.
- **i18n mới phủ frontend.** Chuỗi do **backend soạn** vẫn ra tiếng Anh giữa trang tiếng Việt:
  `facet.note` (Market), `split.note` (Dashboard), `llm.blocker()` (Models), các
  `*_hint` (Applications), `description` của template (CV Studio). **Đừng vá ở frontend** —
  dịch chúng nghĩa là pattern-match chính câu tiếng Anh của mình, mong manh và sai chỗ. Muốn
  phủ hết thì backend phải trả **key + số** (hoặc nhận tham số ngôn ngữ), là một phase riêng.
  **Mẫu đã có**: cảnh báo data-use ở Models đi qua `llm.warning_items()` (policy + task) và
  được dịch ở `i18n/dict/models.ts`; `warnings()` tiếng Anh dựng từ **cùng** items cho CLI.
- **Guard con số kiểm *có mặt*, không kiểm *ngữ cảnh*.** Từ 2026-10-12 `summary` của tailor và cover letter phải qua `guard.unknown_numbers` (letter: nguồn số = Master CV + tên công ty, **không** gồm tên job hay địa chỉ) (trước đó một summary bịa "improved throughput by 40%" đi qua guard). Luật là "con số này có trong Master CV không", nên CV ghi "5 members" thì "5 years" vẫn qua; và câu văn xuôi không số, không tên công nghệ thì không lớp nào kiểm. Bước user đọc diff vẫn là chốt cuối. Giới hạn đầy đủ ở `SKILL.md §0`.
- **`guard._NUMBER_WORDS` chỉ có tiếng Anh** và `_WORD_RE` là `[a-zA-Z]+`, nên số bịa viết
  bằng chữ tiếng Việt ("mười hai", "gấp đôi") lọt qua — chữ **số** thì vẫn bị bắt, và provenance
  (`textnorm.quote_appears_in`) xử lý tiếng Việt đúng + fail-closed. Vì lỗ này mà ba chip gợi ý
  trong `InstructionBox` **cố ý giữ tiếng Anh ở cả hai ngôn ngữ** (lý do đầy đủ ở `i18n/dict/cv.ts`).

## Quyết định đã chốt (không tự đổi nếu user không yêu cầu)

- Apply = **hybrid theo kênh** (email full-auto, portal/LinkedIn human-in-the-loop).
- Nguồn = **ITviec + TopCV + VietnamWorks** lõi (pluggable, mở rộng theo tier — PLAN.md §5.1.1); không LinkedIn/Facebook.
- Giao diện = **Web Dashboard** là chính, **Slack** phụ. DB = **PostgreSQL**.
- Mã nguồn = **public trên GitHub, MIT** (2026-10-12). CV thật không được vào git. Chỉ user có quyền ghi, nên mọi PR từ người ngoài đều qua tay user.
- Chạy = **Mac mini ở nhà + Tailscale** (2026-10-04, `DEPLOY.md §M`): LaunchAgent, **chỉ chạy khi
  máy bật** (user chốt), IP dân dụng VN. Bên dưới là quyết định VPS cũ — vẫn là phương án B.
- (cũ) Chạy = **VPS Việt Nam (~100k/tháng) + Tailscale**, service 24/7 + systemd timer cho crawl.
  Đổi từ "local trên laptop" (2026-08-17) vì laptop là thứ mang đi, mà mang đi thì
  JobPilot offline. **Vẫn không phải public**: uvicorn bind loopback, ra ngoài chỉ qua
  tailnet — xem `DEPLOY.md §0` trước khi đụng vào chuyện phơi ra ngoài.
  VPS đặt ở **VN** vì ITviec/TopCV/VietnamWorks sau Cloudflare, IP datacenter nước ngoài
  bị challenge nhiều hơn; đường lui nếu vẫn bị chặn: crawl ở laptop, DB ở VPS, chỉ đổi
  `DATABASE_URL` (`DEPLOY.md §7`). Kiến trúc nào cũng được (x86-64 hoặc ARM64) vì build PDF
  dùng **tectonic**.
- Stack = Python (FastAPI + Playwright stealth + tectonic LaTeX) + React(Vite/TS/Tailwind/shadcn) + PostgreSQL + slack-bolt.
- LLM = **Claude mặc định**, openai/gemini chọn được **theo từng việc** (`llm.*`, Phase 20b). Không chạy model local.
  Từ 2026-10-04 có thêm **`claude_cli`** = Claude qua gói Pro/Max của user (đang được chọn trên
  Mac mini) — chỉ dùng cá nhân; gãy thì đổi về `claude` trên `/models`.
- Việc LLM = **4 task**: `intake` (đọc JD dán vào + chấm độ khớp), `tailor`, `letter`, `classify`.
  Danh sách chuẩn ở `llm.TASKS` — thêm task thì sửa **một** tuple đó, đừng viết lại literal
  (`cli llm providers`, `cli llm stats`, `GET /stats/llm` và trang `/models` đều đọc nó).
