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
- **`400 Schema is too complex` là do FIELD OPTIONAL, không phải do schema to.** Đo thật
  (2026-08-19, khi thêm `MasterEditPlan`): `TailorPlan` **4682 byte → PASS**; schema mới
  **3153 byte → FAIL**; tách nhỏ còn **3291 byte → vẫn FAIL**; **cùng cấu trúc đó bỏ hết
  default cho mọi field → 3260 byte → PASS**. Field có default ⇒ optional ⇒ nở thành nhánh
  `anyOf`/nullable, và đủ nhiều nhánh thì vỡ ngân sách *dù schema đọc rất nhỏ*. Luật rút ra:
  schema gửi cho provider thì **mọi field required**, "không áp dụng" biểu diễn bằng `""`/`-1`
  chứ không bằng optional — và prompt phải nói rõ điều đó. Hệ quả thứ hai: **đừng gộp một
  model "phẳng" nhiều field cho mọi trường hợp**; một object lồng nhiều field + nhiều array là
  đúng hình dạng bị từ chối. Tách thành nhiều list nhỏ (mỗi loại op một list) vừa nhẹ schema
  vừa khiến tổ hợp vô nghĩa **không biểu diễn được**.
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
- **Không chạy model local.** Mọi task LLM đi qua một provider Claude/OpenAI/Gemini — qua API,
  hoặc qua gói Claude của user (`claude_cli`, bên dưới). Đánh đổi đã chấp nhận:
  thư nhà tuyển dụng **đã khớp đơn** thì rời khỏi máy. Cái *vẫn* đúng: thư không khớp đơn nào
  dừng lại trong máy (xem `jobpilot/apply/CLAUDE.md` § Inbox sync).

### Provider `claude_cli` — chạy trên gói Claude của user (2026-10-04)

User chốt: JobPilot host trên máy của chính họ, gói Pro/Max dùng không hết ⇒ dùng nó thay vì
trả tiền API. `llm/claude_cli.py` gọi `claude -p` (print mode), cùng model với `claude` nhưng
**trừ vào hạn mức gói**, không tính tiền theo token.

- **Chỉ cho dùng cá nhân.** Anthropic cấm *sản phẩm* cho người dùng của họ login bằng claude.ai;
  một người tự động hoá gói của chính mình trên máy mình là chuyện khác, nhưng **không phải đường
  docs khuyên** cho script (đó là bare mode = API key). Nó gãy ngày nào thì đổi về `claude` trên
  `/models`, không code nào phía trên phải đổi.
- **Auth = phiên login `claude` sẵn có trên máy; token là tuỳ chọn** (`Provider.key_optional`).
  Đã thử thật từ một LaunchAgent (PATH `/usr/bin:/bin:…`, đúng môi trường của API): `claude auth
  status` → `loggedIn: true`, gọi `-p` thành công — LaunchAgent trong phiên GUI đọc được keychain.
  `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`) chỉ cần ở nơi không có phiên login (ssh, máy
  không ai đăng nhập). Blocker chỉ đòi **binary** (`Provider.preflight`); binary tìm cả ở
  `~/.local/bin` vì PATH của launchd không có nó. `registry.ready()` — không phải `api_key()` — là
  thứ `/stats/llm` trả về cho `has_key`/`providers`, nếu không UI làm xám đúng backend đang chạy được.
- **$0 chỉ đúng khi login là gói.** `subscription_problem()` đọc `claude auth status --json`
  (cache 5 phút) và **chặn** nếu chưa login, `apiProvider != firstParty` (Bedrock/Vertex), hoặc
  login Console (tính tiền theo token) — fail-closed khi không đọc được. Chạy ở blocker **và** đầu
  `structured()` (vì `cli tailor`/`llm bench` không đi qua route). Env con xoá
  `ANTHROPIC_API_KEY`/`AUTH_TOKEN`/`BASE_URL` + `CLAUDE_CODE_USE_BEDROCK|VERTEX|FOUNDRY`: CLI ưu
  tiên chúng hơn gói ⇒ để lọt là bị tính tiền trong khi `llm_calls` ghi $0.
- **Test không bao giờ gọi `claude` thật**: `conftest._no_real_claude_cli` ghim `find_claude → None`
  (máy dev chạy như CI). `/stats/llm` hỏi `ready()` của mọi provider ⇒ thiếu chốt này thì suite
  shell ra `claude auth status` và pass/fail theo cách máy đó đang login.
- **System prompt đi bằng `--system-prompt-file`, không bao giờ argv.** Với tailor nó là cả Master
  CV, và argv thì mọi process trên máy đọc được (`ps`) suốt ~1 phút. Trên Windows `claude.cmd`
  (npm) chạy qua cmd.exe, cắt argument nhiều dòng ở newline đầu ⇒ model nhận CV cụt mà vẫn trả lời.
  File nằm trong temp dir 0700, xoá khi xong. `encoding="utf-8"` tường minh (Windows mặc định cp1252
  ⇒ JD tiếng Việt nổ `UnicodeEncodeError`).
- **System prompt riêng thay prompt ~32k token của Claude Code** — đo thật: 32.198 → ~1.200 token
  input/lượt. Trên gói, token là tiền tệ; thiếu flag này hạn mức cạn nhanh gấp ~27 lần. Cộng
  `--tools ""`, `--strict-mcp-config`, `--setting-sources ""`, `--no-session-persistence` (không
  để lại session chứa cả Master CV dưới `~/.claude`) và **cwd là thư mục tạm rỗng** (không nạp
  `CLAUDE.md` của repo vào prompt CV).
- **Retry = transcript trong một prompt** (print mode chỉ nhận một lượt user). Đã chạy thật:
  tailor Opus bịa "SQL, NoSQL" → guardrail chặn → lượt 2 qua transcript sửa đúng.
- **`cost_usd = 0.0`, không phải `None`.** Giá *biết* là 0 (gói đã trả); `None` nghĩa là "không
  biết giá". `total_cost_usd` của CLI là giá *nếu đi API*, không phải thứ ai đã trả — đừng ghi nó.
- **Data policy khác `claude`.** Gói nằm dưới **consumer terms**: train hay không theo setting
  "Help improve Claude" của tài khoản ⇒ `PolicyNote.depends_on_account`, cảnh báo nhưng không in
  như chắc chắn.
- **Đo 2026-10-04** (haiku-4-5): classify **5/5**, intake **11/11** — ngang provider API, nhưng
  **p50 6–8 s** (API ~1,3 s) vì khởi động CLI. Tailor Opus 2 lượt: 71 s. Chậm, không sai.
- **Hết hạn mức ở `-p` mode docs không mô tả.** Client chuyển nguyên văn `result` của CLI vào
  `LlmError` thay vì đoán câu chữ.
