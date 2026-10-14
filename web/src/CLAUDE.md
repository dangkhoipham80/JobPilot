# `web/src/` — Web Dashboard (React + Vite + TS)

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Dữ liệu đằng sau các chart ở `jobpilot/analytics/CLAUDE.md`; hợp đồng phân trang của API ở
> `jobpilot/api/CLAUDE.md`.

⚠️ **UI là song ngữ Việt/Anh, mặc định Tiếng Việt.** Thêm bất kỳ chuỗi nào hiện ra màn hình thì
đọc `web/src/i18n/CLAUDE.md` trước: chuỗi cứng trong JSX là bug, không phải style nit. Ngày giờ /
nhãn quality / trạng thái job phải đi qua `useFormat()` / `useLabels()` / `useStatuses()` —
bản không-tham-số-ngôn-ngữ của chúng đã bị xoá nên call-site cũ sẽ **fail biên dịch**, đó là cố ý.

### Chart + màu — đọc trước khi thêm biểu đồ

- **Màu theo *việc* nó làm** (skill `dataviz`, đọc trước khi thêm chart). Mọi chart đếm job dùng
  chung hằng `MEASURE` trong `Market.tsx` — một measure một màu; tô 8 hue xuống 15 dòng là tô
  theo *thứ hạng*. Nominal (skill, city) một hue; ordinal (seniority) `ordinalRamp(n)` — ramp
  **đổi bước theo n**; histogram **không** ramp (trục x đã mang thứ tự); quality dùng `STATUS` +
  icon + chữ, `undated` để **xám** vì không biết ≠ hỏng. Palette mới thì **chạy
  `validate_palette.js`** với surface thật của app, đừng ước lượng bằng mắt.
- **Donut nguồn xếp lát theo slot palette, không theo số lượng.** Bộ 8 hue chỉ validate cho cặp
  **kề nhau trong thứ tự slot**: xếp theo count cho ra xám cạnh magenta **ΔE 2.1 (deutan)** ở dark,
  xếp theo slot thì cặp tệ nhất **ΔE 41**. Xếp hạng nằm ở legend, đọc bằng số. `SOURCE_ORDER`
  phải **đúng bằng số hue**.
- **Token màu đưa vào SVG phải là màu.** `--ink-muted` lưu RGB channels cho Tailwind; nhét thẳng
  vào `fill` là thuộc tính không hợp lệ, **bị bỏ qua im lặng** → nhãn trục về gần đen: light mode
  vẫn đọc được nên không ai thấy, dark mode mất sạch. Dùng `axisColor()` / `gridColor()` /
  `surfaceColor()` ở `ChartFrame.tsx`, đừng đọc CSS var trực tiếp.
- **Chart đọc `isDark()` lúc render.** Chụp dark mode phải set `localStorage` **trước khi app
  boot** (`add_init_script`); bật class `.dark` sau khi mount chỉ repaint CSS — chart giữ palette
  light, ảnh *trông* tối mà verify sai.

### Bảng Jobs + nhãn trạng thái

- **Kiểm `StatusPill` bằng dữ liệu thật, không bằng bảng 9 màu.** Danh sách thật gần như chỉ có
  `DISCOVERED` và `SKIPPED`; hai kiểu đó từng là hai viền xám gần giống hệt trong khi bảy màu kia
  không bao giờ lên màn hình. Thêm/đổi màu trạng thái thì đo tương phản trên `--surface` **và**
  `--surface-2` (hover của dòng) ở cả hai theme — hex literal cần biến thể `dark:` riêng.
- **Cột Vị trí là một phần của bảng (`w-[38%]`), không phải "phần còn lại"**, và chữ **xuống dòng**,
  không `truncate`. Đổi sàn `min-w` thì chụp lại ở ~1180px: sàn quá cao làm cột Thao tác tràn ra
  ngoài card (bảng đã bọc `overflow-x-auto` để tràn thì cuộn chứ không bị cắt).
- **Thứ tự là của API** (`jobpilot/api/CLAUDE.md`): "đã bỏ qua xuống cuối", ba `order`, khoảng độ
  khớp. Đừng sắp hay lọc lại `items` ở frontend — làm trong một trang không phải là làm trên cả
  danh sách. Bundle và backend phải lên **cùng nhau**: với API bản cũ, `order=match` bị **422**
  nhưng `match_min`/`match_below` thì bị **bỏ qua im lặng** — 200 kèm danh sách *không lọc* dưới
  một nhãn đang nói là đã lọc, đúng loại lỗi trông-như-đúng. Nên hai thứ lên cùng nhau (`deploy/macos/update.sh` làm đúng vậy); verify thì dựng backend
  của worktree ở cổng khác chứ đừng trỏ Vite vào service đang chạy.

### "Tailor theo một JD" trong CV Studio — task khởi động ở cú click, không ở lúc trang tải

Thẻ này là `AddJobForm` ở `mode="tailor"` (cùng form với `/jobs`, không fork): lưu job → shortlist →
`api.tailor()` → sang `/jobs/:id/review` kèm `state: { tailorTask }`.

- **Task được tạo ở CV Studio, lúc bấm nút**, rồi *trao* id cho trang review theo dõi. Đừng đổi
  thành "trang review tự tailor khi mở kèm cờ": một lượt gọi model sẽ thành tác dụng phụ của điều
  hướng — và của nút Back, của StrictMode chạy effect hai lần.
- **`CvReview` đọc `location.state.tailorTask` đúng một lần rồi xoá nó khỏi history entry**
  (`navigate(pathname, { replace: true, state: null })`). State của router sống qua reload; không
  xoá thì F5 sau khi server restart sẽ chờ mãi một task mà queue đã quên — `useTask` không phân
  biệt được 404 ở lần fetch đầu với "chưa có".
- **Job đã có bản CV tailor thì chỉ mở trang review, không chạy vòng mới — và trang review NÓI ra
  điều đó** (`state: { tailorSkipped }`). Hỏi **CV** (`api.review(id).version > 0`), đừng hỏi
  status: `FAILED` vừa là "tailor hỏng" vừa là "apply hỏng sau khi CV đã được duyệt", và bản đầu
  xét theo status đã tailor đè lên một CV đã duyệt (review gate đo được: v2 → v3, mất trạng thái
  duyệt). `POST /jobs` là upsert: dán lại một tin rơi vào row cũ, ở bất kỳ đâu trong funnel — không
  có dòng báo thì user bấm "Lưu & tailor" và nhận về một CV cũ tailor theo JD khác, không lời nào.
- **Thẻ nằm NGOÀI nhánh đổi tab và bị ẩn bằng CSS ở tab LaTeX, không unmount.** Form đang giữ một
  tin đã dán — có khi là bản chép từ ảnh đã tốn một lượt model.
- **`useTask` trả một task `Evicted` cả khi nó chưa từng thấy task đó** (404 ngay lần fetch đầu).
  Trước đó nó chỉ làm vậy khi đã có `prev`, nên một id được trao sang mà queue đã quên để lại
  `busy="tailor"` mãi mãi: mọi nút khoá, không dòng nào giải thích.
- **Editor đang có chỉnh sửa chưa lưu thì nút bị khoá và nói lý do** (`blocked`): tailor đọc Master
  CV **đã lưu**, và rời trang là mất phần chưa lưu.
- **Bước sau khi lưu mà hỏng thì form nói "job đã được lưu"** (`savedAnyway`) — chỉ báo "lỗi" là
  mời user thêm job lần hai. Ở `mode="tailor"` thì mô tả là bắt buộc: tailor không JD là tailor
  theo không gì cả.
- Shortlist tự động ở đây **là** quyết định của user (họ dán tin và bấm "tailor"), và tailor không
  gửi gì ra ngoài: nó dừng ở trang review, trước đúng cổng Duyệt của mọi job khác.

### Bẫy React đã trả giá

- **Guard double-click phải là `useRef`, không phải state.** Hai click cùng một tick đều đọc
  `busy === false` (chưa re-render giữa hai lần) nên state check để lọt click thứ hai và ghi
  event trùng. Xem `web/src/components/OutcomeTracker.tsx`.
- **`meta` là JSONB do bất kỳ phiên bản dispatcher nào ghi** — đọc field trong đó phải
  optional-chain. Một row thiếu key từng làm trắng cả trang Applications.
- **Phân trang**: `usePaging(name)` nhớ **size** trong localStorage theo từng list (không nhớ page —
  vị trí là chuyện một lần xem, size là preference), `useClampPage` kéo về trang cuối hợp lệ khi
  list co lại, và **`reset()` khi filter đổi** (đứng ở trang 7 của tìm kiếm giờ còn 4 kết quả =
  bảng trống không manh mối). Dropdown compare version trong CV Studio dựng option từ **dải
  1..total**, không từ trang đã tải, nếu không thì hết diff được v1 với v40.
- **Lưu ý khi chụp/screenshot UI**: headless Chrome **không có PDF viewer**, nên khung preview PDF
  sẽ trống (`net::ERR_ABORTED` trên blob URL). Đó là giới hạn của headless chứ không phải bug —
  chạy `headless=False` để kiểm tra thật.
