# GITHUB OPERATING RULES
## Dự án: [Tên Dự Án] — Phiên bản 1.0

> **Hiệu lực:** Áp dụng ngay từ ngày ký kết. Mọi thành viên (người và AI agent) đều phải tuân thủ.
> **Vi phạm:** PR sẽ bị reject tự động hoặc bởi reviewer. Vi phạm lặp lại > 3 lần trong sprint sẽ được raise với PO/PM.

---

## MỤC LỤC

1. [Branching Strategy](#1-branching-strategy)
2. [Commit Rules](#2-commit-rules)
3. [Pull Request Protocol](#3-pull-request-protocol)
4. [Code Review Rules](#4-code-review-rules)
5. [Conflict Prevention Strategy](#5-conflict-prevention-strategy)
6. [File & Folder Ownership](#6-file--folder-ownership)
7. [AI Coding Agent Rules](#7-ai-coding-agent-rules)
8. [Definition of Done (DoD)](#8-definition-of-done-dod)
9. [Error Handling Protocol](#9-error-handling-protocol)
10. [Enforcement Mechanism](#10-enforcement-mechanism)

---

## 1. BRANCHING STRATEGY

### 1.1 Cấu trúc Branch Cố Định

```
main
 └── dev
      ├── be/[ten-task]
      ├── fe1/[ten-task]
      └── fe2/[ten-task]
```

| Branch | Mục đích | Ai được push? | Được merge vào đâu? |
|--------|----------|---------------|---------------------|
| `main` | Production-ready code | **Không ai được push trực tiếp** | Chỉ từ `dev` qua PR |
| `dev` | Tích hợp hàng ngày | **Không ai được push trực tiếp** | Chỉ từ personal branch qua PR |
| `be/[ten-task]` | Công việc của Backend Dev | BE Developer | `dev` |
| `fe1/[ten-task]` | Công việc của Frontend Dev 1 | FE Developer 1 | `dev` |
| `fe2/[ten-task]` | Công việc của Frontend Dev 2 | FE Developer 2 | `dev` |

### 1.2 Quy Tắc Đặt Tên Branch

**Định dạng bắt buộc:**
```
{role}/{task-id}-{mo-ta-ngan}
```

**Quy tắc:**
- `{role}` phải là: `be`, `fe1`, hoặc `fe2`
- `{task-id}` phải khớp với ID task trên task board (ví dụ: `AVE-42`)
- `{mo-ta-ngan}` chỉ dùng chữ thường và dấu gạch ngang, tối đa 30 ký tự
- **Không dùng:** chữ hoa, dấu cách, dấu gạch dưới, ký tự đặc biệt

**Ví dụ hợp lệ:**
```bash
be/AVE-42-add-user-authentication
fe1/AVE-55-build-login-form
fe2/AVE-61-refactor-dashboard-layout
```

**Ví dụ không hợp lệ:**
```bash
feature/login          # ❌ Không có role prefix, không có task-id
BE/add-auth            # ❌ Chữ hoa
be/AVE_42_auth         # ❌ Dùng dấu gạch dưới
fe1/fix                # ❌ Không có task-id, quá ngắn
hotfix/urgent-bug      # ❌ Không đúng vai trò
```

### 1.3 Quy Tắc Tạo và Xóa Branch

**Tạo branch:**
```bash
# Luôn tạo branch từ dev (đã được pull mới nhất)
git checkout dev
git pull origin dev
git checkout -b be/AVE-42-add-user-authentication
```

**Xóa branch sau merge:**
```bash
# Xóa local sau khi PR được merge
git branch -d be/AVE-42-add-user-authentication
# Xóa remote (GitHub tự động nếu cấu hình, hoặc thủ công)
git push origin --delete be/AVE-42-add-user-authentication
```

### 1.4 Quy Định Merge — Khi Nào Được Phép và Bị Cấm

**✅ Được phép merge khi:**
- Branch đã có ít nhất 1 approval từ reviewer hợp lệ
- Tất cả CI checks đều pass (lint, test, build)
- Không có unresolved conversation trên PR
- Branch đã được rebase trên `dev` mới nhất (không lag quá 2 ngày)

**🚫 Tuyệt đối cấm merge khi:**
- Merge trực tiếp vào `main` bỏ qua `dev`
- Self-merge (tự approve PR của chính mình)
- Force push vào `dev` hoặc `main`
- Merge khi CI đang fail
- Merge khi branch lag sau `dev` hơn 2 ngày mà chưa rebase

---

## 2. COMMIT RULES

### 2.1 Commit Message Format (Bắt Buộc)

**Định dạng:**
```
{type}({scope}): {mo-ta-ngan} [#{task-id}]

[Body tùy chọn — giải thích WHY, không phải WHAT]

[Footer tùy chọn — breaking changes, refs]
```

**Bảng `{type}` hợp lệ:**

| Type | Khi nào dùng |
|------|-------------|
| `feat` | Thêm tính năng mới |
| `fix` | Sửa bug |
| `refactor` | Tái cấu trúc code (không thêm feature, không fix bug) |
| `test` | Thêm hoặc sửa tests |
| `docs` | Cập nhật tài liệu |
| `style` | Format code (whitespace, semicolon — không đổi logic) |
| `chore` | Cập nhật dependencies, config build, scripts |
| `perf` | Cải thiện performance |
| `revert` | Revert commit trước |

**Bảng `{scope}` theo dự án:**

| Scope | Mô tả |
|-------|-------|
| `auth` | Authentication & authorization |
| `api` | API layer |
| `db` | Database / migrations |
| `ui` | UI components chung |
| `dashboard` | Dashboard module |
| `pipeline` | Data pipeline |
| `config` | Cấu hình hệ thống |
| `ci` | CI/CD pipeline |

**Ví dụ commit message hợp lệ:**
```
feat(auth): add JWT token refresh endpoint [#AVE-42]

Implemented sliding window refresh to avoid forcing users
to re-login every 15 minutes. Token TTL configurable via env.

Refs: #AVE-42
```

```
fix(dashboard): correct null pointer in chart renderer [#AVE-55]
```

```
test(pipeline): add unit tests for layer2 integrity checks [#AVE-61]
```

**Ví dụ commit message KHÔNG hợp lệ:**
```
fixed bug           # ❌ Thiếu type, scope, task-id
WIP                 # ❌ Work-in-progress không được commit lên remote
feat: stuff         # ❌ Thiếu scope, thiếu task-id, mô tả vô nghĩa
FEAT(AUTH): Add JWT # ❌ Chữ hoa
feat(auth): add jwt refresh endpoint and also fix the dashboard bug and update readme  # ❌ Làm nhiều việc trong 1 commit
```

### 2.2 Nguyên Tắc Atomic Commit

**Mỗi commit phải và chỉ làm đúng 1 việc.**

| ✅ Đúng | ❌ Sai |
|---------|-------|
| 1 commit thêm endpoint | 1 commit thêm endpoint + sửa bug khác |
| 1 commit thêm migration | 1 commit thêm migration + cập nhật config |
| 1 commit fix bug | 1 commit fix bug + refactor function khác |

**Cách kiểm tra:** Nếu bạn cần dùng chữ "và" trong commit message → đó là dấu hiệu bạn đang vi phạm atomic commit.

**Kỹ thuật stage chọn lọc:**
```bash
# Stage từng phần thay vì toàn bộ file
git add -p src/auth/service.py
```

### 2.3 Hành Vi Commit Bị Cấm

| Hành vi cấm | Lý do | Hậu quả |
|-------------|-------|---------|
| Commit code chưa chạy được (`python` / `node` báo syntax error) | Làm gãy CI ngay lập tức | PR bị reject auto |
| Commit file rác (`.DS_Store`, `*.pyc`, `__pycache__/`, `node_modules/`, `.env`) | Ô nhiễm repo | PR bị reject, phải cleanup |
| Commit secret/credential (API key, password, token) | Rủi ro bảo mật nghiêm trọng | Yêu cầu rotate key ngay, commit bị revert |
| Commit message là "WIP", "fix", "update", "temp", "test123" | Không truy vết được | Commit bị yêu cầu amend |
| Force push vào `dev` hoặc `main` | Xóa lịch sử của người khác | Vi phạm nghiêm trọng, raise với PO |
| Commit toàn bộ file không liên quan đến task | Gây noise, khó review | PR bị reject |
| Commit file binary lớn (>1MB) không phải asset dự án | Bloat repo | PR bị reject |

### 2.4 Quy Tắc Commit Dành Riêng Cho AI Agents

> Áp dụng khi AI agent (Claude, Cursor, Codex, v.v.) tạo hoặc đề xuất commit.

**AI agent phải:**
- Sử dụng đúng commit format ở mục 2.1
- Prefix message bằng `[AI-assisted]` khi > 50% code được AI generate:
  ```
  feat(pipeline): [AI-assisted] implement IC-002 duplicate row detection [#AVE-61]
  ```
- Chỉ commit file trong scope của task hiện tại

**AI agent bị cấm:**
- Tự ý tạo commit message chung chung kiểu `refactor: improve code quality`
- Batch nhiều thay đổi không liên quan vào 1 commit
- Commit file config hệ thống (`pyproject.toml`, `package.json`, `.github/`) trừ khi task yêu cầu rõ ràng
- Tự ý amend commit đã push

---

## 3. PULL REQUEST PROTOCOL

### 3.1 Khi Nào Bắt Buộc Tạo PR

**Luôn luôn phải tạo PR khi:**
- Merge bất kỳ personal branch nào vào `dev`
- Merge `dev` vào `main`

**Không tạo PR khi:**
- Commit trực tiếp trong personal branch của mình (không cần PR trong branch cá nhân)

### 3.2 PR Template (Bắt Buộc)

```markdown
## 📋 Mô Tả

<!-- Mô tả NGẮN GỌN task này làm gì và tại sao cần thiết -->
**Task:** [#AVE-XX](link-to-task)
**Loại thay đổi:** feat / fix / refactor / test / docs (chọn 1)

## 🔧 Những Gì Đã Thay Đổi

<!-- Liệt kê cụ thể, không dùng "nhiều thứ" hay "cải thiện" -->
- [ ] Thêm `[tên function/class/endpoint]` trong `[file path]`
- [ ] Sửa `[tên function]` để `[lý do cụ thể]`

## 🧪 Cách Test

<!-- Các bước cụ thể để kiểm tra PR này hoạt động -->
1. Checkout branch này
2. Chạy `[lệnh cụ thể]`
3. Expect: `[kết quả mong đợi]`

**Test đã chạy:**
- [ ] Unit tests: `pytest tests/unit/` — kết quả: PASS / N/A
- [ ] Integration tests: `pytest tests/integration/` — kết quả: PASS / N/A
- [ ] Manual test trên local — kết quả: PASS / N/A

## 📸 Screenshots / Output (nếu có thay đổi UI hoặc output)

<!-- Chụp ảnh trước và sau nếu có thay đổi giao diện hoặc output -->
| Trước | Sau |
|-------|-----|
| [ảnh/output cũ] | [ảnh/output mới] |

## ✅ Checklist Tự Review

**Code quality:**
- [ ] Code đã chạy được ở local (không có runtime error)
- [ ] Không có `print()` / `console.log()` debug còn sót lại
- [ ] Không có file rác (`.DS_Store`, `*.pyc`, `node_modules`)
- [ ] Không có hardcoded credential hay secret
- [ ] Tất cả function có type hints (Python) hoặc TypeScript types

**Scope control:**
- [ ] Chỉ sửa file thuộc scope của task này
- [ ] Không tự ý refactor code ngoài task
- [ ] Không thêm dependency mới (nếu có → giải thích ở mô tả)

**Collaboration:**
- [ ] Đã pull `dev` mới nhất và rebase trước khi tạo PR
- [ ] Không có conflict với `dev`

## 🤖 AI Assistance Disclosure

- [ ] PR này có sử dụng AI agent để generate code
  - Tool sử dụng: `[Claude / Cursor / Codex / Copilot]`
  - Phần nào được AI generate: `[mô tả cụ thể]`
  - Đã review output của AI: ✅ / ❌

## ⚠️ Breaking Changes

<!-- Để trống nếu không có -->
- [ ] PR này có breaking change
  - Mô tả: `[gì bị break]`
  - Migration cần thiết: `[các bước]`

## 👥 Reviewer Gợi Ý

- BE Dev: `@[username]` — cần review phần backend
- FE Dev: `@[username]` — cần review phần frontend (nếu có)
- PO/PM: `@[username]` — cần approve cho feature
```

### 3.3 Quy Trình Review Theo Vai Trò

**PR từ BE Developer (`be/` branches):**
- Reviewer bắt buộc: FE Developer 1 hoặc FE Developer 2 (1 trong 2)
- Approver bắt buộc: PO/PM (chỉ khi PR chứa business logic mới)
- Thời hạn review: **trong vòng 24h làm việc**

**PR từ FE Developer 1 (`fe1/` branches):**
- Reviewer bắt buộc: FE Developer 2 (cross-review giữa FE)
- Reviewer khuyến nghị: BE Developer (nếu có tích hợp API)
- Approver bắt buộc: PO/PM (chỉ khi PR chứa thay đổi UI có thể nhìn thấy)
- Thời hạn review: **trong vòng 24h làm việc**

**PR từ FE Developer 2 (`fe2/` branches):**
- Reviewer bắt buộc: FE Developer 1
- Reviewer khuyến nghị: BE Developer (nếu có tích hợp API)
- Approver bắt buộc: PO/PM (chỉ khi PR chứa thay đổi UI có thể nhìn thấy)
- Thời hạn review: **trong vòng 24h làm việc**

**PR từ `dev` → `main`:**
- Reviewer bắt buộc: Tất cả developer (BE + FE1 + FE2)
- Approver bắt buộc: PO/PM
- Thời hạn review: **trong vòng 48h làm việc**

### 3.4 Vai Trò Của PO/PM

**PO/PM approve khi:**
- PR chứa tính năng mới visible với người dùng
- PR thay đổi business logic hoặc workflow người dùng
- PR từ `dev` → `main`

**PO/PM KHÔNG cần approve khi:**
- Refactor nội bộ không ảnh hưởng UI/UX
- Fix bug nhỏ không đổi behavior
- Thêm/sửa tests
- Cập nhật docs

---

## 4. CODE REVIEW RULES

### 4.1 Checklist Review Bắt Buộc

Reviewer phải kiểm tra **tất cả** mục dưới đây trước khi approve:

**🔍 Logic & Correctness**
- [ ] Code thực hiện đúng những gì PR mô tả
- [ ] Không có bug rõ ràng (null pointer, off-by-one, race condition)
- [ ] Edge cases được xử lý (input rỗng, null, giá trị âm, overflow)
- [ ] Error handling đúng — lỗi không bị nuốt im lặng (`except: pass`)

**⚡ Performance**
- [ ] Không có N+1 query trong vòng lặp
- [ ] Không có blocking operation không cần thiết
- [ ] Không load toàn bộ dataset vào memory khi chỉ cần subset
- [ ] Không có vòng lặp lồng nhau O(n²) khi có giải pháp tốt hơn

**🔒 Security**
- [ ] Không có hardcoded secret, password, API key
- [ ] Input được validate và sanitize trước khi xử lý
- [ ] SQL query dùng parameterized (không string concatenation)
- [ ] File path không được tạo từ user input trực tiếp

**📐 Architecture Consistency**
- [ ] Đặt tên biến/hàm/class theo convention đã thống nhất
- [ ] Không tạo abstraction layer mới mà không thảo luận trước
- [ ] Không import module không thuộc scope
- [ ] File được đặt đúng thư mục theo ownership rules (mục 6)

**🧪 Test Coverage**
- [ ] Logic phức tạp có unit test tương ứng
- [ ] Happy path và sad path đều được test
- [ ] Test không phụ thuộc vào external state (side-effect free)

### 4.2 Cách Reject PR

**Khi reject, reviewer phải:**
1. Chọn **"Request changes"** (không phải "Comment")
2. Viết comment theo format:

```
**[REJECT]** — {Category}

**Vấn đề:** [Mô tả cụ thể vấn đề, kèm line number nếu có]
**Lý do:** [Tại sao đây là vấn đề]
**Cần sửa:** [Hướng dẫn cụ thể để fix]

Ví dụ code sửa (nếu có):
```python
# Thay vì:
result = db.query("SELECT * FROM users WHERE id=" + user_id)

# Hãy dùng:
result = db.query("SELECT * FROM users WHERE id=?", (user_id,))
```
```

**Categories cho reject:**
- `[REJECT] Security` — Vấn đề bảo mật
- `[REJECT] Architecture` — Vi phạm kiến trúc
- `[REJECT] Logic Bug` — Lỗi logic
- `[REJECT] Missing Test` — Thiếu test bắt buộc
- `[REJECT] Out of Scope` — Thay đổi ngoài phạm vi task
- `[REJECT] Convention` — Vi phạm naming/structure convention

### 4.3 Quy Tắc Phản Biện (Anti-Ego Rules)

**Reviewer phải:**
- Phản biện **code**, không phản biện **người viết code**
- Dùng câu hỏi thay vì khẳng định khi không chắc: "Đây có phải trường hợp X không?" thay vì "Code này sai"
- Ghi rõ mức độ quan trọng của comment:
  - `[BLOCKING]` — Phải sửa trước khi merge
  - `[SUGGESTION]` — Khuyến nghị nhưng không bắt buộc
  - `[QUESTION]` — Cần giải thích thêm, không cần sửa ngay

**Reviewer không được:**
- Dùng ngôn ngữ cảm tính: "code xấu", "không hiểu code này làm gì", "sao lại làm vậy"
- Comment chung chung: "cần cải thiện", "code này có vấn đề"
- Reject PR vì style preference cá nhân không thuộc convention đã thống nhất

**PR author phải:**
- Trả lời mọi comment `[BLOCKING]` trước khi request re-review
- Ghi rõ hành động đã thực hiện: "Fixed in commit abc1234" hoặc "Giữ nguyên vì [lý do]"
- Không resolve conversation của người khác

---

## 5. CONFLICT PREVENTION STRATEGY

### 5.1 Quy Tắc Pull Trước Khi Code

**Bắt buộc thực hiện MỖI BUỔI SÁNG trước khi bắt đầu code:**

```bash
git checkout dev
git pull origin dev
git checkout {your-personal-branch}
git rebase dev
```

**Bắt buộc thực hiện TRƯỚC KHI TẠO PR:**

```bash
git checkout dev
git pull origin dev
git checkout {your-personal-branch}
git rebase dev
# Giải quyết conflict nếu có
# Chạy lại tests để đảm bảo không regression
```

### 5.2 Quy Tắc Rebase vs Merge

| Tình huống | Phương pháp | Lệnh |
|------------|-------------|------|
| Cập nhật personal branch với `dev` mới nhất | **Rebase** | `git rebase dev` |
| Merge personal branch vào `dev` | **Merge** (qua PR, squash nếu branch dirty) | Qua GitHub UI |
| Merge `dev` vào `main` | **Merge** (tạo merge commit rõ ràng) | Qua GitHub UI |

**Tại sao rebase personal branch?**
- Giữ lịch sử `dev` linear và dễ đọc
- Tránh "merge commit" noise trong personal branch
- Conflict được phát hiện sớm tại local

**⚠️ Không bao giờ rebase branch public (`dev`, `main`):**
```bash
# ❌ TUYỆT ĐỐI CẤM
git checkout dev
git rebase some-other-branch
```

### 5.3 Phân Vùng Code Ownership để Giảm Conflict

**Nguyên tắc:** Mỗi file chỉ nên có 1 owner primary. Khi 2 người cùng sửa 1 file → conflict không thể tránh.

**FE1 và FE2 tránh sửa cùng file bằng cách:**
- Phân chia theo module/page (không phân chia theo layer)
- FE1 sở hữu: Module A (ví dụ: `dashboard/`, `reports/`)
- FE2 sở hữu: Module B (ví dụ: `settings/`, `auth/`)
- File shared (`components/`, `hooks/`, `styles/`) → phải thông báo qua chat trước khi sửa

**Quy trình khi buộc phải sửa file của người khác:**
1. Ping owner trong Slack/chat: "Mình cần sửa `components/Button.tsx` cho task #AVE-55, bạn có đang sửa file này không?"
2. Chờ confirm không conflict
3. Sửa xong → notify: "Đã merge, bạn rebase nhé"

---

## 6. FILE & FOLDER OWNERSHIP

### 6.1 Bảng Phân Quyền Sở Hữu Code

```
project-root/
├── backend/                    ← 🔵 BE Developer (OWNER)
│   ├── ave/
│   │   ├── pipeline/           ← 🔵 BE ONLY
│   │   ├── engines/            ← 🔵 BE ONLY
│   │   ├── models/             ← 🔵 BE ONLY
│   │   ├── storage/            ← 🔵 BE ONLY
│   │   ├── utils/              ← 🔵 BE ONLY
│   │   └── cli.py              ← 🔵 BE ONLY
│   ├── tests/                  ← 🔵 BE OWNER (FE có thể đọc)
│   └── rules/                  ← 🔵 BE OWNER
│
├── frontend/
│   ├── src/
│   │   ├── modules/
│   │   │   ├── dashboard/      ← 🟡 FE1 (PRIMARY OWNER)
│   │   │   ├── reports/        ← 🟡 FE1 (PRIMARY OWNER)
│   │   │   ├── settings/       ← 🟢 FE2 (PRIMARY OWNER)
│   │   │   └── auth/           ← 🟢 FE2 (PRIMARY OWNER)
│   │   ├── components/         ← 🔄 SHARED (thông báo trước khi sửa)
│   │   ├── hooks/              ← 🔄 SHARED (thông báo trước khi sửa)
│   │   ├── services/           ← 🔄 SHARED (thông báo trước khi sửa)
│   │   └── styles/             ← 🔄 SHARED (thông báo trước khi sửa)
│
├── docs/                       ← 🟣 PO/PM (OWNER), mọi người có thể PR
├── .github/
│   ├── workflows/              ← 🔵 BE (chủ yếu), PO/PM approve
│   └── CODEOWNERS              ← 🟣 PO/PM quản lý
├── pyproject.toml              ← 🔵 BE ONLY (dependency backend)
├── package.json                ← 🟡🟢 FE1 hoặc FE2, cần thông báo
└── README.md                   ← 🟣 PO/PM (OWNER)
```

**Chú giải:**
- 🔵 BE Developer là owner
- 🟡 FE Developer 1 là owner
- 🟢 FE Developer 2 là owner
- 🔄 Shared — phải thông báo trước khi sửa
- 🟣 PO/PM là owner

### 6.2 Quy Tắc Sửa File Ngoài Ownership

**Khi developer cần sửa file ngoài ownership của mình:**

1. **Tạo issue/comment** trên task board: "Cần sửa `backend/ave/models/finding.py` để thêm field X cho FE integration"
2. **Thông báo owner** trong chat: tag trực tiếp, không gửi trong channel chung
3. **Chờ phản hồi** — owner có 4 giờ làm việc để respond
4. **Nếu cấp thiết** và owner không respond → escalate lên PO/PM
5. **Reviewer phải là owner** của file bị sửa

**AI agent bị cấm sửa file ngoài ownership** không có explicit instruction từ con người. Xem chi tiết ở Mục 7.

---

## 7. AI CODING AGENT RULES

> **Áp dụng cho:** Claude, Cursor, GitHub Copilot, Codex, và mọi AI assistant được dùng để generate code.
> **Trách nhiệm:** Developer sử dụng AI **chịu hoàn toàn trách nhiệm** về code được AI tạo ra. "AI làm vậy" không phải lý do hợp lệ.

### 7.1 AI CHỈ ĐƯỢC PHÉP

```
✅ Sửa code trong phạm vi file/module của task hiện tại
✅ Thêm function/method mới vào file thuộc ownership của developer
✅ Viết test cho code đã tồn tại
✅ Viết docstring/comment cho code hiện có
✅ Suggest refactor nhỏ BÊN TRONG function đang sửa (không thay đổi interface)
✅ Generate boilerplate code theo pattern đã có trong codebase
```

### 7.2 AI BẮT BUỘC PHẢI

```
📋 Đọc file GITHUB_OPERATING_RULES.md này trước khi bắt đầu task
📋 Đọc file liên quan trong codebase để hiểu context trước khi sửa
📋 Tuân thủ naming convention đang có trong file được sửa
📋 Giữ nguyên style của file hiện tại (nếu file dùng double quote → không đổi sang single quote)
📋 Comment code bằng ngôn ngữ đang được dùng trong codebase (nếu codebase comment bằng tiếng Anh → dùng tiếng Anh)
📋 Báo cáo (không tự sửa) nếu phát hiện vấn đề ngoài scope của task
```

**Cụ thể về "đọc context trước khi code":**
```
Trước khi sửa file X, AI phải đọc:
1. File X đầy đủ (không chỉ đọc đoạn cần sửa)
2. Các file mà X import
3. Phần liên quan trong GITHUB_OPERATING_RULES.md
4. Task description đầy đủ (không chỉ đọc tóm tắt)
```

### 7.3 AI BỊ TUYỆT ĐỐI CẤM

```
🚫 Tự ý refactor toàn bộ file khi chỉ được yêu cầu sửa 1 function
🚫 Đổi tên biến/function/class đã tồn tại (breaking change với code khác)
🚫 Thêm dependency mới vào pyproject.toml / package.json mà không được yêu cầu rõ ràng
🚫 Xóa code mà không hiểu rõ code đó được dùng ở đâu
🚫 Sửa file thuộc ownership của người khác (xem Mục 6)
🚫 Generate code "placeholder" hoặc "TODO" với ý định sẽ quay lại sau
🚫 Tự ý thay đổi database schema hoặc migration
🚫 Sửa file trong .github/workflows/ trừ khi task yêu cầu rõ ràng
🚫 Generate code mà không có test khi task yêu cầu có test
🚫 Tạo file mới trong thư mục không thuộc scope của task
🚫 Ignore linting errors bằng cách thêm suppress comment (# noqa, // eslint-disable)
```

### 7.4 Quy Trình Làm Việc Với AI Agent

**Trước khi bắt đầu task:**
```
Developer → AI Agent:
"Đọc file GITHUB_OPERATING_RULES.md.
Task hiện tại: [mô tả task từ task board]
File scope: [list files được phép sửa]
Ownership: [vai trò của developer]
Đọc xong xác nhận trước khi bắt đầu."
```

**Khi AI đề xuất thay đổi ngoài scope:**
```
AI: "Mình nhận thấy function X có thể refactor để tốt hơn..."
Developer phải: Reject đề xuất này, ghi chú lại để tạo task riêng nếu cần.
Developer không được: Accept và commit thay đổi ngoài scope.
```

**Checklist trước khi commit code do AI generate:**
```
☐ Đọc từng dòng code — không commit blindly
☐ Hiểu được mỗi dòng code làm gì
☐ Kiểm tra AI không sửa file ngoài scope
☐ Kiểm tra AI không thêm dependency không được yêu cầu
☐ Chạy tests để xác nhận không regression
☐ Xóa comment thừa mà AI tự thêm ("This function handles...")
```

### 7.5 AI Output Review Standard

**Code do AI generate phải đạt tiêu chuẩn:**

| Tiêu chí | Yêu cầu |
|----------|---------|
| Type safety | Đầy đủ type hints (Python) hoặc TypeScript types — không có `any` |
| Error handling | Mọi exception được xử lý cụ thể, không có bare `except:` |
| Naming | Theo convention của codebase, không theo style riêng của AI |
| Complexity | Không tạo abstraction layer không cần thiết |
| Dependencies | Không import library mới nếu stdlib có thể giải quyết |

---

## 8. DEFINITION OF DONE (DoD)

Một task được coi là **DONE** khi và chỉ khi đáp ứng **tất cả** tiêu chí sau:

### 8.1 Tiêu Chí Kỹ Thuật

| # | Tiêu chí | Áp dụng cho |
|---|----------|-------------|
| 1 | Code chạy được không có runtime error | Mọi task |
| 2 | CI pipeline pass (lint + build + test) | Mọi task |
| 3 | Không có linting error mới (so với `dev`) | Mọi task |
| 4 | Unit test coverage không giảm so với `dev` | Task có logic mới |
| 5 | Integration test pass nếu có thay đổi API | Task thay đổi API |
| 6 | Database migration có rollback script | Task có DB migration |
| 7 | Không có merge conflict với `dev` | Mọi task |

### 8.2 Tiêu Chí Chất Lượng

| # | Tiêu chí | Người kiểm tra |
|---|----------|----------------|
| 1 | Ít nhất 1 reviewer đã approve | Reviewer |
| 2 | Mọi `[BLOCKING]` comment đã được resolve | PR author |
| 3 | Code không phá vỡ module khác (no regression) | CI + Reviewer |
| 4 | Không có secret/credential trong code | CI (automated) |
| 5 | PR template đã điền đầy đủ | PR author |

### 8.3 Tiêu Chí Business (Chỉ Với Feature PR)

| # | Tiêu chí | Người kiểm tra |
|---|----------|----------------|
| 1 | PO/PM đã approve | PO/PM |
| 2 | Behavior khớp với acceptance criteria trong task | PO/PM |

### 8.4 Những Gì KHÔNG Cần Test

Để tránh over-engineering, các task sau **không bắt buộc** có unit test:
- Thay đổi config (YAML, JSON config files)
- Cập nhật documentation
- Thay đổi CSS/style thuần (không có logic)
- Rename file/variable không có logic thay đổi

---

## 9. ERROR HANDLING PROTOCOL

### 9.1 Khi Phát Hiện Lỗi Sau Merge

**Triage ngay trong 15 phút:**

```
Mức độ Critical (production down, data loss risk):
→ Tạo incident trong Slack channel #incidents
→ Assign fix ngay cho BE Developer
→ Notify PO/PM
→ Target: hotfix trong 2 giờ

Mức độ High (feature broken, nhưng không ảnh hưởng toàn hệ thống):
→ Tạo bug task với priority High
→ Assign cho owner của code bị lỗi
→ Target: fix trong sprint hiện tại

Mức độ Low (minor bug, workaround có sẵn):
→ Tạo bug task với priority Normal
→ Backlog cho sprint tiếp theo
```

### 9.2 Cách Trace Commit Gây Lỗi

**Bước 1 — Git bisect để tìm commit gây lỗi:**
```bash
git bisect start
git bisect bad HEAD                  # HEAD hiện tại là bad
git bisect good {commit-hash-known-good}  # Commit cuối cùng biết là good
# Git sẽ checkout từng commit để test
# Sau mỗi lần test:
git bisect good   # Nếu commit đang check là good
git bisect bad    # Nếu commit đang check là bad
# Kết thúc khi git xác định được commit gây lỗi
git bisect reset  # Trở về HEAD
```

**Bước 2 — Kiểm tra commit gây lỗi:**
```bash
git show {bad-commit-hash}           # Xem diff của commit
git log --oneline {bad-commit}^..{bad-commit}  # Context xung quanh
```

**Bước 3 — Tìm PR tương ứng:**
```bash
git log --merges --oneline | grep {bad-commit}
# Hoặc tìm trên GitHub: search commit hash trong PRs
```

### 9.3 Cách Rollback An Toàn

**Option A — Revert commit (ưu tiên, an toàn nhất):**
```bash
# Tạo branch fix từ dev
git checkout dev
git pull origin dev
git checkout -b be/AVE-99-revert-bad-commit

# Revert commit cụ thể
git revert {bad-commit-hash}
# Giải quyết conflict nếu có
# Test kỹ

# Tạo PR với title: "revert: [mô tả commit bị revert] [#AVE-99]"
```

**Option B — Hotfix (chỉ dùng khi revert gây quá nhiều conflict):**
```bash
git checkout dev
git pull origin dev
git checkout -b be/AVE-99-hotfix-[mo-ta]

# Sửa trực tiếp vấn đề
# Test kỹ hơn bình thường

# Tạo PR — phải có ít nhất 2 approval thay vì 1
```

**⛔ Không được dùng:**
```bash
git push --force origin dev    # Tuyệt đối cấm
git push --force origin main   # Tuyệt đối cấm
```

### 9.4 Fix Không Gây Side Effect

**Checklist bắt buộc trước khi merge fix:**

```
☐ Fix chỉ thay đổi đúng phần gây lỗi (không sửa thêm gì khác)
☐ Tất cả existing tests vẫn pass
☐ Viết regression test cho bug vừa fix (ngăn tái phát)
☐ Kiểm tra module phụ thuộc vào code vừa fix
☐ Reviewer là người có context về phần code bị fix
☐ Nếu fix trong BE, FE Developer được notify để test integration
```

---

## 10. ENFORCEMENT MECHANISM

### 10.1 GitHub Actions — Pipeline Bắt Buộc

Các check sau chạy tự động trên **mọi PR** và phải pass trước khi cho phép merge:

#### Check 1 — Branch Name Validator
```
Trigger: Khi PR được tạo
Logic:
  - Extract tên branch từ PR
  - Validate regex: ^(be|fe1|fe2)/[A-Z]+-\d+-[a-z0-9-]+$
  - Nếu fail: comment vào PR với hướng dẫn rename, block merge
```

#### Check 2 — Commit Message Linter
```
Trigger: Khi commit được push lên remote
Logic:
  - Parse từng commit trong branch
  - Validate: type phải trong allowed list, scope phải có, task-id phải có
  - Nếu fail: mark status check failed, block merge
  - Tool: commitlint với config custom
```

#### Check 3 — File Ownership Validator
```
Trigger: Khi PR được tạo hoặc update
Logic:
  - Đọc CODEOWNERS file
  - Kiểm tra mọi file trong PR diff có reviewer là owner không
  - Nếu có file thuộc ownership người khác mà không có approval từ owner: block merge
  - Tool: GitHub CODEOWNERS tích hợp sẵn
```

#### Check 4 — Secret Scanner
```
Trigger: Mọi commit push
Logic:
  - Scan toàn bộ diff cho patterns: API key, password, token, private key
  - Patterns: AKIA[0-9A-Z]{16}, ghp_[a-zA-Z0-9]{36}, -----BEGIN RSA PRIVATE KEY-----
  - Nếu phát hiện: block push ngay lập tức, notify team qua Slack
  - Tool: git-secrets hoặc truffleHog hoặc GitHub Secret Scanning
```

#### Check 5 — PR Template Completeness
```
Trigger: Khi PR được tạo hoặc edited
Logic:
  - Parse PR body
  - Kiểm tra các section bắt buộc có nội dung (không phải còn là placeholder comment)
  - Kiểm tra checklist items có được check ([ ] vs [x])
  - Nếu thiếu: comment danh sách section còn thiếu, block merge
```

#### Check 6 — Test Suite
```
Trigger: Mọi push vào PR branch
Logic:
  - Run: pytest tests/unit/ (backend)
  - Run: npm run test (frontend)
  - Run: pytest tests/integration/ (chỉ khi có thay đổi integration-relevant)
  - Fail nếu bất kỳ test nào fail
  - Report coverage, fail nếu coverage giảm > 5% so với base branch
```

#### Check 7 — Linting & Formatting
```
Trigger: Mọi push vào PR branch
Logic:
  - Backend: ruff check . && ruff format --check .
  - Frontend: eslint src/ && prettier --check src/
  - Fail nếu có bất kỳ error nào
  - Warning được log nhưng không block merge
```

### 10.2 GitHub CODEOWNERS Configuration

```
# .github/CODEOWNERS

# Default owner (PO/PM reviews everything as backup)
*                           @po-pm-username

# Backend exclusive ownership
/backend/                   @be-developer-username
/rules/                     @be-developer-username
/pyproject.toml             @be-developer-username

# Frontend module ownership
/frontend/src/modules/dashboard/    @fe1-developer-username
/frontend/src/modules/reports/      @fe1-developer-username
/frontend/src/modules/settings/     @fe2-developer-username
/frontend/src/modules/auth/         @fe2-developer-username

# Shared frontend (both FE devs must review)
/frontend/src/components/    @fe1-developer-username @fe2-developer-username
/frontend/src/hooks/         @fe1-developer-username @fe2-developer-username
/frontend/src/services/      @fe1-developer-username @fe2-developer-username

# Documentation (PO/PM owns)
/docs/                      @po-pm-username
/README.md                  @po-pm-username

# CI/CD (BE owns, PO/PM must approve)
/.github/workflows/         @be-developer-username @po-pm-username
/.github/CODEOWNERS         @po-pm-username
```

### 10.3 Branch Protection Rules (Cấu Hình GitHub Settings)

**Cho branch `main`:**
```
✅ Require pull request reviews before merging
  - Required approving reviews: 2
  - Dismiss stale pull request approvals when new commits are pushed: true
  - Require review from Code Owners: true
✅ Require status checks to pass before merging
  - Branch Name Validator: REQUIRED
  - Commit Message Linter: REQUIRED
  - Secret Scanner: REQUIRED
  - Test Suite: REQUIRED
  - Linting: REQUIRED
✅ Require branches to be up to date before merging: true
✅ Restrict who can push to matching branches: [chỉ GitHub Actions bot]
✅ Allow force pushes: DISABLED
✅ Allow deletions: DISABLED
```

**Cho branch `dev`:**
```
✅ Require pull request reviews before merging
  - Required approving reviews: 1
  - Require review from Code Owners: true
✅ Require status checks to pass before merging
  - Tất cả checks như main: REQUIRED
✅ Require branches to be up to date before merging: true
✅ Allow force pushes: DISABLED
✅ Allow deletions: DISABLED
```

### 10.4 Automated Notifications

```
Slack Notifications (qua GitHub → Slack integration):
- PR created → #dev-prs channel
- PR approved → PR author được notify
- PR review requested → Reviewer được tag trực tiếp
- CI failed → PR author được tag trong #dev-alerts
- Secret detected → TOÀN BỘ TEAM được alert trong #security-alerts
- PR merged to main → #releases channel
```

### 10.5 Xử Lý Vi Phạm

| Vi phạm | Hậu quả tự động | Hậu quả thủ công |
|---------|-----------------|------------------|
| Branch name sai | PR bị block | Developer phải rename và recreate PR |
| Commit message sai | Push bị reject (pre-receive hook) | Developer phải amend và force-push vào personal branch |
| Force push vào `dev`/`main` | Bị block ở tầng repo settings | Escalate lên PO/PM ngay |
| Secret trong code | Push bị block + alert toàn team | Rotate credentials ngay, audit scope của exposure |
| CI fail | PR bị block | Developer fix trước khi re-request review |
| Self-merge | Không thể (settings) | N/A |
| PR không có approval | Không thể merge | Request review từ đúng người |

---

## PHỤ LỤC A — Quick Reference Card

### Checklist Hàng Ngày

```
Đầu ngày:
☐ git pull origin dev
☐ git rebase dev (trên personal branch)

Trước khi code:
☐ Đọc task description đầy đủ
☐ Xác nhận scope: file nào được phép sửa
☐ Nếu dùng AI agent: load rules vào context AI

Khi commit:
☐ git add -p (chọn đúng phần cần commit)
☐ Commit message theo format: type(scope): description [#task-id]
☐ Mỗi commit 1 việc duy nhất

Trước khi tạo PR:
☐ git rebase dev (lần cuối)
☐ Chạy test local
☐ Tự review code của mình 1 lần
☐ Điền PR template đầy đủ
```

### Danh Sách Lệnh Hay Dùng

```bash
# Sync với dev hàng ngày
git checkout dev && git pull origin dev && git checkout - && git rebase dev

# Tạo branch mới đúng cách
git checkout dev && git pull origin dev && git checkout -b be/AVE-42-mo-ta-task

# Commit đúng format
git add -p && git commit -m "feat(auth): add token refresh [#AVE-42]"

# Xem khác biệt với dev trước khi tạo PR
git diff dev..HEAD --stat

# Undo commit cuối (trước khi push)
git reset --soft HEAD~1

# Tìm commit gây bug
git log --oneline | head -20
git bisect start && git bisect bad HEAD && git bisect good {known-good-hash}
```

---

## PHỤ LỤC B — Onboarding Checklist cho Member Mới

```
☐ Đọc toàn bộ tài liệu này
☐ Clone repo, chạy được ở local
☐ Tạo branch test với đúng format: {role}/ONBOARD-00-test-setup
☐ Tạo 1 commit với đúng format
☐ Tạo PR draft với PR template điền đầy đủ
☐ Nhờ reviewer confirm format đúng
☐ Xóa branch test
☐ Cấu hình git hooks local (nếu team dùng)
☐ Cài pre-commit: pip install pre-commit && pre-commit install
```

---

*Tài liệu này được review và cập nhật vào đầu mỗi sprint. Mọi thay đổi phải được PO/PM approve qua PR vào `docs/GITHUB_OPERATING_RULES.md`.*

**Phiên bản:** 1.0 | **Ngày tạo:** 2026-05-03 | **Owner:** PO/PM
