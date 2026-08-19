# `jobpilot/cv/` — CvDocument, template LaTeX, build PDF

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.
> Cover letter dùng chung `_preamble.tex.j2` của template — xem `jobpilot/apply/CLAUDE.md`.

### Thêm một template mới

**Template = một thư mục** `templates/<id>/` + `template.json`. Không sửa Python để thêm
template; `list_templates()` đọc theo thư mục, `describe_template()` đọc manifest.

Thư mục phải có đủ **7 file**: `_preamble.tex.j2`, `cv.tex.j2`, `cover_letter.tex.j2`, và 4
section (`paragraph`, `bullets`, `education`, `entries` — `experience` và `projects` dùng
chung `section_entries.tex.j2`). Thiếu file nào thì scope đó chết lúc render, không phải lúc
list. `template.json`:

```json
{ "name": "Plain", "description": "...", "assets": ["fonts"] }
```

- **`assets` là thứ được copy từ repo root vào build dir.** `awesome_cv` cần
  `awesome-cv.cls` + `fontawesome.sty` + `fonts`; `plain` dựng trên `article` nên chỉ cần
  `fonts`. Manifest thiếu `assets` → **fallback về bộ cũ (cả ba)**, để một thư mục thả vào
  không manifest vẫn chạy y như trước.
- **`description` hiện thẳng trong picker**, không giấu sau tooltip: "Awesome-CV" vs "Plain"
  không nói được *khi nào* chọn cái nào, "ATS parser đọc đúng thứ tự" mới nói được.

### Bẫy đã trả giá khi viết template thứ hai

- **`cv/latex.py` phát `\tech`, `\techfe`, `\hreficon` VÔ ĐIỀU KIỆN.** Template nào không
  định nghĩa đủ ba macro đó thì **mọi CV dùng nó** đều fail build. Không phải tuỳ chọn — có
  test ghim (`test_plain_defines_every_macro_the_inline_markup_emits`).
- **`\begin{itemize}\end{itemize}` là LỖI LaTeX cứng**, không phải block rỗng. `awesome-cv.cls`
  có `cvitems` dễ tính nên `awesome_cv` không lộ; `enumitem` của `plain` thì chết. Mà **DB mới
  seed CV RỖNG** (rule 3 ở CLAUDE.md gốc) ⇒ entry không bullet là thứ user mới gặp **đầu
  tiên**, không phải corner case. Mọi list phải guard `<% if e.items or e.role or ... %>`.
- **`trim_blocks` ăn newline sau mỗi `%>`** ⇒ dòng kết thúc bằng block tag sẽ **dính vào dòng
  sau**. Cho `\item` thì LaTeX vẫn nuốt (hợp lệ, chỉ xấu `.tex`); cho `\par` thì 2 đoạn thành
  1 dòng. Luật: **dòng `\item` phải kết thúc bằng một biến `<< … >>`, không phải `<% … %>`** —
  dồn phần điều kiện vào `<% set %>` phía trên.
- **Đừng viết file `.tex`/`.j2` bằng heredoc trong Bash.** Nó **ăn mất một backslash**:
  `\\[2pt]` tới LaTeX thành `\[2pt]` → "Bad math environment delimiter", và mình đi debug
  LaTeX trong khi LaTeX không sai. Dùng Write tool.
- **Số trang là một phần của thiết kế template.** Bản `plain` đầu tiên đẩy sample CV sang
  **2 trang** trong khi `awesome_cv` gói gọn 1 trang — "plain" mà tốn thêm một trang thì là
  CV tệ hơn, không phải CV mộc hơn. Sửa xong template phải **build lại và đọc số trang**.
- **`fontspec` + Roboto trong `fonts/`, không phải font mặc định của TeX.** Font mặc định
  không có glyph tiếng Việt và chỗ thiếu glyph là một **khoảng trắng im lặng** trong PDF, không
  phải lỗi build. Verify bằng cách đọc lại text layer (`pypdf`), đừng nhìn số trang rồi kết luận.

### `doc.template` là chuỗi tự do đi vào một đường dẫn

`template_dir()` check id theo **danh sách thật trên đĩa** rồi mới join path — cùng lý do
`compile.check_override()` tồn tại: text từ ô nhập biến thành path là dạng bug chỉ bị phát
hiện theo cách đắt tiền. Version cũ restore về có thể mang tên template build này không còn
ship; UI phải **nói ra** (`TemplatePicker` báo đỏ) thay vì hiện "không chọn gì".

### Template không dùng `theme.color` thì UI phải thừa nhận

`plain` render đơn sắc ⇒ picker màu không tới được PDF. `HeaderEditor` làm mờ + ghi "not used
by the plain template". Cùng một luật với `tex_override`: **im lặng bỏ qua thứ user gõ tệ hơn
là từ chối nhận nó**. Thêm template đơn sắc mới thì thêm id vào `MONOCHROME_TEMPLATES`
(`web/src/components/cv/HeaderEditor.tsx`).
