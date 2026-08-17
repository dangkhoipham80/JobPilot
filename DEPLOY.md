# Deploy JobPilot lên VPS (Tailscale-only)

> Đích: JobPilot chạy 24/7 trên một VPS Linux, truy cập từ điện thoại/laptop
> **chỉ qua Tailscale**. Không mở port công khai, không domain, không Cloudflare.
> Ngân sách ~100k VNĐ/tháng.

## 0. Mô hình bảo mật — đọc trước, đừng bỏ qua

**Tầng mạng là auth thật. Token API thì không.**

Dashboard là một bundle tĩnh. Bundle tĩnh phải tải được *trước khi* nó kịp hỏi
mật khẩu, mà token nó dùng để gọi API lại được Vite **nướng cứng vào bundle** lúc
build (`web/src/lib/api.ts`). Ai mở được trang thì đọc được token trong JS —
`grep` một phát là ra.

⇒ Token chỉ chặn caller lạc cùng máy. Thứ thật sự chặn người ngoài là
**Tailscale**. Nếu có ngày bạn `tailscale funnel` hoặc mở port 8000 ra Internet
thì token đó bằng không, và người ta có: CV của bạn, Gmail app password, LLM key,
và một con bot gửi mail nhân danh bạn. **Đừng làm vậy.** Muốn public thì phải xây
login server-side thật trước (session cookie + hash mật khẩu + rate-limit), đó là
một phase riêng.

Ba lớp phòng thủ hiện có, theo thứ tự quan trọng:

1. **Tailscale** — không ở trong tailnet thì gói tin không tới được máy.
2. **uvicorn bind `127.0.0.1`** — kể cả tailnet bị lộ, chỉ `tailscale serve` proxy vào được.
3. **Token 32 byte + 3 gate email khoá khỏi HTTP** — chống caller lạc và chống
   "token rò → server tự gửi mail".

## 1. Chọn máy

| Yêu cầu | Số tối thiểu | Vì sao |
|---|---|---|
| RAM | 2 GB (+2 GB swap) | Chromium (~0.5–1 GB lúc crawl) + Postgres + xelatex |
| Đĩa | **25 GB** | ảnh Docker LaTeX ~3.5 GB, Chromium ~0.5 GB, OS ~5 GB, còn lại cho DB |
| CPU | 2 vCPU | build PDF là CPU-bound, nhưng chỉ chạy từng lúc |
| Kiến trúc | **x86-64** | `csmith/awesome-cv-builder` **chỉ có amd64** — ARM phải tự build image TeXLive |
| Vị trí | **Việt Nam** | ITviec/TopCV/VietnamWorks sau Cloudflare; IP datacenter nước ngoài bị challenge nhiều hơn |

⚠️ Nhiều gói 50–66k/tháng chỉ có 20 GB đĩa — **chật**, LaTeX image ăn hết một phần
lớn. Nhắm gói ~100–120k có ≥25 GB NVMe.

## 2. Cài trên VPS

```bash
sudo adduser --system --group --home /opt/jobpilot jobpilot
sudo apt update && sudo apt install -y git curl postgresql docker.io python3.11-venv

# Node 20 cho việc build dashboard trên chính host
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs

# jobpilot phải gọi được docker (build PDF) — không có nhóm này thì
# tailor/build.py raise BuildError và KHÔNG có fallback nào cả.
sudo usermod -aG docker jobpilot

sudo -u postgres psql -c "CREATE DATABASE jobpilot;"
sudo -u postgres psql -c "CREATE USER jobpilot WITH PASSWORD '<đặt-mật-khẩu>';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE jobpilot TO jobpilot;"
```

Lấy code + môi trường:

```bash
sudo -u jobpilot -H bash
cd /opt/jobpilot
git clone <repo> .
python3.11 -m venv .venv
.venv/bin/pip install -e '.[all]'
.venv/bin/playwright install --with-deps chromium   # cần cho ITviec/TopCV/VietnamWorks
docker pull csmith/awesome-cv-builder                # ~3.5 GB, kéo trước cho đỡ timeout lần đầu
```

`.env` (chmod 600, **không bao giờ commit**):

```bash
JOBPILOT_API_TOKEN=$(python -c "from jobpilot.api.security import generate_token; print(generate_token())")
DATABASE_URL=postgresql+psycopg://jobpilot:<mật-khẩu>@127.0.0.1:5432/jobpilot
ANTHROPIC_API_KEY=...
```

> App **từ chối khởi động** nếu token là placeholder hoặc <20 ký tự. Đó là cố ý:
> một server bật lên rồi từ chối mọi request trông như bug ở dashboard, còn một
> server không chịu bật thì nói thẳng lý do vào log.

Migrate + build dashboard + bật service:

```bash
.venv/bin/alembic upgrade head
./deploy/update.sh          # build bundle với token thật rồi restart

exit   # về lại user thường
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobpilot-api jobpilot-crawl.timer jobpilot-backup.timer
```

`update.sh` cần `systemctl restart` và `journalctl` — cấp đúng hai lệnh đó, không cấp sudo trống:

```bash
sudo tee /etc/sudoers.d/jobpilot <<'EOF'
jobpilot ALL=(root) NOPASSWD: /usr/bin/systemctl restart jobpilot-api
jobpilot ALL=(root) NOPASSWD: /usr/bin/journalctl -u jobpilot-api *
EOF
sudo visudo -c    # syntax sai là hỏng sudo của cả máy — check trước
```

Hai chi tiết dễ sai:
- **`/usr/bin/`, không phải `/bin/`.** Ubuntu 22.04+ dùng merged-usr, sudo resolve ra
  `/usr/bin/journalctl`; rule ghi `/bin/...` sẽ không match.
- **Trong sudoers mỗi `*` khớp *một* argument.** Rule `journalctl -u jobpilot-api *` mà lệnh
  thật là `journalctl -u jobpilot-api -n 40 --no-pager` (ba argument) thì **không khớp** → sudo
  từ chối. Dấu `*` cuối ở đây nằm cuối rule nên khớp phần còn lại; nếu bạn đổi lệnh trong
  `update.sh` thì kiểm lại. Hỏng chỗ này chỉ lộ ra ở **error path** — đúng lúc service không
  lên và bạn cần đọc log nhất, thì log không hiện.

## 3. Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=jobpilot-vps

# TLS + proxy về loopback. uvicorn vẫn bind 127.0.0.1, không mở port firewall nào.
sudo tailscale serve --bg 8000
```

Xong thì mở `https://jobpilot-vps.<tailnet>.ts.net` trên điện thoại đã cài
Tailscale cùng tài khoản.

⚠️ **Đừng dùng `tailscale funnel`.** Funnel đẩy ra Internet công khai — xem §0.

## 4. Verify (chạy thật, đừng dừng ở test xanh)

Theo đúng luật trong `CLAUDE.md`: test xanh không chứng minh nó chạy.

- [ ] `curl -fsS http://127.0.0.1:8000/health` trên VPS → `{"status":"ok",...}`
- [ ] Mở URL `.ts.net` từ **điện thoại dùng 4G, tắt wifi**. Wifi có thể đi đường
      LAN và không chứng minh được tailnet hoạt động.
- [ ] Dashboard load, chấm **LIVE** sáng (WS đã auth xong — nó chỉ sáng khi nhận
      được `hello`, không phải khi socket vừa mở).
- [ ] Chạy 1 crawl, xem progress chảy realtime ở trang Runs.
- [ ] Build 1 CV PDF → kiểm đường Docker. Chạy **lần thứ hai** nữa: lần 2 là lúc
      lộ ra lỗi quyền file nếu container ghi PDF bằng root.
- [ ] Tailor 1 job → kiểm LLM key.
- [ ] Apply 1 job ở `dry_run` → **xác nhận không có mail nào rời máy**.
- [ ] Vào trang Settings: 3 gate email phải hiện **khoá** ("host only"), không bấm được.
- [ ] **Tắt Tailscale trên điện thoại → URL phải KHÔNG vào được.** Vẫn vào được
      nghĩa là đang lộ ra ngoài → dừng ngay.
- [ ] `curl` từ một máy ngoài tailnet → phải **timeout**, không phải 401. 401
      nghĩa là gói tin tới được máy bạn.

## 5. CI/CD

`.github/workflows/ci.yml`:

- **backend** — ruff + pytest (SQLite fixture, không cần Postgres service).
- **frontend** — `tsc --noEmit` rồi `vite build`. Tách riêng vì Vite transpile mà
  **không** type-check: build xanh không chứng minh gì về types.
- **deploy** — `needs: [backend, frontend]` nên không bao giờ deploy code đỏ.
  Runner join tailnet bằng `tailscale/github-action`, ssh vào chạy `deploy/update.sh`.

Secrets cần đặt trong repo settings:

| Secret | Là gì |
|---|---|
| `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` | OAuth client trong Tailscale admin, gắn tag `tag:ci` |
| `DEPLOY_SSH_KEY` | private key; public key nằm ở `~jobpilot/.ssh/authorized_keys` |
| `DEPLOY_HOST` | tên máy trong tailnet, vd `jobpilot-vps` |
| `DEPLOY_USER` | `jobpilot` |

ACL của tailnet phải cho `tag:ci` tới host qua port 22.

`update.sh` build lại bundle **trên host**, vì token bị nướng vào bundle lúc
build — bundle build ở CI mang token placeholder của CI. Nó lấy `VITE_API_TOKEN`
từ `JOBPILOT_API_TOKEN` trong `.env` để chỉ có **một** chỗ ghi token; giữ thêm
một `web/.env.local` trên server là tạo bản sao thứ hai chờ lệch nhau rồi cho ra
một dashboard 401 với chính backend của nó.

## 6. Backup

`deploy/backup.sh` chạy hằng đêm qua `jobpilot-backup.timer`:

- `pg_dump -Fc` → khôi phục được từng bảng bằng `pg_restore`, không phải all-or-nothing.
- `jobpilot cv export` → JSON đọc được bằng mắt trên máy bất kỳ. Master CV là thứ
  **không** tái tạo được bằng cách crawl lại; DB dump thì cần đúng phiên bản
  Postgres mới restore được. Hai định dạng, hai kiểu hỏng khác nhau.
- Script **kiểm tra file khác rỗng** rồi mới báo thành công. Một job backup báo
  xanh trong khi ghi file 0 byte còn tệ hơn không có backup, vì nó khiến bạn ngừng
  kiểm tra.

Khôi phục:

```bash
pg_restore -d "postgresql://jobpilot:<pw>@127.0.0.1/jobpilot" --clean /var/backups/jobpilot/jobpilot-<stamp>.dump
.venv/bin/python -m jobpilot.cli cv import /var/backups/jobpilot/cv-<stamp>.json
```

## 7. Nếu crawl bị Cloudflare chặn

Đây là rủi ro số 1 khi rời máy nhà, và không ai verify trước được. Nếu ITviec/
TopCV/VietnamWorks bắt đầu trả 403 hoặc trang challenge từ VPS:

- Nguồn feed (WeWorkRemotely, Arbeitnow) và ATS (Greenhouse, Lever) **không** bị
  ảnh hưởng — chúng không sau Cloudflare.
- Đường lui rẻ: crawl vẫn chạy ở **laptop**, DB vẫn ở **VPS**. Chỉ cần đặt
  `DATABASE_URL` trên laptop trỏ vào Postgres của VPS qua tailnet
  (`postgresql+psycopg://jobpilot:<pw>@jobpilot-vps:5432/jobpilot`), rồi tắt
  `jobpilot-crawl.timer` trên VPS. Code không đổi một dòng nào — nó chỉ là một
  biến môi trường. Dashboard vẫn 24/7, chỉ riêng việc crawl cần laptop bật.
- Nhớ cho phép Postgres nghe trên interface tailnet nếu đi đường này
  (`listen_addresses` + `pg_hba.conf` giới hạn đúng dải `100.64.0.0/10`),
  **không** mở ra ngoài.
