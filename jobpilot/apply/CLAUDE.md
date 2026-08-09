# `jobpilot/apply/` — nộp đơn, outcome, inbox

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.

### Outcome tracking (Phase 18) — đọc trước khi đụng vào số liệu

- **`/stats` trả hai bộ đếm và chúng KHÔNG thay thế nhau được**: `current` đếm theo
  `Application.outcome_stage` (board đang hiện gì), `reached` đếm `COUNT(DISTINCT application_id)` trên
  `application_events` chưa retract (đã từng tới chặng nào). **Mọi tỉ lệ phải dùng
  `reached`** — một đơn phỏng vấn 2 vòng rồi bị từ chối chỉ nằm ở `current["rejected"]`, nên
  tính interview rate theo `current` sẽ báo số đơn đang *kẹt* ở vòng phỏng vấn, một con số
  tụt xuống khi mọi việc đang tốt lên. Có test ghim ở cả `test_outcome.py` lẫn
  `test_outcome_api.py`; đừng "đơn giản hoá" về một bộ.
- **Outcome sống ở tầng `Application`, không đụng `JobStatus`.** Thêm value vào Postgres
  enum cần `ALTER TYPE … ADD VALUE` (không chạy trong transaction block) và kéo theo
  `web/src/lib/statuses.ts` + funnel + `slack/events.py`. Job `SUBMITTED` vẫn `SUBMITTED` dù
  sau đó offer hay bị từ chối. Muốn thêm loại outcome mới thì thêm một chuỗi vào
  `apply/outcome.ALL_OUTCOMES` + `OutcomeType` bên Pydantic/TS — **không** cần migration.
- **`ghosted` không tự suy ra theo bộ đếm ngày**, và outcome không bao giờ tự ghi — inbox sync
  cũng chỉ *đề xuất*: mail vào → gợi ý → user bấm xác nhận mới ghi.

### Inbox sync (Phase 19) — đọc trước khi đụng vào `apply/inbox.py`

- **Thứ tự fetch → ghép cục bộ → LLM là thiết kế riêng tư, không phải tối ưu.** Thư không
  thuộc đơn nào **dừng lại ngay trong máy**; chỉ thư đã khớp mới tới model. Đừng đảo thứ tự,
  đừng "gửi hết cho model cho gọn" — có test ghim
  (`test_unmatched_mail_is_never_handed_to_the_classifier`). Vì mọi task LLM đều đi qua API
  provider, bước ghép cục bộ **là** phần bảo vệ và nó phải đứng trước.
- **`quote` phải xuất hiện thật trong thư**, nếu không verdict bị loại và lưu status
  `unusable`. **Vẫn phải lưu** dù bị loại: không lưu thì lần sync sau thư đó lại "mới" và
  lại gọi Claude — trả tiền vô hạn cho một câu trả lời không bao giờ hiển thị.
- **Bật cần `apply.inbox.enabled`** + `IMAP_USER`/`IMAP_PASSWORD` (Gmail phải là App
  Password). Mặc định **tắt** — đọc hộp thư của người khác không phải thứ tự ý bật hộ.
  `apply.inbox.folder` cho ai muốn siết vào một label riêng.
- **Chỉ đề xuất `replied`/`interview`/`offer`/`rejected`.** `withdrawn`/`ghosted` là quyền
  tự khai của user. "Đã nhận hồ sơ" là `auto_ack`, không phải `replied`.
- **Tên công ty phải fold về ASCII trước khi so với domain** (`inbox.fold`) — domain không
  bao giờ có dấu, nên "Công ty TNHH X" mà không fold sẽ giữ `công` như phần đặc trưng.
- **`meta` là JSONB do bất kỳ phiên bản dispatcher nào ghi** — đọc field trong đó ở React
  phải optional-chain. Một row thiếu key từng làm trắng cả trang Applications.

### Cover letter + email

- **Cover letter đã ra PDF** (Phase 17): `cv/templates/awesome_cv/cover_letter.tex.j2` dùng chung `_preamble.tex.j2` với CV. **`awesome-cv.cls` bản trim trong repo KHÔNG có macro letter nào** (`\cvletter`, `\recipient`… — grep class file trước khi tin spec). Text vẫn là bản chính (email mang text ở body, PDF là đính kèm); build hỏng thì **đơn vẫn gửi**, lý do vào `meta.letter.pdf_error`. Ngắt đoạn phải viết `\par` tường minh — Jinja `trim_blocks` ăn dòng trống, biến 2 đoạn thành 1 dòng dính liền mà compile vẫn sạch.
- **Gmail OAuth** chưa làm — dùng `method: smtp` (Gmail app password chạy được).
