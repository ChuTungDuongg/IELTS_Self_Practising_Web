# Thiết kế biên soạn Note Completion

> **Kiểm toán tài liệu: HISTORICAL.** Tài liệu tham khảo lịch sử; không phải hợp đồng hiện hành.
> Mục đích: Thiết kế biên soạn Note Completion. Đối chiếu mã nguồn `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [triển khai](../../../backend/app/services/auth.py).
> Đọc cùng [mô-đun/hướng dẫn hiện hành](../../modules/identity.md); [audit và giới hạn](../../DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

## Kết quả mong muốn

Thay luồng biên soạn độc lập cũ dựa trên `layout.nodes` của Note Completion bằng mô hình tài liệu ghi chú chuyên biệt. Người biên soạn chỉnh sửa trực tiếp các khối ghi chú có ngữ nghĩa, nhập `{{gap}}` hoặc dùng **Insert gap** để tạo câu hỏi được liên kết tại vị trí con trỏ, và thấy cùng tiêu đề, đề mục, dấu đầu dòng, thụt lề và chỗ trống nội tuyến trong Builder Preview, Candidate và Review.

## Phạm vi và ràng buộc

- Chỉ thay đổi `note_completion`; hành vi Form, Flow-chart, Summary, Sentence, Text, Table và Diagram tiếp tục dùng triển khai hiện có.
- PostgreSQL tiếp tục là nguồn chuẩn; mọi xác thực/đánh giá nằm trong FastAPI.
- Tái sử dụng cấu hình câu hỏi TEXT, schema đáp án và bộ đánh giá hiện có.
- Không thêm thư viện văn bản giàu định dạng hoặc lưu `{{gap}}` trong nội dung được lưu trữ.
- Bảo toàn câu hỏi gắn với UUID, đáp án và cấu hình khi thay đổi văn bản, kiểu trình bày, thụt lề, thứ tự khối hoặc vị trí chỗ trống.
- Bảo toàn cách đánh số toàn cục Reading/Listening bằng cách nhận số câu hỏi cơ sở do Builder cung cấp.

## Mô hình dữ liệu

`config.layout` của Note Completion trở thành:

```json
{
  "kind": "NOTE",
  "title": "HIRING A PUBLIC ROOM",
  "blocks": [
    {
      "id": "<uuid>",
      "style": "BULLET",
      "indent": 0,
      "segments": [
        { "id": "<uuid>", "type": "TEXT", "text": "the " },
        { "id": "<uuid>", "type": "GAP", "question_id": "<uuid>" },
        { "id": "<uuid>", "type": "TEXT", "text": " Room – seats 100" }
      ]
    }
  ],
  "columns": [],
  "rows": [],
  "nodes": []
}
```

Các tập hợp cũ rỗng giữ tương thích tuần tự hóa `StructuredLayout`, còn `blocks` là biểu diễn Note chuẩn. Kiểu khối gồm `HEADING`, `TEXT`, `BULLET` và `EXAMPLE`; tiêu đề ghi chú tùy chọn được lưu riêng trong `layout.title`. Mức thụt lề là số nguyên từ 0 đến 3. Danh tính đoạn, khối, chỗ trống và câu hỏi là UUID.

Bố cục Note được lưu phải có ít nhất một khối không rỗng. Mỗi GAP tham chiếu một câu hỏi của nhóm, mỗi câu hỏi được tham chiếu đúng một lần và mọi câu hỏi liên kết dùng đáp án TEXT hợp lệ. Bản nháp Builder ban đầu chưa lưu có thể chứa một khối TEXT trống và không có câu hỏi; chỉ có thể lưu sau khi có nội dung hợp lệ và ít nhất một chỗ trống.

## Hành vi biên soạn

Trình biên tập sở hữu một span văn bản `contentEditable` cho mỗi đoạn TEXT và một nút React cho mỗi đoạn GAP. Khi span đang hoạt động chứa một hoặc nhiều token `{{gap}}` hoàn chỉnh, chỉ span đó được tách từ trái sang phải. Mỗi token tạo câu hỏi mới và UUID GAP với `max_words: 2`, `max_numbers: 1` và `{kind: "TEXT", accepted: ["answer"], case_sensitive: false}`. Các đoạn và câu hỏi hiện có không bị thay đổi.

Thao tác Insert gap thực hiện cùng phép tách tại vị trí con trỏ đã ghi nhớ. Enter tạo khối bên dưới: BULLET tiếp tục bằng BULLET, HEADING tiếp tục bằng BULLET, TEXT tiếp tục bằng TEXT và EXAMPLE tiếp tục bằng TEXT. Điều khiển kiểu khối và thụt lề chỉ thay đổi cách trình bày. Di chuyển khối hoặc chỗ trống đổi thứ tự các đối tượng hiện có, sau đó số thứ tự chuẩn được suy ra từ thứ tự khối rồi đến thứ tự đoạn.

Kéo chỗ trống lấy chính đối tượng đoạn đó khỏi khối nguồn rồi chèn vào đoạn TEXT đích tại vị trí con trỏ chuột. Thao tác này tuyệt đối không tạo câu hỏi thay thế. Xóa chỗ trống hợp nhất văn bản liền kề và chỉ xóa câu hỏi liên kết của nó. Xóa khối không có chỗ trống diễn ra ngay; xóa khối có chỗ trống dùng hộp thoại xác nhận chung và liệt kê số các câu hỏi bị ảnh hưởng.

## Hiển thị

Bộ hiển thị Note chuyên biệt căn giữa tiêu đề không rỗng, in đậm khối HEADING, tự thêm dấu đầu dòng cho khối BULLET, phân biệt văn bản EXAMPLE và thụt lề nhất quán theo ngữ nghĩa. Mỗi GAP hiển thị các thuộc tính đích câu hỏi hiện có, số câu hỏi và ô nhập gọn ngay giữa văn bản xung quanh. Candidate, Preview và Review dùng chung bộ hiển thị này.

## Chuẩn hóa dữ liệu cũ

FastAPI chuẩn hóa `nodes` NOTE cũ trước khi xác thực schema. Mỗi node cũ trở thành một khối mà không suy đoán quan hệ liền kề: TEXT trở thành khối kiểu TEXT chứa một đoạn TEXT; GAP trở thành khối kiểu TEXT chứa một đoạn GAP. Danh tính UUIDv5 suy ra từ vị trí nhóm/node giúp chuẩn hóa lặp lại vẫn ổn định. Khối hiện đại được chuẩn hóa mà không thay đổi UUID hợp lệ. Đầu ra đã chuẩn hóa xóa `nodes` và dùng `blocks`.

## Xác thực và kiểm thử

Kiểm tra tính toàn vẹn frontend và cả hai luồng xác thực tham chiếu backend so sánh danh sách GAP Note theo thứ tự với tập câu hỏi của nhóm, từ chối bản trùng, tham chiếu không xác định và đối tượng mồ côi. Mô hình Pydantic backend cưỡng chế UUID, kiểu, thụt lề, cấu trúc đoạn, khối lưu trữ không rỗng và giới hạn tiêu đề. Kiểm thử bao quát mô hình, chuyển đổi phím tắt/dán, chèn tại con trỏ, danh tính ổn định, kéo chỗ trống, thứ tự, kiểu/thụt lề, thao tác phá hủy, chuẩn hóa cũ, trả lời nội tuyến của thí sinh, điều khiển Builder và các bộ kiểm thử Text/Table/cấu trúc khác hiện có.
