# `jobpilot/api/` — REST + WebSocket

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Phần frontend của phân trang (`usePaging`, `useClampPage`) ở `web/src/CLAUDE.md`.

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
  timeline 3 dòng là chrome thuần tuý. Là endpoint list duy nhất còn trả mảng trần.
