# Đóng góp cho JobPilot

[English](CONTRIBUTING.md) · **Tiếng Việt**

Cảm ơn bạn đã ghé xem. JobPilot là công cụ cho một người dùng, chạy trên máy của chính bạn, nên
đóng góp có ích nhất là thứ bạn tự thấy cần: một parser đọc đúng một site, một nguồn mới cho phép
crawl, một template CV, một bug chỉ lộ ra với dữ liệu thật.

## Luật mà mọi thay đổi phải giữ

Đây không phải sở thích về phong cách. Pull request nào phá một trong các luật này sẽ không được
merge.

1. **Không bịa kinh nghiệm.** Tailor chỉ được sắp xếp lại, bỏ bớt hoặc diễn đạt lại những gì đã có
   trong CV. Không bao giờ thêm skill, công việc hay con số. Guardrail nằm ở `jobpilot/tailor/`;
   luật nằm ở [`SKILL.md`](SKILL.md) §0.
2. **Mọi thứ rời khỏi máy đều phải có người duyệt.** Ngoại lệ duy nhất là kênh email sau khi người
   dùng đã bật nó. Không bao giờ tự động nộp trên LinkedIn và không bao giờ scrape LinkedIn.
3. **Không đưa dữ liệu cá nhân vào repo.** Repo này công khai. Đừng commit CV thật, địa chỉ email
   thật của nhà tuyển dụng hay thư thật trong hộp thư — dù ở code, test, docs, commit message hay
   pull request. Test dùng CV hư cấu trong `jobpilot/cv/sample.py`. Nếu bạn export CV của mình, giữ
   đuôi `.local.json` (`my-cv.local.json`); `.gitignore` khớp theo đúng đuôi đó.
4. **Không bao giờ ghi đè Master CV.** Bản tailor được build ra `out/cv/<scope>/`.
5. **Tôn trọng robots.txt, điều khoản dịch vụ và rate limit.** Đọc hết `robots.txt` trước khi viết
   scraper. Nguồn nào lỗi thì ghi log rồi bỏ qua, không retry vô hạn.
6. **Secret nằm trong `.env`.** Không log, không commit token, và không commit file database.

## Cài đặt

Bạn cần Python 3.11+, Node 20, PostgreSQL và
[tectonic](https://tectonic-typesetting.github.io/) (để build PDF).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[all,dev]'
playwright install chromium          # chỉ cần cho scraper ITviec / VietnamWorks

cp .env.example .env                 # đặt DATABASE_URL và JOBPILOT_API_TOKEN
python -c "from jobpilot.api.security import generate_token; print(generate_token())"
psql -U postgres -c "CREATE DATABASE jobpilot;"
alembic upgrade head

make api                             # backend ở :8000
make web                             # dashboard ở :5173, mở terminal thứ hai
```

Backend từ chối khởi động nếu token là giá trị mẫu hoặc ngắn hơn 20 ký tự. Cùng giá trị đó đặt
trong `web/.env.local` dưới tên `VITE_API_TOKEN` (xem `web/.env.example`).

Database mới bắt đầu với một CV rỗng. Điền nó trong CV Studio; phần lớn code không cần CV thật để
làm việc.

## Trước khi mở pull request

Chạy đúng những gì CI chạy:

```bash
ruff check jobpilot                                   # ruff được ghim version trong extra dev
pytest jobpilot/tests -q
cd web && npx tsc --noEmit && npm run build
```

- Test chạy trên fixture SQLite nên không cần Postgres. CI đặt `JOBPILOT_API_TOKEN` là một giá trị
  từ 20 ký tự trở lên khi chạy; hãy làm vậy nếu bạn không có `.env`.
- CI không chạy `black --check`, còn `make lint` thì có. Cây code chưa từng được format lại, nên
  `make lint` sẽ fail ở những file bạn không đụng tới. Dùng `ruff check jobpilot`.
- Bộ test không phủ migration. Nếu bạn đổi schema, hãy chạy `alembic upgrade head` trên một
  Postgres thật.

Test xanh là chưa đủ với code chạm vào thế giới bên ngoài. Dự án này đã nhiều lần có parser qua
hết test mà vẫn sai trên site thật.

- Sửa scraper, tailor hay luồng apply? Chạy thật luồng đó và đọc kết quả.
- Sửa template Jinja, `jobpilot/cv/latex.py`, `awesome-cv.cls` hay `fontawesome.sty`? Build lại
  PDF.
- Ghi trong pull request bạn đã chạy gì và thấy gì.

## Quy trình

- Tạo nhánh từ `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- `main` được bảo vệ. Thay đổi đi qua pull request, hai check `backend` và `frontend` phải xanh,
  và force push bị chặn.
- Fork repo rồi mở pull request từ fork của bạn. Chỉ maintainer mới merge được, nên mọi thay đổi
  từ bên ngoài đều được họ review và duyệt trước. CI trên pull request từ fork cũng chờ maintainer
  duyệt rồi mới chạy.
- Commit message theo [Conventional Commits](https://www.conventionalcommits.org/), ví dụ
  `fix(crawl): measure the dedup window from first sight`.
- **Mọi thứ trên GitHub đều bằng tiếng Anh**: commit message, tiêu đề và mô tả pull request,
  issue. Tài liệu thiết kế trong repo có thể bằng tiếng Việt.
- Mỗi pull request chỉ một thay đổi. Mô tả nó làm gì, vì sao, bạn đã kiểm tra thế nào, và chỗ nào
  bạn chưa chắc.

## Quy ước

- **Python**: 3.11+, có type hint, code và comment bằng tiếng Anh.
- **Database**: Postgres là nguồn sự thật duy nhất. Đổi schema thì phải có migration Alembic;
  đừng sửa schema bằng tay.
- **State**: mọi thay đổi trạng thái đi qua REST API. Dashboard web và Slack đều là client của nó.
- **Scraper** kế thừa `crawler/base.py:BaseScraper` và chuẩn hoá về schema `Job` chung, với
  `id = "<source>:<native_id>"`.
- **Text trong CV** không bao giờ chứa LaTeX thô. Nó dùng một tập con markdown nhỏ — `**bold**`,
  `` `tech` ``, `~tech~`, `[label](url)` — và mọi thứ còn lại được escape trong
  `jobpilot/cv/latex.py`.
- **Frontend**: React, Vite, TypeScript, Tailwind, shadcn/ui. Dashboard song ngữ; chuỗi UI mới
  phải có ở cả `en` và `vi` trong `web/src/i18n/`, thiếu một bên là lỗi `tsc`.
- **Mạng**: uvicorn chỉ bind `127.0.0.1`. Đừng thêm đường code nào bind `0.0.0.0`.

## Luật chi tiết nằm ở đâu

Luật của từng vùng code, cùng những cái bẫy đã phải trả giá, nằm trong file `CLAUDE.md` của chính
thư mục đó. Chúng được viết cho [Claude Code](https://claude.com/claude-code) nhưng cũng là quy
ước cho người. Các file này, cùng `PLAN.md`, `SKILL.md`, `PHASES.md` và `DEPLOY.md`, đều bằng
tiếng Việt.

| File | Nội dung |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | nguyên tắc, lệnh, quy ước cắt ngang nhiều vùng |
| [`jobpilot/crawler/CLAUDE.md`](jobpilot/crawler/CLAUDE.md) | thêm nguồn mới, robots, các nguồn đã loại, bẫy selector và fetch |
| [`jobpilot/cv/CLAUDE.md`](jobpilot/cv/CLAUDE.md) | thêm template, macro bắt buộc, bẫy Jinja và LaTeX |
| [`jobpilot/intake/CLAUDE.md`](jobpilot/intake/CLAUDE.md) | đọc JD dán vào và chấm độ khớp |
| [`jobpilot/companies/CLAUDE.md`](jobpilot/companies/CLAUDE.md) | gộp tên nhà tuyển dụng, liên hệ HR, nơi nhận đơn |
| [`jobpilot/llm/CLAUDE.md`](jobpilot/llm/CLAUDE.md) | provider và model theo từng việc, schema, đo chi phí |
| [`jobpilot/api/CLAUDE.md`](jobpilot/api/CLAUDE.md) | prefix `/api`, auth và ranh giới mạng, hợp đồng phân trang |
| [`jobpilot/apply/CLAUDE.md`](jobpilot/apply/CLAUDE.md) | outcome, đồng bộ hộp thư, PDF cover letter |
| [`jobpilot/analytics/CLAUDE.md`](jobpilot/analytics/CLAUDE.md) | facet và độ phủ, parse lương |
| [`web/src/CLAUDE.md`](web/src/CLAUDE.md) | màu và chart, bẫy React, phân trang ở frontend |
| [`web/src/i18n/CLAUDE.md`](web/src/i18n/CLAUDE.md) | dashboard song ngữ hoạt động thế nào |

[`PHASES.md`](PHASES.md) là nhật ký từng phase: các quyết định và những bug chỉ lộ ra khi chạy
thật. Đọc phần của vùng code bạn sắp sửa.

## Issue

Mở issue bằng tiếng Anh. Với bug, ghi bạn đã chạy gì, mong đợi gì và chuyện gì đã xảy ra. Với bug
của parser, ghi nguồn và URL của tin. Xoá token, CV của bạn và địa chỉ email của bất kỳ ai trước
khi dán log.

## Giấy phép

Khi đóng góp, bạn đồng ý rằng phần đóng góp của mình được phát hành theo [giấy phép MIT](LICENSE).
File của bên thứ ba giữ điều khoản riêng; xem mục Giấy phép trong [README](README.vi.md).
