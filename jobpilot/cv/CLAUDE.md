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

### Hai engine build PDF: tectonic (mặc định) và docker (đường lui)

`cv.engine` = `auto` | `tectonic` | `docker`; `auto` ưu tiên tectonic, không có thì rơi về
docker, không có cả hai thì `BuildError` chỉ cách cài **cả hai**. Code: `tailor/build.py`.

- **Chọn tectonic chỉ vì chi phí cài, không phải vì output.** Đã đo trên **Master CV thật** +
  sample có tiếng Việt, cả hai template: **cùng số trang, cùng tập từ trong text layer, cùng
  verdict của `ats.py`** (trừ đúng một khác biệt, xem dưới). Tectonic ~10 MB binary tĩnh +
  ~50 MB cache, không daemon; ảnh docker 3.18 GB + phải nhớ bật Docker Desktop.
- **Khác biệt thật DUY NHẤT: template `plain` build bằng docker nhả ra 2 ligature `ﬁ`, tectonic
  thì không** ⇒ finding `ligatures` của `ats.py` **biến mất** khi đổi engine. Đây là *tốt hơn*
  (recruiter search "office" không khớp "oﬃce"), nhưng nó có nghĩa: **báo cáo ATS của cùng một
  CV phụ thuộc engine đã build nó**. Thấy finding đổi mà JSON không đổi thì nghi engine trước,
  đừng đi sửa template.
- **`fontawesome.sty` + `awesome-cv.cls` đã phải sửa để chạy được tectonic** — cả hai là file
  vendor, sửa tối thiểu, có comment tại chỗ:
  - `.sty` nạp FontAwesome **theo tên**, chỉ tìm thấy khi font được cài ở mức hệ thống. Ảnh
    docker có sẵn nên đường này chạy suốt và `fonts/FontAwesome.ttf` trong repo **chưa bao giờ
    được dùng**. Engine trần thì chết ngay. Nay ưu tiên `Path=fonts/`.
  - Sửa xong thì lộ lỗi thứ hai: `.cls:159` định nghĩa **lại** `\FA`. fontspec của TeX Live cũ
    (docker) cho ghi đè im lặng, fontspec mới (tectonic) báo `Command '\FA' already defined`.
    `\renewfontfamily` là cái bẫy — TeX Live trong ảnh docker **không có** lệnh đó, dùng nó là
    đổi lỗi tectonic lấy lỗi docker. Đang dùng `\let\FA\relax` trước `\newfontfamily`: cả hai
    đều đọc là "chưa định nghĩa". **Đổi bất cứ dòng nào trong hai file này thì phải build lại
    bằng CẢ HAI engine**, vì mỗi engine chỉ bắt được một nửa số lỗi.
- **Tectonic để lại `.log`, docker thì không** — nên `build_cv()` xoá `.log` cùng lúc với
  `.pdf`. Không xoá thì: build bằng tectonic (có log) → đổi sang docker → thiếu pypdf →
  `_pages_from_log` đọc log cũ và báo số trang của **một PDF đã không còn tồn tại**.
- **Log của tectonic ghi `Output written on cv.xdv`, không phải `cv.pdf`.** Regex hiện khớp
  được chỉ vì phần tên file là wildcard — có test ghim, đừng "dọn" nó chặt lại.
- Build **lần đầu** cần mạng (tectonic tải gói TeX về cache) và chậm; lần sau offline, ~1–2s.
  Cache theo **user**, nên warm bằng root rồi tưởng service chạy được là một cái bẫy deploy.

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
- **Dán nguyên một JD vào ô instruction = cấp phép trọn gói mọi tên công nghệ trong đó.**
  Giấy phép là *cả instruction*, không phải riêng câu trích — nên một instruction dài dạng
  "update my CV for this job: Requirements: Kafka, Kubernetes, Terraform, ..." cấp phép cho
  agent viết bullet gộp cả 5 công nghệ đó vào Master CV dù user chưa từng nói mình có kinh
  nghiệm với chúng, miễn có 1 quote hợp lệ đâu đó. Đây không phải lỗi thực thi, mà là hệ quả
  trực tiếp của quyết định "giấy phép theo cả câu, không theo riêng quote" (chọn có chủ đích vì
  quote-only làm chính tên project bị chặn — xem bullet phía trên). Vẫn còn lớp diff + user
  duyệt để bắt lại — nhưng nếu tính năng "Ask for a change" từng được PR/demo nói là chặn được
  tên công nghệ lạ, câu đó cần sửa lại: nó chặn được model **tự bịa ra** một tên công nghệ, không
  chặn được model **sao chép** tên công nghệ từ một JD user dán vào.
- **Master CV là corpus mà mọi lần tailor sau đối chiếu.** Một câu bịa lọt vào đây sẽ được
  "rửa" thành *đã có trên CV* cho mọi job về sau. Đó là lý do đường này phải **chặt hơn**
  tailor, không phải lỏng hơn.
- **Không giới hạn số vòng** (`edit_max_rounds` là của *một job*, không phải của Master CV).
- **Vòng không đổi gì thì KHÔNG ghi version.** Model từ chối làm (instruction quá mơ hồ) là một
  vòng **thành công** — câu trả lời đúng là từ chối. Ghi thêm một version giống hệt bản trước là
  xếp câu trả lời đó vào loại "đã sửa CV", làm lịch sử đầy row có diff rỗng và chôn mất row có
  ý nghĩa. Quyết định bằng `documents_differ(master, edited)` — **so tài liệu, không hỏi diff**:
  diff là bản *tóm tắt cho người đọc*, mà tóm tắt thì được phép bỏ sót, nên dựa vào nó để quyết
  định có ghi hay không là biến mọi điểm mù của nó thành **mất trắng một lần sửa**.
- **`tailor/diff.py` từng MÙ với nội dung THÊM VÀO.** `_order_note` báo `dropped` + `reordered`
  mà **không** báo `added`, vì caller duy nhất của nó (tailor) không bao giờ thêm được gì. Thêm
  1 entry vào projects (3→4) mà diff trả `changed=False`. Nguy hiểm vì **diff chính là thứ user
  duyệt** trước khi chấp nhận — cả tính năng sửa Master CV dựa vào đó. Đã sửa + thêm status
  `expanded` (nhãn "Added", màu accent để không lướt qua được). Bài học: một hàm dùng chung
  **an toàn vì caller cũ không làm được điều đó** sẽ thành lỗ hổng ngay khi có caller mới.
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
