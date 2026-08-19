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

### Sửa Master CV bằng câu lệnh — guardrail ở đây NGƯỢC với tailor

`POST /api/cv/master/edit` (chỉ master; scope tailored trả 400 và chỉ sang
`/jobs/{id}/edit`). Code: `tailor/edit.py` + `tailor/edit_guard.py`.

- **Tailor hỏi "cái này đã có trên CV chưa?"; edit hỏi "dữ kiện này có phải do USER nói
  không?"** Đảo ngược này là cả tính năng: dữ kiện mới **là mục đích** (project vừa làm xong
  chưa thể có trên CV), nhưng người được quyền đưa vào là **user**, không phải model. Đừng
  "sửa" bằng cách nới `vocabulary(master)` — nó cấp phép cho *từ*, không phải cho *lời khai*.
- **Instruction là GIẤY PHÉP, `source_quote` là TRÍCH DẪN.** Op thêm mới (`new_bullets`,
  `new_entries`) **bắt buộc** có quote và quote phải xuất hiện thật trong instruction
  (`textnorm.quote_appears_in`, dùng chung với inbox — **đừng viết bản thứ hai**). Đã thử cấp
  phép *chỉ* theo nội dung quote: **sai trong thực tế** — dữ kiện của một entry nằm rải khắp
  câu, nên quote vào mệnh đề "a crawler built with FastAPI" thì chính **tên project** bị chặn.
- **Chữ số được kiểm riêng.** `guard.unknown_terms` chỉ thấy token *trông như công nghệ*, mà
  `_TOKEN_RE` bắt buộc bắt đầu bằng chữ cái ⇒ "increased throughput by 40%" và "led a team of
  12 engineers" **không có gì để nó nhìn**. Chịu được ở tailor (schema không cho viết câu đó),
  **không chịu được ở đây**. Nên mọi cụm chữ số trong text mới phải có trong master hoặc trong
  instruction. Metric bịa là thứ đắt nhất có thể xuất hiện trên CV.
- **Rủi ro CÒN LẠI, nói thẳng:** guard là *lexical*. Nó chặn được tên công nghệ lạ và con số
  lạ, **không** chặn được câu văn xuôi bịa quanh những từ đã được cấp phép ("built a scalable
  crawler handling millions of listings" — không token nào lạ). Hai lớp đỡ còn lại là **diff
  bắt buộc xem trước khi chấp nhận** và `note`. Đừng quảng cáo guard này mạnh hơn thực tế.
- **Master CV là corpus mà mọi lần tailor sau đối chiếu.** Một câu bịa lọt vào đây sẽ được
  "rửa" thành *đã có trên CV* cho mọi job về sau. Đó là lý do đường này phải **chặt hơn**
  tailor, không phải lỏng hơn.
- **Không giới hạn số vòng** (`edit_max_rounds` là của *một job*, không phải của Master CV).
- **Test dùng task queue thì BẮT BUỘC fixture `worker_db`.** Task body mở session riêng bằng
  `session_scope()` ⇒ override `get_db` của FastAPI **không tới được nó**, và nó ghi thẳng vào
  `DATABASE_URL` thật. Đã xảy ra: một test ghi hẳn một version bịa vào Master CV thật, và task
  vẫn báo **done**. Hỏng *im lặng*, đúng loại tệ nhất.

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
