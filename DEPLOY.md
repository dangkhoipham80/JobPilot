# Deploy JobPilot — Oracle Cloud free tier + Tailscale (0đ/tháng)

> Đích: dashboard chạy 24/7, xem từ điện thoại mọi lúc, **không tốn tiền hàng
> tháng**, và **không phơi ra Internet**.

## 0. Mô hình bảo mật — đọc trước, đừng bỏ qua

**Tầng mạng là auth thật. Token API thì không.**

Dashboard là một bundle tĩnh. Bundle tĩnh phải tải được *trước khi* nó kịp hỏi
mật khẩu, mà token nó dùng để gọi API lại được Vite **nướng cứng vào bundle** lúc
build (`web/src/lib/api.ts`). Ai mở được trang thì `grep` một phát ra token.

⇒ Token chỉ chặn caller lạc cùng máy. Thứ thật sự chặn người ngoài là
**Tailscale**. Nếu có ngày bạn `tailscale funnel` hoặc mở port 8000 ra Internet
thì token đó bằng không, và người ta có: CV của bạn, Gmail app password, LLM key,
và một con bot gửi mail nhân danh bạn. **Đừng làm vậy.** Muốn public thì phải xây
login server-side thật trước — đó là một phase riêng.

Bốn lớp phòng thủ, theo thứ tự quan trọng:

1. **Tailscale** — không ở trong tailnet thì gói tin không tới được máy.
2. **uvicorn bind `127.0.0.1`** — kể cả tailnet bị lộ, chỉ `tailscale serve` vào được.
3. **Postgres chỉ nghe trên interface tailnet** (§5) — đây là lớp mới và là chỗ
   dễ hở nhất trong kiến trúc này, vì laptop cần nối vào DB từ xa.
4. **Token 32 byte + 3 gate email khoá khỏi HTTP.**

## 1. Kiến trúc: máy nào làm gì

Đây là điểm khác biệt lớn nhất so với "thuê VPS chạy tất cả", và là lý do nó **0đ**:

| | Server (Oracle, Singapore) | Laptop (nhà bạn) |
|---|---|---|
| Dashboard + API + WebSocket | ✅ 24/7 | — |
| Postgres (nguồn sự thật) | ✅ | — |
| Build PDF (xelatex) | ✅ | ✅ (Docker) |
| Tailor / apply / inbox sync | ✅ | — |
| **Crawl (Playwright)** | ❌ | ✅ |

**Crawl cố ý chạy ở laptop.** ITviec/TopCV/VietnamWorks đứng sau Cloudflare, mà
Cloudflare challenge IP datacenter nặng hơn IP dân dụng rất nhiều — còn máy free
lại nằm ở Singapore chứ không phải VN. Crawl từ laptop dùng **IP dân dụng Việt
Nam**, tức là địa chỉ tốt nhất hệ thống này có thể có cho việc đó.

Nó cũng giữ server nhẹ: không Chromium, không Playwright, không thư viện browser
— đó chính là thứ giúp mọi thứ lọt vào free tier.

Giá phải trả: laptop ngủ thì **lỡ một cửa sổ crawl**. Crawl là job nền 2 lần/ngày
và chạy bù ở lần sau; còn dashboard — thứ bạn thực sự muốn mở từ điện thoại — vẫn
chạy.

## 2. Tạo máy Oracle

Xem hướng dẫn từng bước đã gửi. Tóm tắt phần khoá cứng:

- **Home region = Singapore**, chọn xong **không đổi được vĩnh viễn**.
- Shape `VM.Standard.A1.Flex`, **2 OCPU / 12 GB** (Oracle cắt còn một nửa từ
  15/06/2026). Kẹt capacity thì lấy **1 OCPU / 6 GB** — vẫn thừa cho JobPilot.
- Image **Canonical Ubuntu 24.04** (tự ra bản `aarch64` khi shape là Ampere).
- Boot volume **50 GB**.
- Gặp *"Out of host capacity"* thì đổi Availability Domain trước, rồi thử giờ
  thấp điểm.

## 3. Cài trên server

```bash
sudo timedatectl set-timezone Asia/Ho_Chi_Minh   # timer dùng giờ local (§7)

sudo adduser --system --group --home /opt/jobpilot jobpilot
sudo apt update
sudo apt install -y git curl postgresql python3-venv

# LaTeX. KHÔNG cài Docker: ảnh csmith/awesome-cv-builder chỉ có amd64, máy này
# arm64. TeX Live thì có sẵn bản arm64 trong repo Ubuntu.
sudo apt install -y texlive-xetex texlive-latex-extra texlive-fonts-extra

# Node 20 để build dashboard ngay trên host
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

`texlive-fonts-extra` nặng (~1 GB) nhưng **bắt buộc**: `awesome-cv.cls` gọi
`\RequirePackage[default,opentype]{sourcesanspro}`. Đĩa không phải vấn đề ở đây —
free tier cho 200 GB. Kiểm nhanh cả ba thứ dễ thiếu nhất:

```bash
kpsewhich sourcesanspro.sty tcolorbox.sty unicode-math.sty
```

Thiếu dòng nào thì build CV sẽ chết với lỗi LaTeX khó đọc, không phải lỗi "thiếu gói".

Database:

```bash
sudo -u postgres psql -c "CREATE DATABASE jobpilot;"
sudo -u postgres psql -c "CREATE USER jobpilot WITH PASSWORD '<mật-khẩu-mạnh>';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE jobpilot TO jobpilot;"
```

Code + môi trường:

```bash
sudo -u jobpilot -H bash
cd /opt/jobpilot
git clone https://github.com/dangkhoipham80/JobPilot.git .
python3 -m venv .venv
# KHÔNG cài extra `crawler` — server không crawl, và bỏ nó là bỏ luôn Playwright.
.venv/bin/pip install -e '.[data,api,cv,tailor,openai,gemini,slack]'
```

`.env` (chmod 600, **không bao giờ commit**):

```bash
JOBPILOT_API_TOKEN=<sinh bằng lệnh bên dưới>
DATABASE_URL=postgresql+psycopg://jobpilot:<mật-khẩu>@127.0.0.1:5432/jobpilot
ANTHROPIC_API_KEY=...
```

```bash
.venv/bin/python -c "from jobpilot.api.security import generate_token; print(generate_token())"
```

> App **từ chối khởi động** nếu token là placeholder hoặc <20 ký tự. Cố ý: một
> server bật lên rồi từ chối mọi request trông như bug ở dashboard, còn một server
> không chịu bật thì nói thẳng lý do vào log.

Chọn backend build — máy này không có Docker nên `auto` sẽ tự chọn `local`, nhưng
ghi rõ ra thì không phải đoán:

```bash
mkdir -p jobpilot && printf 'cv:\n  build_backend: local\n' >> jobpilot/config.local.yaml
```

Rồi:

```bash
.venv/bin/alembic upgrade head
./deploy/update.sh          # build bundle với token thật rồi restart
exit
```

Service:

```bash
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobpilot-api jobpilot-backup.timer
```

`update.sh` cần `systemctl` và `journalctl`:

```bash
sudo tee /etc/sudoers.d/jobpilot <<'EOF'
jobpilot ALL=(root) NOPASSWD: /usr/bin/systemctl restart jobpilot-api
jobpilot ALL=(root) NOPASSWD: /usr/bin/journalctl -u jobpilot-api *
EOF
sudo visudo -c    # syntax sai là hỏng sudo cả máy — check trước
```

Thử ngay hai rule đó **lúc mọi thứ còn tốt**, vì chúng chỉ được dùng ở error path
— đúng lúc service không lên và bạn cần đọc log nhất:

```bash
sudo -u jobpilot sudo -ln /usr/bin/journalctl -u jobpilot-api -n 40 --no-pager
```

## 4. Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=jobpilot-vps
sudo tailscale serve --bg 8000     # TLS, proxy về 127.0.0.1:8000
```

Mở `https://jobpilot-vps.<tailnet>.ts.net` trên điện thoại đã cài Tailscale cùng
tài khoản. ⚠️ **Đừng dùng `tailscale funnel`** — xem §0.

Xong bước này thì **đóng port 22 public** trong Oracle Console (VCN → Security
Lists → xoá ingress `0.0.0.0/0:22`), nhưng chỉ sau khi đã ssh được qua tailnet.

## 5. Postgres qua tailnet — làm cẩn thận

Laptop cần ghi vào Postgres của server để crawl. Đây là chỗ dễ hở nhất, vì nó là
service duy nhất phải nghe ngoài loopback.

Lấy IP tailnet của server (`tailscale ip -4`, dạng `100.x.y.z`), rồi:

```bash
# /etc/postgresql/16/main/postgresql.conf
listen_addresses = 'localhost,100.x.y.z'
```

```bash
# /etc/postgresql/16/main/pg_hba.conf — thêm ĐÚNG một dòng, dùng IP /32 của laptop
host    jobpilot    jobpilot    100.a.b.c/32    scram-sha-256
```

```bash
sudo systemctl restart postgresql
```

**Dùng `/32` của đúng máy laptop, không dùng `100.64.0.0/10`.** Dải /10 là toàn
bộ không gian CGNAT của Tailscale — mở cả dải nghĩa là *mọi* thiết bị trong tailnet
(kể cả điện thoại, kể cả máy bạn thêm sau, kể cả máy bị mượn) đều nối thẳng được
vào DB. Tailnet là hàng rào, không phải lý do bỏ hàng rào thứ hai.

Kiểm rằng nó **không** nghe ra ngoài:

```bash
sudo ss -tlnp | grep 5432     # chỉ được thấy 127.0.0.1 và 100.x.y.z
```

## 6. Laptop: chạy crawl

Trong `.env` **của laptop**, trỏ `DATABASE_URL` sang server:

```bash
DATABASE_URL=postgresql+psycopg://jobpilot:<mật-khẩu>@jobpilot-vps:5432/jobpilot
JOBPILOT_API_TOKEN=<cùng token với server>
```

Không đổi dòng code nào — đây chỉ là một biến môi trường.

```bash
python -m jobpilot.cli crawl
```

Đặt lịch bằng Task Scheduler (Windows) 2 lần/ngày. Nếu laptop tắt lúc tới hạn thì
bật "Run task as soon as possible after a scheduled start is missed".

## 7. Verify — chạy thật, đừng dừng ở test xanh

- [ ] `curl -fsS http://127.0.0.1:8000/health` trên server → `{"status":"ok",...}`
- [ ] `systemctl list-timers jobpilot-*` → NEXT phải là **03:00 giờ VN**. Kiểm ở
      đây chứ không phải `systemd-analyze calendar`: đã có ca timer tính theo UTC
      trong khi `systemd-analyze` trả đúng giờ local.
- [ ] Mở URL `.ts.net` từ **điện thoại dùng 4G, tắt wifi** — wifi có thể đi đường
      LAN và không chứng minh được tailnet hoạt động.
- [ ] Dashboard load, chấm **LIVE** sáng (nó chỉ sáng khi WS nhận được `hello`,
      tức là đã auth xong, không phải khi socket vừa mở).
- [ ] **Build CV hai lần liên tiếp.** Lần hai mới lộ lỗi quyền file nếu có.
- [ ] **So PDF của server với PDF của laptop.** Đây là kiểm tra quan trọng nhất của
      phase này: hai backend khác nhau (xelatex native vs Docker) phải cho ra cùng
      một CV. Đã verify hai *cách gọi* cho ra text y hệt, nhưng **TeX Live arm64 của
      Ubuntu là bản khác với bản trong image** — chỉ máy thật mới trả lời được.
      Khác nhau nghĩa là CV bạn duyệt ở Studio không phải CV được gửi đi.

      ```bash
      .venv/bin/python -m jobpilot.cli cv build     # trên server
      # rồi so số trang + nội dung text với bản build ở laptop
      ```
- [ ] Tailor 1 job → kiểm LLM key.
- [ ] Apply 1 job ở `dry_run` → xác nhận **không có mail nào rời máy**.
- [ ] Trang Settings: 3 gate email hiện **khoá** ("host only"), không bấm được.
- [ ] Crawl từ **laptop** → job mới xuất hiện trên dashboard của server.
- [ ] **Tắt Tailscale trên điện thoại → URL phải KHÔNG vào được.** Vẫn vào được là
      đang lộ ra ngoài → dừng ngay.
- [ ] `curl` từ máy ngoài tailnet → phải **timeout**, không phải 401. 401 nghĩa là
      gói tin vẫn tới được máy bạn.

## 8. CI/CD

`.github/workflows/ci.yml`: **backend** (ruff + pytest), **frontend**
(`tsc --noEmit` rồi `vite build` — tách vì Vite transpile mà không type-check),
**deploy** (`needs: [backend, frontend]` nên không bao giờ deploy code đỏ).

Secrets cần đặt: `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` (OAuth client gắn tag
`tag:ci`), `DEPLOY_SSH_KEY`, `DEPLOY_HOST` (`jobpilot-vps`), `DEPLOY_USER`
(`jobpilot`). ACL tailnet phải cho `tag:ci` tới host qua port 22.

`update.sh` build lại bundle **trên host** vì token bị nướng vào bundle lúc build;
bundle build ở CI mang token placeholder của CI. Nó lấy `VITE_API_TOKEN` từ
`JOBPILOT_API_TOKEN` trong `.env` để chỉ có **một** chỗ ghi token.

## 9. Backup — không phải tuỳ chọn

Oracle **vừa cắt free tier một nửa không báo trước** (06/2026) và **có chính sách
thu hồi instance "idle"**. Máy này có thể biến mất mà không ai hỏi ý bạn.

`jobpilot-backup.timer` chạy `deploy/backup.sh` hằng đêm: `pg_dump -Fc` (khôi phục
được từng bảng bằng `pg_restore`) + `cv export` ra JSON (đọc được bằng mắt trên máy
bất kỳ; Master CV là thứ **không** tái tạo được bằng cách crawl lại). Script kiểm
file khác rỗng rồi mới báo thành công — một job backup báo xanh trong khi ghi file
0 byte còn tệ hơn không có backup, vì nó khiến bạn ngừng kiểm tra.

**Kéo bản backup về laptop định kỳ.** Backup nằm cùng máy với thứ nó backup thì
không cứu được trường hợp mất máy — mà đó chính là trường hợp dễ xảy ra nhất ở đây.

## 10. Nếu crawl ở laptop cũng bị chặn

Nguồn feed (WeWorkRemotely, Arbeitnow) và ATS (Greenhouse, Lever) **không** sau
Cloudflare nên không ảnh hưởng. Với 3 site VN: hạ `crawl.jobs_per_site`, tăng
`crawl.rate_limit_seconds`, và crawl thưa hơn. Không có cách nào "vượt" hợp lệ —
`CLAUDE.md` nguyên tắc 5: tôn trọng ToS/robots/rate-limit, site nào fail thì log
và chạy tiếp.
