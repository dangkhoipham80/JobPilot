# `jobpilot/llm/` — model backend

> Nạp **on-demand** khi Claude đọc file trong thư mục này. Luật chung của repo ở `CLAUDE.md` gốc.

### Model backend (Phase 20 → 20b) — đọc trước khi đổi provider

- **Chọn theo từng việc, không phải một công tắc.** `llm.tailor` / `llm.letter` / `llm.classify`
  (rỗng = rơi về `llm.provider`, mặc định `claude`). Provider hợp lệ nằm ở
  `llm/registry.PROVIDERS` — thêm một backend = **một entry + một module client**, không sửa
  `Literal` ở bốn chỗ. Model chọn theo `llm.models[provider]`, ghi đè theo việc bằng
  `llm.task_models[task]`.
- **Một engine cho mỗi task, không phải một engine cho mỗi provider.** `ModelTailorEngine` /
  `ModelLetterEngine` / `ModelClassifier`, mỗi cái cầm một `StructuredClient`. Vòng retry là thứ
  chặn một plan sai lọt vào PDF, nên nó **không được** có bản sao theo backend — trước 20b thì
  `letter.py` đã có đúng hai bản gần giống nhau. Giờ bất biến đó do *không còn gì để fork* giữ,
  không phải do một test giữ.
- **Ba provider không nhận cùng một JSON Schema.** `llm/schema.py`: `flatten_schema` (Gemini —
  docs chỉ liệt kê subset, cảnh báo schema lồng sâu có thể bị từ chối), `strictify` (OpenAI
  strict — mọi object `additionalProperties:false`, **mọi** field trong `required`). Bẫy ở
  `strictify`: "mọi field required" **không** có nghĩa bỏ field optional — optional được nới
  thành nullable, nếu không model bị ép **bịa** ra `summary`.
- **Đo, đừng đoán.** Mọi lượt gọi ghi một row `llm_calls` (**kể cả lượt bị guard từ chối, kể cả
  lượt gọi hỏng**). Đọc bằng `GET /stats/llm` hoặc `jobpilot llm stats`. `jobpilot llm bench
  --task classify|tailor` chạy lại đúng phép đo của Phase 20 (5 email có đáp án / 4 job thật).
- **Mẫu nhỏ thì hiện `n=<count>`, không hiện %.** `llm/stats.MIN_SAMPLE`. 3 lượt 2 lỗi không
  phải "33%", nó là 3 lượt — và tỉ lệ thì mời người ta so sánh hai backend trên 3 lượt.
- **`cost_usd = NULL` khác `0.00`.** Model không có trong `llm/pricing.PRICES` thì không đoán
  giá; `unpriced_rounds` đi kèm mọi tổng, để một tổng dựng từ nửa số row không bị đọc như dựng
  từ tất cả. Bảng giá có `CHECKED_ON` — nó **sẽ** cũ đi.
- **Chỉ một ô cần cảnh báo: Gemini free tier.** Anthropic / OpenAI / Gemini **trả tiền** đều
  không train trên input API; Gemini **unpaid** thì có, và điều khoản ghi thẳng *"Do not submit
  sensitive, confidential, or personal information"* — trong khi `tailor`/`letter` gửi **cả
  Master CV**. Không đọc được tier từ API key nên có `llm.gemini_paid_tier`; `llm.warnings()`
  **cảnh báo, không chặn** — quyền là của user.
- **`llm.blocker(task)` kiểm tra key, không kiểm tra credit.** Key hỏng hay hết tiền chỉ biết
  bằng cách tiêu một request; giả vờ ngược lại chỉ là cách sai chậm hơn. Nó nằm trong
  `get_engine()` của route (không nằm trong route body) để test tự cấp engine không bị đòi key —
  đúng cái bẫy `test_missing_tokens_produce_a_readable_error` đã dính.
- **Telemetry không bao giờ được làm hỏng việc nó đo.** `usage.record` thử ghi có link
  job/application, vỡ thì ghi lại không link. Bản đầu nuốt lỗi im lặng và **mất sạch** row của
  `llm bench` vì FK.
- **Prompt phải nói ra thứ schema đã ngầm định** (`section_order` rỗng = giữ nguyên; kiểu nào
  dùng field nào). `retry_prompt` phải nhắc lại **đúng luật vừa vỡ** (`_REMEDIES`).
- **Ba luật chốt cho model backend (user đặt, không tự đổi):** (1) **không được leak API key** —
  đây là rủi ro, không phải chi tiết; (2) **model phải đổi được từ Web** (trang `/models`: chọn
  provider+model cho từng việc, dashboard giá/chất lượng/độ trễ, credit đã dùng/còn lại);
  (3) **mặc định dùng model rẻ nhất mà vẫn hiệu quả**, chứng minh bằng `llm bench` chứ không đoán.
- **Scrub key ở chỗ *tạo ra* lỗi, không phải ở từng nơi lỗi đi tới.** `llm/redact.py` gọi từ
  `LlmError.__init__` + `CallLog`: key sai thì provider **trích lại key** trong message
  (`Incorrect API key provided: sk-proj-…`) và chuỗi đó đi thẳng vào `llm_calls.error`, ra CLI,
  ra API. `log.warning` nào mang exception của SDK cũng phải `redact()`.
- **"Credit còn lại" KHÔNG lấy được từ provider.** Anthropic/OpenAI/Google đều đòi **Admin key**
  cho endpoint chi phí (đã thử, cả ba trả 401). Nên nó là `llm.budget_usd` (tự nhập) trừ đi phần
  **JobPilot tự đo** — là bộ đếm ngân sách, không phải số dư tài khoản, và UI phải nói đúng thế.
- **Mặc định hiện tại: `classify` = `openai/gpt-4o-mini`** (10 lượt, 100% đúng, rẻ nhất **và**
  nhanh nhất); `tailor`/`letter` giữ `claude-opus-4-8`. Mọi model đã thử đều 5/5 trên bộ classify
  ⇒ việc này phân biệt bằng **giá + độ trễ**, không phải độ chính xác.
- **Đừng chốt model khi cột tỉ lệ còn hiện `n=<count>`.** n=5 đã cho kết luận SAI một lần:
  `gemini-3.1-flash-lite` p50 705ms ở 5 lượt → **2732ms** ở 10 lượt, đảo ngược cả "rẻ nhất" lẫn
  "nhanh nhất". Đây là lý do `MIN_SAMPLE` tồn tại, và nó bắt được chính người viết ra nó.
- **`tailor` rẻ hơn không có nghĩa là đổi được.** `gpt-4.1` qua guardrail vòng đầu với ~$0.016/lượt
  so với ~$0.10 của `claude-opus-4-8`, nhưng guardrail chỉ bắt *bịa*, không bắt "đúng sự thật
  nhưng xếp hạng dở" — tailor phải chấm bằng mắt ở trang CV Review trước khi đổi.
- **`thinking` không bật cho mọi model được.** Haiku trả 400 *"adaptive thinking is not supported
  on this model"* ⇒ để nguyên là **chặn luôn cả tầng model rẻ**. Giờ registry tắt thinking cho
  `classify`, và client tự tắt + gọi lại một lần khi gặp đúng lỗi đó (không hardcode danh sách model).
- **Provider *liệt kê* model không có nghĩa là dùng được.** `gemini-2.5-flash` nằm trong
  `models.list()` nhưng `generateContent` trả **404 "no longer available to new users"**. Danh sách
  chỉ là *menu*, `llm bench` mới là bằng chứng. Và khi so id thì phải **so theo prefix**:
  Anthropic liệt kê `claude-haiku-4-5-20251001` còn alias mình gọi là `claude-haiku-4-5` — so khớp
  chính xác từng đánh dấu nhầm model đang chạy tốt là "không khả dụng".
- **Không chạy model local.** Mọi task LLM đi qua API của provider. Đánh đổi đã chấp nhận:
  thư nhà tuyển dụng **đã khớp đơn** thì rời khỏi máy. Cái *vẫn* đúng: thư không khớp đơn nào
  dừng lại trong máy (xem `jobpilot/apply/CLAUDE.md` § Inbox sync).
