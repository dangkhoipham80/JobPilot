# `jobpilot/api/` — REST + WebSocket + dashboard tĩnh

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Phần frontend của phân trang (`usePaging`, `useClampPage`) ở `web/src/CLAUDE.md`.
> Cách deploy lên VPS ở `DEPLOY.md`.

### Same-origin + prefix `/api` — đọc trước khi thêm route

- **Mọi route REST và cả WebSocket nằm dưới `/api`** (`main.API_PREFIX`). Bắt buộc, không
  phải thẩm mỹ: dashboard là client-side router phục vụ trang ở `/jobs`, `/cv`, `/settings`,
  `/applications` — **đúng những path API đang trả JSON**. Chung origin mà không có prefix thì
  F5 ở `/jobs` ra một mảng JSON thay vì trang. Route mới → nhớ prefix, đừng đăng ký ở root.
- **`static.mount_spa` phải mount SAU CÙNG** và tự suy ra `api_roots(app)` từ các route đã
  đăng ký. Catch-all phải trả **404 JSON** cho path thuộc API: nếu để nó rơi vào `index.html`,
  `GET /api/stats/typoo` trả **200 + HTML**, và fetch đang chờ JSON báo
  `unexpected token '<'` thay vì "không có endpoint đó". Lỗi báo sai chỗ là lỗi tốn cả buổi.
- **`TestClient` không áp `base_url` cho `websocket_connect`** (Starlette hardcode
  `urljoin("ws://testserver", url)`), nên `conftest.api_client()` chỉ lo phần HTTP; test WS
  phải tự viết `/api/ws`. Đừng "sửa" helper cho WS — nó không đọc `base_url`.
- **`/health` đăng ký ở CẢ `/health` lẫn `/api/health`** — uptime monitor muốn cái ngắn,
  client prefix mọi thứ muốn cái kia, không bên nào cần biết chuyện của bên nào.
- **Slack client base là `http://127.0.0.1:8000/api`** (`slack/client.DEFAULT_BASE`). Bỏ
  `/api` là nó nhận HTML rồi chết ở `json.decode`, chứ không phải 404 dễ đọc.

### Auth — token này KHÔNG phải thứ chặn người ngoài

- **Token bị Vite nướng cứng vào bundle** (`web/src/lib/api.ts`, thay tĩnh lúc build). File
  tĩnh phải tải được *trước khi* kịp hỏi credential, mà chính nó chứa token ⇒ ai mở được trang
  thì `grep` ra token. **Tầng mạng (Tailscale) mới là auth thật**; token chỉ chặn caller lạc
  cùng máy. Hệ quả bắt buộc nhớ: **đừng bao giờ `tailscale funnel` hay mở port 8000 ra
  Internet** — làm vậy là biếu không CV, Gmail app password, LLM key và một con bot gửi mail
  nhân danh user. Muốn public thì phải làm login server-side thật trước, đó là phase riêng.
- **Token < 20 ký tự thì app từ chối khởi động** (`security.check_api_token`, gọi trong
  `lifespan`). Đặt ở `lifespan` chứ không phải `create_app` là có lý do: build app cũng là
  việc test suite làm, và một checkout chưa có `.env` vẫn phải chạy được test — thứ nó không
  được phép làm là **lắng nghe**. Ngưỡng 20 còn để token tự vượt sàn 12 ký tự của
  `llm/redact.py`, nếu không nó không bị scrub khỏi log.
- **So token bằng `security.token_matches`** (`hmac.compare_digest`), không bao giờ `!=`.
  Cả REST lẫn WS dùng chung một hàm để hai đường không lệch luật.
- **Token WS đi trong FRAME ĐẦU TIÊN, không phải query string.** Query string nằm trong
  request line ⇒ access log của uvicorn/mọi proxy ghi thẳng ra đĩa, còn dính vào history và
  `Referer`. Có test ghim rằng đường `?token=` cũ **không** còn dùng được — để nó chạy song
  song là vá mà vẫn rò.
- **Socket được `accept()` rồi mới auth, nhưng chỉ `manager.subscribe()` SAU KHI auth xong.**
  Phải accept mới đọc được frame; nhưng subscribe sớm là mọi `job_updated` chảy sang một
  socket chưa chứng minh được nó là ai.

### Setting nào KHÔNG được sửa qua HTTP

- **3 gate email khoá cứng** (`config.LOCKED_SETTINGS`: `apply.email.enabled`, `dry_run`,
  `test_recipient`) — `PUT /settings` trả **403**. Đây là đường ngắn nhất từ "token bị rò" tới
  "server gửi mail cho người lạ nhân danh user"; mọi setting khác chỉ là preference, ba cái này
  quyết định máy có được nói thay mình không. Sửa bằng cách **sửa file trên host rồi restart**.
- **Chỉ chặn khi giá trị THAY ĐỔI, không chặn khi chỉ có mặt.** Trang Settings lưu nguyên cả
  section nên lần nào cũng gửi kèm 3 field này; chặn cả no-op thì card không lưu nổi và ai cũng
  học cách đi vòng. Gửi lại đúng giá trị đang có thì cho qua.
- **`GET /settings` trả thêm `locked`** để UI render read-only. Một switch bấm được rồi mới báo
  lỗi lúc save dạy user rằng trang này không đáng tin; một switch xám tự nó giải thích.

### Phân trang — đọc trước khi thêm một list endpoint

- **Mọi list endpoint trả `Page{items, total, limit, offset}`** (`api/schemas.Page`), không
  bao giờ mảng trần: 25/25 và 25/900 là **cùng một mảng** trên đường truyền, nên không có
  `total` thì UI phải đoán bằng `items.length === limit` — sai đúng lúc tổng là bội số của
  page size. Client phải đọc `.items` (Slack có `_items()` bọc sẵn).
- **`ORDER BY` phải kết thúc bằng một cột UNIQUE.** `LIMIT/OFFSET` trên thứ tự có tie là bug
  **im lặng**: dòng bằng nhau ra thứ tự khác nhau giữa trang 1 và trang 2 ⇒ một dòng hiện hai
  lần, một dòng không bao giờ hiện. Ở corpus này `posted_at` **null** với mọi LinkedIn alert nên
  tie là mặc định, không phải ngoại lệ. `paging.page_query()` **raise** nếu thiếu `ORDER BY`.
- **`total` đếm bằng subquery của chính statement đã lọc** (`paging.total_for`), không dựng
  lại `where` bằng tay — dựng lại là cách `total` trôi khỏi thứ nó đếm rồi mời user sang một
  trang trống.
- **`MAX_PAGE_SIZE=200` cho tất cả**, vượt là **422**. Endpoint không cap là DoS vào chính
  dashboard của mình (`/applications` từng không có cap).
- **Board Applications: mỗi cột một query `?result=<stage>`.** Lọc client-side từ một list
  nghĩa là bốn cột chung một cửa sổ — một chuỗi rejection đẩy offer ra khỏi response, và cột
  "Offers" trống vì `limit` trông y hệt cột "Offers" trống vì chưa ai mời.
- **Guard thì không được phân trang.** `queue.active()` dùng `limit=None`; trang Runs hỏi
  riêng một request để gate nút Crawl. Một guard nhìn nhầm cửa sổ sẽ báo "không có gì đang
  chạy" và cho chạy task thứ hai.
- **`/applications/{id}/events` cố ý KHÔNG phân trang** — lịch sử của *một* đơn, pager trên
  timeline 3 dòng là chrome thuần tuý. Một trong **hai** endpoint list còn trả mảng trần.
- **`GET /crawl/recent` (2026-10-04) là ngoại lệ thứ hai**: top-N cố định (`limit` ≤ 10, mặc định 3)
  các cấu hình crawl *khác nhau* gần nhất — không có trang 2 để đi tới, nên `total` không trả lời câu
  hỏi nào. Mỗi item đúng shape `POST /crawl` nhận, để "Crawl lại" gửi nguyên item về.
