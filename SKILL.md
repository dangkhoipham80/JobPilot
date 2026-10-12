---
name: tailor-cv
description: >
  Tailor Master CV tới một Job Description cụ thể — trích requirement,
  gap-analysis, sắp xếp lại CV bằng một plan theo chỉ số, sinh cover letter,
  build PDF. Dùng khi cần điều chỉnh CV cho một job đã chọn. Nguyên tắc số 1:
  KHÔNG BỊA — chỉ nhấn mạnh/diễn đạt lại dữ kiện có thật trong Master CV.
---

# SKILL: tailor-cv

Đây là spec cho engine tailor CV của JobPilot (xem `PLAN.md`). Code tương ứng nằm ở
`jobpilot/tailor/`; số mục (§0–§5) được docstring trong code trỏ tới, nên **giữ nguyên số mục**
khi sửa file này.

## 0. Nguyên tắc tối thượng — Truthfulness

> **KHÔNG BAO GIỜ thêm kỹ năng, công nghệ, kinh nghiệm, con số, hay thành tựu
> không tồn tại trong Master CV.**

Được phép:
- ✅ **Nhấn mạnh** kinh nghiệm/skill có thật khớp JD bằng cách đưa nó lên trước.
- ✅ **Diễn đạt lại** phần summary bằng từ khoá của JD *nếu* nội dung tương đương đã có (vd JD viết "RESTful microservices" mà CV có "RESTful APIs + microservices" → ok gộp).
- ✅ **Ẩn** section, entry hoặc bullet ít liên quan để CV gọn 1 trang.
- ✅ **Sắp xếp lại** thứ tự section/project/experience/bullet theo độ liên quan.

Bị cấm:
- ❌ Thêm skill chưa từng xuất hiện (vd JD cần Kafka mà CV không có → **không** thêm).
- ❌ Bịa metric ("tăng 40% hiệu năng") nếu Master CV không ghi.
- ❌ Đổi năm/công ty/chức danh.
- ❌ Suy diễn skill ("dùng Spring Boot nên chắc biết Hibernate").

Nếu JD yêu cầu skill user **không có**: KHÔNG thêm vào CV. Thay vào đó đánh dấu trong
**gap report** để user tự quyết (học thêm / bỏ qua job / ghi chú trong cover letter là "sẵn sàng học").

**Luật này được ép bằng hình dạng dữ liệu, không phải bằng lời dặn.** Plan mà model trả về
(`tailor/schema.py:TailorPlan`) là **index-based**: nó chỉ chọn, sắp xếp và ẩn nội dung có sẵn theo
vị trí. "Thêm một skill" không phải điều model được dặn đừng làm — đó là thứ schema không biểu
diễn được. Chỗ duy nhất model được viết chữ tự do là `summary`, và `tailor/guard.py` kiểm nó bằng ba lớp:

1. **Structural** — mọi chỉ số trong plan phải trỏ vào nội dung có thật trong Master CV, không
   trùng lặp.
2. **Lexical** — mọi token trông giống tên công nghệ trong `summary` phải đã xuất hiện ở đâu đó
   trong Master CV. Văn xuôi thường thì để yên, nên vẫn diễn đạt lại được.
3. **Numeric** — mọi con số trong `summary` phải là con số Master CV có ghi (chữ số, các từ chỉ
   số như "twelve", "dozen", "doubled", và *one..ten* khi đứng trước đơn vị: "one year",
   "five times"). Lớp 2 không thấy được số, vì token của nó bắt đầu bằng chữ cái. "CV có ghi"
   gồm các section, ngày tháng, và dòng chức danh + quote ở header; **không** gồm số điện thoại
   hay địa chỉ.

Cover letter được kiểm cùng cách (`apply/letter.py`). Nguồn số được phép của nó là Master CV
cộng **tên công ty** ("Studio 6677"); `learning_note` được thêm số nằm trong requirement
`MISSING`. Tên job và địa chỉ **không** cấp phép cho con số nào: title kiểu "(5+ years)" hay địa
chỉ "12 Tôn Đản" không phải dữ kiện về ứng viên, và thư đi email thì không ai đọc trước khi gửi.

Plan vi phạm được gửi lại cho model **một** lần để sửa (`tailor/engine.py`). Sai lần hai thì
raise, không âm thầm ra một CV chưa ai kiểm.

**Rủi ro còn lại — đừng tin guard hơn mức nó làm được.**

- Lớp numeric kiểm *con số có trong CV hay không*, không kiểm *ngữ cảnh*. CV có ghi "5 members"
  thì "5 years of experience" vẫn qua, vì số 5 có trong CV.
- *one..ten* viết bằng chữ chỉ được kiểm khi đứng ngay trước một đơn vị (years, months, weeks,
  decades, percent, times, -fold); ngoài ra chúng là từ đệm ("one of the two services") và được
  bỏ qua. Số viết bằng chữ tiếng Việt ("mười hai", "gấp đôi") không được kiểm. Chữ số thì bắt
  được ở mọi ngôn ngữ.
- **Tên tháng không lớp nào kiểm.** Chúng được coi là từ thường để "since December 2024" không bị
  đọc thành tên công nghệ, nên CV ghi "Dec. 2019" mà summary viết "since March 2019" vẫn qua —
  năm thì được kiểm, tháng thì không.
- So khớp theo dãy chữ số: CV ghi "12,000" mà text viết "12000" thì bị từ chối. Viết đúng như CV.
- Thâm niên **tự tính từ ngày tháng** ("1+ years") bị từ chối nếu CV không ghi con số đó. Muốn
  summary nói vậy thì ghi nó vào Master CV.
- Văn xuôi không có số và không có tên công nghệ ("led the migration") không lớp nào kiểm. Thứ
  chặn nó vẫn là prompt và bước user đọc diff trước khi Approve.

> Sửa **Master CV** bằng câu lệnh (CV Studio) là việc khác và dùng guardrail **ngược** lại:
> ở đó dữ kiện mới là mục đích, nên luật là *provenance* (mọi thứ thêm vào phải trích được từ
> câu lệnh của user), không phải *vocabulary*. Xem `jobpilot/cv/CLAUDE.md`.

## 1. Input / Output

**Input:**
- `job`: object theo `Job` schema (§3.1 PLAN.md) — quan trọng nhất là `description_md`, `skills`, `title`, `level`, `company`. Tailor **chưa** có phòng thủ riêng chống câu lệnh chèn trong JD (ô 22 của `PLAN.md §9.1`); hiện chỉ có schema và guard giới hạn hậu quả.
- `master_cv`: `CvDocument` (JSON có cấu trúc) trong bảng `cv_versions`, scope `master` — nguồn sự thật duy nhất. Nó được đưa vào prompt dưới dạng **outline có đánh số** (`tailor/prompt.py`); mọi chỉ số trong plan trỏ về outline này.

**Output:**
- **`TailorPlan`** — `match_score`, `requirements[]`, `summary`, `section_order`, `sections[]`, `entries[]`, `changes[]`.
- **CV tailored** — `tailor/apply.py` áp plan lên Master một cách **deterministic** (cùng master + cùng plan ⇒ cùng document; Master không bị đổi). Kết quả là một row `cv_versions` mới, scope theo job, `author='agent'`, plan nằm trong `meta` — CV, lý do và diff là một bản ghi bất biến. Chạy lại thì thêm version mới, không ghi đè.
- `cv.pdf` — render JSON → `.tex` qua Jinja2 → tectonic, ra `out/cv/<scope>/`.
- Cover letter — text (bản chính) + PDF đính kèm.

## 2. Quy trình 5 bước

### Bước 1 — Trích requirement từ JD
Mỗi requirement có `text` (đúng như JD viết) và `kind`:
- `must_have`: skill/kinh nghiệm bắt buộc.
- `nice_to_have`: ưu tiên.
- `soft`: teamwork, agile, ngôn ngữ...

### Bước 2 — Gap analysis vs Master CV
Với mỗi requirement, gán `status` kèm `evidence`:
- `HAVE` — có trong Master CV (ghi rõ nằm ở đâu).
- `PARTIAL` — có liên quan gần.
- `MISSING` — không có (→ vào gap report, **không** đưa vào CV).

`match_score` = (HAVE + 0.5·PARTIAL) / tổng requirement, `must_have` tính gấp đôi; kẹp trong 0..1.

> Đây là `match_score` của **tailor**. Job còn có điểm từ lúc crawl (khớp từ khoá,
> `crawler/quality.py`) và điểm fit của intake — ba loại khác nhau, xem `jobpilot/intake/CLAUDE.md`.

### Bước 3 — Sắp xếp lại có kiểm soát

Model không sửa `.tex` và không viết lại bullet. Nó điền các trường của plan:

| Trường của plan | Được làm gì |
|---|---|
| `summary` | Chữ tự do duy nhất: 2–3 câu hướng vào role của JD, chỉ dùng công nghệ đã có trong Master CV. |
| `section_order` | Thứ tự các section. |
| `sections[].enabled` | `false` để ẩn một section ít liên quan cho CV vừa 1 trang. |
| `sections[].entry_order` / `item_order` | Thứ tự (và tập con) entry hoặc item trong section — đưa cái liên quan nhất lên đầu. |
| `entries[].bullet_order` | Thứ tự (và tập con) bullet của một entry. |
| `entries[].tech_stack_order` | Thứ tự tech stack của một entry, để tech JD cần đứng trước. |
| `changes[]` | Mỗi thay đổi kèm lý do, để user đọc ở bước duyệt. |

Không có trường nào để đổi tiêu đề, ngày tháng, công ty hay nội dung một bullet.

**Rule độ dài**: giữ CV **1 trang** bằng cách ẩn phần ít liên quan. Build xong sẽ đếm trang và
cảnh báo nếu khác 1; hiện **chưa** có vòng tự cắt (đó là ô 23 của `PLAN.md §9.1`).

### Bước 4 — Cover letter
Sinh text rồi build `cover_letter.tex` → PDF:
- Mở đầu: vị trí ứng tuyển + công ty (`job.title`, `job.company`).
- Thân: 2–3 điểm mạnh **có thật** khớp must-have, dẫn chứng từ experience/project.
- Nếu có `MISSING` quan trọng: 1 câu thể hiện tinh thần học hỏi (trung thực, không khẳng định đã biết).
- Kết: call-to-action lịch sự + thông tin liên hệ.
- Giọng: chuyên nghiệp, ngắn (<= 300 từ), không sáo rỗng.

> **Không dùng `\cvletter`** — bản `awesome-cv.cls` trong repo là bản đã trim, không
> có macro letter nào (`\recipient`, `\letteropening`, env `cvletter` đều không tồn
> tại). Template riêng ở `cv/templates/awesome_cv/cover_letter.tex.j2`, dựng bằng
> đúng những macro class thật sự có (`\makecvheader`, `\cvsection`, `cvparagraph`),
> và dùng chung `_preamble.tex.j2` với CV nên đổi theme là đổi cả hai.
>
> **Text vẫn là bản chính**: email mang text ở body (PDF không làm body được), PDF là
> file đính kèm. Build PDF hỏng thì đơn **vẫn gửi** — lý do ghi vào
> `meta.letter.pdf_error`, không nuốt im.

### Bước 5 — Build & verify
- Áp plan → `CvDocument` tailored → render `.tex` → copy class/font cần thiết vào `out/cv/<scope>/`.
- Build bằng tectonic (engine duy nhất).
- **Verify**: build thành công + số trang. Fail → job về `FAILED`, không đưa CV hỏng lên cho user duyệt.

## 3. Định dạng diff (để user duyệt)

`changes[]` mỗi phần tử:
```jsonc
{ "section": "summary", "what": "…", "reason": "khớp must-have 'distributed systems'" }
```
`what` nói cụ thể: "đưa project Lumen lên đầu" tốt hơn "sắp xếp lại project".

Trang **CV Review** hiện PDF tailored cạnh diff so với Master (`tailor/diff.py` — cùng hàm diff
mà CV Studio dùng để so hai version bất kỳ) và `gaps` (⚠️ JD cần Kafka — bạn chưa có). Slack, nếu
bật, hiện bản tóm tắt gọn của cùng dữ liệu đó.

## 4. Vòng "Sửa" (edit loop)

Khi user bấm **✏️ Sửa** và nhập instruction (vd "rút gọn summary", "đẩy project Roundtable xuống cuối", "ưu tiên Docker"):
- Tailor lại với instruction đó, **vẫn qua đúng schema và guardrail ở §0** — instruction yêu cầu bịa thì không có đường nào để thực hiện.
- Re-build, re-diff, hiện lại. Tối đa `app.edit_max_rounds` vòng (mặc định 3), sau đó user Approve hoặc Bỏ.

## 5. Checklist trước khi trả kết quả
- [ ] Plan qua cả ba lớp guardrail (structural + lexical + numeric).
- [ ] `summary` không có thành tích nào Master CV không ghi — câu văn xuôi không số thì guard **không** bắt được, phải đọc.
- [ ] `match_score` và `gaps` đã có.
- [ ] PDF build ok; số trang đã được báo.
- [ ] Cover letter đúng công ty/vị trí.
- [ ] `changes[]` đủ để user hiểu vì sao CV đổi.
- [ ] Master CV trong `cv_versions` **không** bị ghi đè — bản tailored là một row mới.
