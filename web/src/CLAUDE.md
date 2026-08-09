# `web/src/` — Web Dashboard (React + Vite + TS)

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Dữ liệu đằng sau các chart ở `jobpilot/analytics/CLAUDE.md`; hợp đồng phân trang của API ở
> `jobpilot/api/CLAUDE.md`.

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
