# CLAUDE.md

Hướng dẫn cho Claude Code khi làm việc trong repo này.

## Repo là gì

Hai lớp:
1. **CV Template** — bộ khung LaTeX [Awesome-CV](https://github.com/posquit0/Awesome-CV) (`awesome-cv.cls`, `fontawesome.sty`, `fonts/`), build bằng Docker. Repo **chỉ chứa khung**, không chứa CV nào.
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
3. **Không commit thông tin cá nhân**: Master CV sống trong bảng `cv_versions` của Postgres, ra/vào qua API (`GET/PUT /cv/{scope}`). Repo không chứa CV nào — DB mới thì `ensure_master()` tạo **CV rỗng** (`cv/skeleton.py`), user tự điền trong CV Studio hoặc `jobpilot cv import <file.json>`. `cv/sample.py` là CV **hư cấu** chỉ dùng cho test + demo, app không bao giờ seed từ đó.
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
4. **Push git** — commit (Conventional Commits) + push. Chỉ push **sau khi review approve và user đồng ý**.
5. **Tiếp phase sau.**

Ràng buộc:
- **Không tự merge/nhảy phase** khi chưa có approve.
- Mỗi phase = 1 (hoặc vài) commit gọn, message rõ; kết thúc phase mới push.
- Branch làm việc: `feat/jobpilot` (giữ `main` sạch), trừ khi user yêu cầu khác.
- Sau mỗi phase: ghi chi tiết vào `PHASES.md`, thêm 1 dòng vào bảng "Trạng thái hiện
  tại" bên dưới, cập nhật "Nợ kỹ thuật" nếu có gì đổi.
- **Luật mới thuộc về một vùng code thì viết vào `CLAUDE.md` của vùng đó**, không viết vào
  file gốc. File gốc chỉ giữ thứ cần biết *trước khi* biết mình sẽ đụng thư mục nào: nguyên
  tắc, quy trình, commands, conventions, bài học xuyên suốt. **Giữ file gốc dưới 40k ký tự**
  — `/doctor` đếm CRLF là 2 ký tự nên nó luôn báo cao hơn `wc -m`; lấy số của `/doctor`.

## Commands

### Build CV (Master hoặc tailored)
```bash
# Windows PowerShell (tại thư mục chứa cv.tex)
docker run --rm -v ${PWD}:/work csmith/awesome-cv-builder
# Linux/macOS/WSL
docker run -u $UID:$GID --rm -v $PWD:/work csmith/awesome-cv-builder
# Output: cv.pdf
```

### JobPilot (khi đã scaffold — xem cấu trúc ở PLAN.md §8)
```bash
# --- Postgres: dùng bản cài sẵn trên máy (PostgreSQL 17 + pgAdmin 4) ---
# Tạo DB một lần:  psql -U postgres -c "CREATE DATABASE jobpilot;"
# rồi đặt trong .env:  DATABASE_URL=postgresql+psycopg://postgres:<pass>@127.0.0.1:5432/jobpilot
# (Hoặc `docker-compose up -d postgres` nếu muốn chạy Postgres trong Docker.)
alembic upgrade head                # migrate DB — tạo schema `jobpilot`
uvicorn jobpilot.api.main:app --reload   # API backend (REST + WebSocket) tại :8000
cd web && npm run dev               # Web Dashboard (Vite) tại :5173  ← control plane chính
python -m jobpilot.cli crawl        # crawl các nguồn đang bật → Postgres
python -m jobpilot.cli crawl --query "java spring" --limit 50   # scope 1 lần chạy
                                    # query NGẮN thôi: nó thành slug ở từng site,
                                    # "java spring boot backend" → TopCV 0 job.
                                    # `crawl.max_pages` (mặc định 5) quyết định đi thêm
                                    # bao nhiêu trang. Hoặc dùng card "Crawl setup" ở trang Runs.
python -m jobpilot.cli backfill     # gắn quality signal + facet phân tích cho job cũ (idempotent)
python -m jobpilot.cli backfill --force   # tính lại cả row đã có — dùng sau khi SỬA parser
python -m jobpilot.cli cv seed      # tạo Master CV rỗng nếu chưa có (idempotent)
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
python -m jobpilot.cli slack        # (tùy chọn) Slack Bolt — kênh phụ; cần API đang chạy
pytest jobpilot/tests               # test
# tất cả trong 1 lệnh:
make dev
```

## Conventions

- **Ngôn ngữ code/comment**: English. Docs cho user (PLAN/SKILL/PHASES) có thể tiếng Việt.
  **Mọi thứ đẩy lên GitHub thì English**: commit message, PR title, PR description, issue.
  Ranh giới là *ai đọc*: `PHASES.md` là nhật ký cho mình, PR là thứ public.
- **Python**: 3.11+, type hints, `ruff`/`black` nếu có. Mỗi scraper kế thừa `crawler/base.py:BaseScraper`.
- **LaTeX**: giữ cú pháp Awesome-CV; dùng macro có sẵn `\tech{}`, `\techfe{}`, `\cvsimpleentry`, `\cvitems`. Đổi màu chủ đạo trong CV Studio (`theme.color`), không sửa `.tex` tay.
- **Job schema**: mọi scraper phải normalize về `Job` schema chung (PLAN.md §3.1) để dedup theo `id = "<source>:<native_id>"`.
- **State**: **Postgres là nguồn sự thật duy nhất**; mọi thay đổi trạng thái đi qua API backend (Web và Slack cùng gọi API → không lệch state). Orchestrator idempotent (chạy lại không hỏng). Đẩy update realtime qua WebSocket (web) + update message (Slack).
- **Web/Frontend**: React + Vite + TS + TailwindCSS + shadcn/ui; charts theo skill `dataviz`, UI theo skill `frontend-design` (palette nhất quán light/dark, có cá tính riêng). Bind `localhost`, không expose ra ngoài. DB migrations bằng Alembic — đổi schema phải tạo migration, không sửa tay.
- **CV inline markup**: text trong `CvDocument` **không bao giờ** chứa LaTeX thô. Dùng subset markdown: `**bold**` → `\textbf`, `` `x` `` → `\tech`, `~x~` → `\techfe`, `[label](url)` → `\hreficon`. Mọi thứ còn lại được escape (`jobpilot/cv/latex.py`). Agent tailor (Phase 5) phải xuất đúng subset này.
- **CV data flow (quan trọng)**: nguồn sự thật là **JSON structured** (CV Studio + agent tailor cùng dùng) → serialize ra `.tex` qua Jinja2 → Docker build PDF. Không sửa `.tex` tailored bằng tay ngoài luồng này (trừ raw-mode trong Studio, có cảnh báo mất round-trip). Mọi lần save = 1 row `cv_versions` (author = user|agent).
- **Verify thay đổi runtime**: sau khi sửa scraper/tailor/apply, chạy thử flow tương ứng và quan sát output thật, đừng chỉ dựa vào test. Sau khi sửa template Jinja2 hoặc `cv/latex.py` phải build lại PDF để chắc không lỗi LaTeX.

## Trạng thái hiện tại

Roadmap `PLAN.md §9` **đã xong** (Phase 0 → 15); roadmap mở rộng **§9.1 (Phase 18 → 25)** đang
chạy — 18–20c xong. Nhật ký chi tiết từng phase nằm ở **`PHASES.md`**: đọc phần tương ứng trước
khi đụng vào một vùng code lần đầu. Mục "Nợ kỹ thuật" bên dưới là phần **còn đang áp dụng**.

| Phase | Nội dung | Code |
|---|---|---|
| 0–2 | scaffold; build wrapper Docker LaTeX; models + Alembic + FastAPI skeleton | `store/`, `api/`, `alembic/` |
| 3 | crawler framework (pure `search_url`/`parse_*`, robots, rate-limit, dedup) + ITviec | `crawler/base.py`, `pipeline.py`, `persist.py` |
| 4 | Web Dashboard: jobs/funnel/charts + realtime WS | `web/`, `api/main.py` |
| 4.5 | CV Studio: JSON `CvDocument` → Jinja2 `.tex` → Docker PDF, `cv_versions` append-only | `cv/` |
| 5 | Tailor engine **index-based** + guardrail chống bịa (structural + lexical) + CV Review | `tailor/` |
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

690 test pass. Đã verify trên môi trường thật: Alembic lên **PostgreSQL 17 local**, 8 trang web,
Docker LaTeX build (Master + tailored), crawl 6+ nguồn qua API + Postgres, `llm_calls` +
`GET /stats/llm` + `llm bench`. **Cả ba provider đã gọi thật thành công** cho cả schema phẳng
(`MailVerdict`) lẫn schema lồng (`TailorPlan`), kể cả OpenAI strict mode — classify 5/5 trên
6 model, tailor 2/2 qua guardrail vòng đầu. Trang `/models` đổi model từ UI ghi xuống
`config.local.yaml` và CLI chạy đúng backend mới.

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
- **CV Studio còn thiếu**: HTML live preview, theme gallery. Diff 2 version bất kỳ **đã có** (Phase 16) — dùng chung `tailor/diff.py` với CV Review, chỉ khác bộ chữ (`VERSION_LABELS` vs `TAILOR_LABELS`). Thêm loại so sánh mới = thêm một `DiffLabels`, **đừng fork hàm diff**: hai bộ luật song song sẽ lệch nhau lúc nào không biết.
- **Cần `pip install -e '.[cv]'`** cho `pypdf`, nếu không page count trả `None` (badge "1 trang" biến mất, không còn cảnh báo CV tràn 2 trang). Build PDF vẫn chạy bình thường — chỉ mất phần đếm trang.
- **Queue vẫn 1 worker**: tailor xếp sau một crawl đang chạy sẽ đứng `queued` vài phút. Đúng nghĩa "queued", nhưng nếu thấy vướng thì nâng `max_workers` — task body đã mở session riêng nên an toàn về mặt DB.
- **Slack đã verify thật** (2026-08-08): cần đúng **một** scope `chat:write`, Socket Mode +
  app-level token `connections:write`, bật **Interactivity** (quên thì tin nhắn vẫn hiện mà bấm
  nút im lặng), và `/invite @jobpilot` vào channel. Lỗi hay gặp: channel **riêng tư** mà bot chưa
  được mời trả `channel_not_found`, không phải `not_in_channel` — hai lỗi đó phân biệt public/private.

## Quyết định đã chốt (không tự đổi nếu user không yêu cầu)

- Apply = **hybrid theo kênh** (email full-auto, portal/LinkedIn human-in-the-loop).
- Nguồn = **ITviec + TopCV + VietnamWorks** lõi (pluggable, mở rộng theo tier — PLAN.md §5.1.1); không LinkedIn/Facebook.
- Giao diện = **Web Dashboard local** là chính, **Slack** phụ. DB = **PostgreSQL**.
- Chạy = **local**, tay hoặc cron nhẹ.
- Stack = Python (FastAPI + Playwright stealth + Docker LaTeX) + React(Vite/TS/Tailwind/shadcn) + PostgreSQL + slack-bolt.
- LLM = **Claude mặc định**, openai/gemini chọn được **theo từng việc** (`llm.*`, Phase 20b). Không chạy model local.
