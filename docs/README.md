# FraudGuard Agent Kit

Bộ cấu hình này biến nội dung mentor kỹ thuật của FraudGuard thành một quy trình
đa agent ổn định:

- Task chính là **PO/mentor** và là đầu mối duy nhất làm việc với người dùng.
- `fraudguard_code` chỉ triển khai hạng mục đã được PO phê duyệt.
- `fraudguard_reviewer` kiểm tra độc lập correctness, leakage, data safety,
  reproducibility và bằng chứng kiểm thử.
- `AGENTS.md` chứa các quy tắc chung mà mọi task/agent trong repository phải
  tuân theo.

## Cài vào repository FraudGuard

Sao chép vào thư mục gốc của repository:

```text
FraudGuard/
├── AGENTS.md
└── .codex/
    ├── config.toml
    └── agents/
        ├── fraudguard-code.toml
        └── fraudguard-reviewer.toml
```

Nếu repository đã có `AGENTS.md` hoặc `.codex/config.toml`, hãy hợp nhất nội
dung thay vì ghi đè.

Sau khi sao chép, mở một task Codex mới trong repository. Codex đọc
`AGENTS.md` và cấu hình agent khi task bắt đầu, vì vậy task đang mở trước đó có
thể chưa nhận cấu hình mới.

## Khởi động task PO

1. Mở repository FraudGuard trong Codex.
2. Tạo task mới và đặt tên `PO — FraudGuard`.
3. Dán toàn bộ nội dung trong `PO_START_PROMPT.md`.
4. Chỉ thảo luận yêu cầu và quyết định sản phẩm với task PO.
5. Chỉ nói `PHÊ DUYỆT` sau khi phạm vi, non-goals và acceptance criteria đã rõ.
6. PO sẽ tự giao việc cho `fraudguard_code`, sau đó gọi
   `fraudguard_reviewer`.

Không cần tạo task Code thủ công. Agent Code do PO sinh ra có quan hệ điều phối
rõ ràng và trả kết quả về đúng task PO.

## Luồng bắt buộc

```text
Người dùng
    ↓ quyết định
PO/mentor
    ↓ implementation packet
fraudguard_code
    ↓ diff + test evidence
fraudguard_reviewer
    ↓ PASS hoặc NEEDS_CHANGES
PO/mentor
    ↓ nghiệm thu hoặc giao vòng sửa
Người dùng
```

## Quy tắc vận hành

- PO không sửa source code.
- Code không tự đổi yêu cầu, roadmap hoặc kiến trúc.
- Reviewer không sửa code; chỉ cung cấp bằng chứng và kết luận.
- Mỗi lượt chỉ giao một hạng mục đủ nhỏ để kiểm chứng.
- Khi yêu cầu mơ hồ, agent phải báo PO thay vì tự suy diễn.
- Không có bằng chứng kiểm thử thì không được tuyên bố hoàn thành.
- Nếu Code và Reviewer bất đồng, PO đọc code/test liên quan và trình người dùng
  quyết định khi vấn đề ảnh hưởng sản phẩm hoặc kiến trúc.

## Strict Approval Mode

Bộ này bật chế độ **Strict Approval**. Với mọi yêu cầu mới, thay đổi mới hoặc
vòng sửa sau review, PO phải:

1. Lập `CHANGE REQUEST` có ID như `CR-001`, nêu mục tiêu, phạm vi/file dự kiến
   sửa, phần không sửa, rủi ro, acceptance criteria và kiểm tra dự kiến.
2. Dừng lại chờ chị trả lời đúng dạng `PHÊ DUYỆT <ID>`.
3. Chỉ sau thông điệp đó mới được tạo/giao Code agent thực hiện đúng phạm vi.

Nếu Reviewer yêu cầu sửa, PO phải tạo CHANGE REQUEST mới và xin chị phê duyệt
lại; không được tự động giao Code sửa tiếp. `ok`, `được`, `làm đi` hoặc im lặng
không được xem là phê duyệt.
