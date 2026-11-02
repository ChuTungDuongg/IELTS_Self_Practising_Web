# Import bản nháp có cấu trúc (`ielts-draft-import-v1`)

> **Phân loại tài liệu: CURRENT (đã sửa từ NEEDS UPDATE).** Tài liệu chuẩn cho chủ đề này; đối chiếu boundaries/API từ source, không xác minh deployment đang chạy.
> Mục đích: import bản nháp có cấu trúc (`ielts-draft-import-v1`). Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/services/draft_import.py).
> Đọc cùng [hướng dẫn module hiện hành](modules/assets-transfer.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả tests/benchmark thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

Draft Import nhận văn bản và đáp án đã được chép lại từ ảnh chụp hoặc bản scan. Công cụ không chạy OCR hay AI inference. Lệnh tạo một `Test` mới, version 1, trạng thái `DRAFT`. Mở Builder URL được trả về để kiểm tra và publish theo workflow bình thường.

Manifest hư cấu có thể chạy ngay nằm ở [docs/examples/draft-import-manifest.json](examples/draft-import-manifest.json).

Chạy từ `backend/`:

```sh
uv run python -m app.import_draft path/to/manifest.json --owner-user-id ADMIN_UUID
```

Asset paths được tính tương đối từ thư mục chứa `manifest.json`; nên đặt trong thư mục con `assets/`. Importer từ chối absolute paths, traversal `..`, file thiếu, extensions không hỗ trợ, file signatures sai và file vượt upload size limits hiện có. File hợp lệ được copy qua provider cấu hình bởi `get_asset_storage` và liên kết với version mới; input files vẫn là nguồn local kể cả khi destination là S3/R2. Khi import thất bại, service thoát transaction rồi dọn file thuộc operation sau khi kiểm durable database references. Mất commit acknowledgement hoặc database không truy cập được không được dẫn tới xóa assets có thể đã commit; trường hợp đó có thể cần đối soát.

## Manifest

```json
{
  "format": "ielts-draft-import-v1",
  "title": "Fictional IELTS Practice Test",
  "description": "Optional source notes",
  "modules": []
}
```

`modules` có thể chứa tổ hợp của tối đa một module `READING`, một `LISTENING` và một `WRITING`. Importer từ chối trùng module type. Module titles là tùy chọn. `recommended_duration_seconds` cũng tùy chọn; giá trị thiếu mặc định là 3600 cho Reading, 1800 cho Listening và 3600 cho Writing. Giá trị dương được cung cấp tường minh được giữ nguyên. Questions và passage blocks không cần UUIDs; importer tạo IDs và giữ chúng ổn định qua Builder fetch/save.

Chỉ đặt `"allow_incomplete": true` khi nguồn chưa có answer key hoặc có question numbers chưa biểu diễn được. Trong mode này, đáp án thiếu được lưu thành empty keys và các khoảng trống question numbering tường minh được giữ trong unpublished draft. Các structural validations khác vẫn có hiệu lực. Draft chưa thể publish cho đến khi giải quyết keys và numbering. Mặc định là `false`.

### Reading

Reading có `passages`. Mỗi passage có `title`, một hoặc nhiều `blocks`, và từ không đến nhiều `question_groups`. Block là `heading` hoặc `paragraph` có `text`. Paragraph `label` tùy chọn; nếu thiếu sẽ tạo A, B, C,...; label được cung cấp sẵn được giữ nguyên. Matching Headings targets dùng `"Paragraph A"` hoặc `"A"` và phải xác định đúng một paragraph.

### Listening

Listening có tối đa bốn `sections`, tương ứng Builder Listening Parts. Mỗi section có `title` và `question_groups`. Đường dẫn `audio` cấp module là tùy chọn. Mô hình audio duy nhất vẫn là một Listening audio asset dùng chung. Thiếu audio tạo Draft warning.

### Writing

Writing có `tasks`, mỗi task gồm `task_number` là 1 hoặc 2, `prompt`, `task_type` tùy chọn và `minimum_recommended_words` tùy chọn. `task_type` là structured authoring tag, không phải hệ phân loại IELTS chính thức. Task 1 nhận `LINE_GRAPH`, `BAR_CHART`, `PIE_CHART`, `TABLE`, `MIXED_CHARTS`, `PROCESS`, `MAP_PLAN`, `OBJECT_SYSTEM_DIAGRAM` hoặc `OTHER_VISUAL`. Task 2 nhận `OPINION`, `DISCUSS_BOTH_VIEWS`, `DISCUSS_BOTH_VIEWS_AND_OPINION`, `ADVANTAGES_DISADVANTAGES`, `ADVANTAGES_OUTWEIGH_DISADVANTAGES`, `PROBLEM_SOLUTION`, `CAUSE_SOLUTION`, `TWO_PART_QUESTION` hoặc `OTHER_ESSAY`. Bỏ `task_type` để giữ trạng thái chưa phân loại; importer không suy loại từ prompt text. Task 1 có thể có đường dẫn `image`; Task 2 không được có ảnh. Task thiếu được biểu diễn bằng fixed empty task slot của Builder và có warning. Hướng dẫn số từ chuẩn là 150 cho Task 1 và 250 cho Task 2 nếu không cung cấp giá trị khác.

## Nhóm câu hỏi

Dùng chính xác tên `question_type` trong question registry hiện tại:

`multiple_choice`, `multiple_choice_multiple`, `true_false_not_given`, `yes_no_not_given`, `text_completion`, `matching_headings`, `matching`, `matching_information`, `matching_features`, `matching_sentence_endings`, `summary_completion_word_list`, `plan_labelling`, `map_labelling`, `diagram_labelling`, `form_completion`, `note_completion`, `table_completion`, `flow_chart_completion`, `summary_completion`, `sentence_completion` và `short_answer`.

Mỗi group có thể có `instruction`; thiếu instruction được chấp nhận kèm warning. Với câu hỏi thông thường, cung cấp `questions` gồm `prompt` và `answer`. `number` tùy chọn; nếu thiếu sẽ đánh số theo thứ tự trong module. Số được cung cấp sẵn được giữ nguyên, nhưng module hoàn chỉnh phải đánh đúng từ 1 đến N, không thiếu/trùng và nằm trong 1–40. Numbering mơ hồ hoặc sai làm import thất bại trừ khi `allow_incomplete=true`; trùng số luôn làm import thất bại.

Với `true_false_not_given`, đáp án là `TRUE`, `FALSE` hoặc `NOT_GIVEN`; với `yes_no_not_given`, là `YES`, `NO` hoặc `NOT_GIVEN`. Hệ thống câu hỏi hiện có chuẩn hóa chữ hoa/thường và các biến thể khoảng trắng đơn giản. Giá trị không hợp lệ làm import thất bại.

Với `multiple_choice`, mỗi câu có `options`, ví dụ `[{"key":"A","text":"River"},{"key":"B","text":"Hill"}]`, và `answer` là key như `"A"`. `multiple_choice_multiple` dùng mảng, ví dụ `"answer": ["A", "B"]`. Một shared multi-select question chiếm một IELTS number cho mỗi lựa chọn bắt buộc. Nếu bỏ đáp án, đặt `min_selections` bằng `max_selections`, hoặc cung cấp `number` và `end_number` bao gồm cả hai đầu, ví dụ 13 và 14; importer kiểm số lựa chọn khớp khoảng số. Câu tiếp theo bắt đầu sau khoảng đó. Candidate answers không có thứ tự.

Với `matching_headings`, đặt `options` ở cấp group; mỗi câu có `target` như `"Paragraph A"` và `answer` là option key. `matching`, `matching_features` và `matching_sentence_endings` dùng group options/question answers tương tự. `matching_information` dùng paragraph label như `"A"` làm đáp án và ánh xạ tới block ID. Matching groups có `allow_option_reuse`.

Với `short_answer` và đáp án văn bản, `answer` là string hoặc mảng các phương án được chấp nhận. Có thể đặt `max_words`, `max_numbers` cho từng câu. Registered evaluator phía server vẫn là nơi quyết định kết quả.

## Điền chỗ trống `{{gap}}`

Dùng `content` và một phần tử `answers` cho mỗi `{{gap}}`, theo thứ tự đọc. `numbers` là mảng số câu tường minh tùy chọn. Có thể thay bằng `questions` với một đáp án mỗi gap. Không cung cấp đồng thời `answers` và `questions`.

```json
{
  "question_type": "note_completion",
  "content": ["Course benefits:", "good {{gap}}", "close to {{gap}}"],
  "answers": ["reputation", "home"]
}
```

`text_completion`, `summary_completion_word_list`, `note_completion`, `form_completion`, `flow_chart_completion`, `summary_completion` và `sentence_completion` dùng các dòng string. `table_completion` dùng `content` dạng các hàng chứa string cells, ví dụ `[["Place", "Feature"], ["River", "{{gap}}"]]`; `columns` cung cấp column labels tương ứng hoặc mặc định `Column 1`, `Column 2`,... `summary_completion_word_list` còn cần group `options` và mỗi đáp án là option key.

Importer biến mỗi marker thành một structured GAP có ID tạo mới, liên kết với một question ID tạo mới. Thứ tự text quanh gaps được giữ nguyên. Hỗ trợ nhiều gaps cùng dòng, gaps liền nhau, ở đầu hoặc cuối. Text/note/table segment models giữ empty boundary text khi canonical structure yêu cầu. Literal markers không được lưu trong các structured layouts này. Ngoại lệ là `diagram_labelling`: Builder prompt format hiện có chủ đích dùng một literal `{{gap}}` cho mỗi diagram question.

## Ảnh và audio

`plan_labelling` và `map_labelling` yêu cầu group `image`, group `options` và question answers. Reading questions còn cần normalized marker positions `x`, `y` trong khoảng 0 đến 1. Visual model hiện tại của Listening không lưu markers. `diagram_labelling` yêu cầu group `image`; mỗi câu có `box` (`x`, `y`, `width`) và `arrow` (`start_x`, `start_y`, `end_x`, `end_y`) bằng normalized coordinates. `prompt` của diagram question được thêm một `{{gap}}` nếu chưa có. Writing Task 1 có thể có `image`; Listening có thể có một `audio` cấp module.

Ảnh được hỗ trợ: PNG, JPEG, WebP. Audio được hỗ trợ: MP3, M4A, AAC, WAV, Ogg. Nội dung file phải khớp extension.

## Kiểm tra dữ liệu

Tùy chọn `allow_incomplete` chỉ nới điều kiện đầy đủ của bản nháp; các kiểm tra cấu trúc và an toàn vẫn có hiệu lực.

Fatal errors dừng import và không để lại test hoặc copied asset: JSON/schema sai, question types không biết, đáp án sai, numbering trùng/không canonical, matching target thiếu, gap count không khớp answer count, assets không an toàn/sai định dạng, hoặc structural Builder validation errors. Thông báo chỉ rõ manifest path hoặc Builder field cần sửa.

Readiness warnings đi kèm Draft tạo thành công gồm: thiếu Listening audio, ít hơn ba Reading passages hoặc bốn Listening sections, ít hơn 40 câu trong Reading/Listening module, Writing tasks chưa đủ và group instructions bị thiếu. Trước publish, administrator cần rà OCR ambiguity, paragraph labels, answer keys, visual marker placement, diagram geometry và audio synchronization.

## Ví dụ hoàn chỉnh bằng dữ liệu hư cấu

Lưu nội dung dưới đây thành `manifest.json` cạnh `assets/fictional-chart.png` nếu muốn có ảnh tùy chọn. Bỏ thuộc tính `image` để chạy ví dụ không cần asset.

```json
{
  "format": "ielts-draft-import-v1",
  "title": "Fictional River Town Practice",
  "description": "Entirely invented practice material.",
  "modules": [
    {
      "type": "READING",
      "title": "Reading",
      "passages": [
        {
          "title": "The Imaginary River Town",
          "blocks": [
            {"type": "heading", "text": "A town made for a story"},
            {"type": "paragraph", "label": "A", "text": "River Town is a fictional place beside a blue canal. Its library opened in 2012."},
            {"type": "paragraph", "label": "B", "text": "Residents use small boats to visit the library after sunset."}
          ],
          "question_groups": [
            {
              "question_type": "true_false_not_given",
              "instruction": "Do the statements agree with the passage?",
              "questions": [
                {"number": 1, "prompt": "River Town is a real city.", "answer": "FALSE"},
                {"number": 2, "prompt": "The library opened in 2012.", "answer": "TRUE"}
              ]
            },
            {
              "question_type": "matching_headings",
              "instruction": "Match each paragraph to a heading.",
              "options": [
                {"key": "i", "text": "The town and its library"},
                {"key": "ii", "text": "Evening journeys"}
              ],
              "questions": [
                {"number": 3, "target": "Paragraph A", "answer": "i"},
                {"number": 4, "target": "Paragraph B", "answer": "ii"}
              ]
            },
            {
              "question_type": "note_completion",
              "instruction": "Complete the notes.",
              "content": ["Library opened in {{gap}}", "Residents travel by {{gap}}"],
              "answers": ["2012", "boat"]
            }
          ]
        }
      ]
    },
    {
      "type": "LISTENING",
      "title": "Listening",
      "sections": [
        {
          "title": "Section 1",
          "question_groups": [
            {
              "question_type": "multiple_choice",
              "instruction": "Choose one answer.",
              "questions": [
                {
                  "number": 1,
                  "prompt": "Where will the fictional meeting take place?",
                  "options": [
                    {"key": "A", "text": "The library"},
                    {"key": "B", "text": "The canal bridge"}
                  ],
                  "answer": "A"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "WRITING",
      "tasks": [
        {"task_number": 1, "task_type": "PIE_CHART", "prompt": "Describe a fictional chart showing library visits in River Town.", "minimum_recommended_words": 150},
        {"task_number": 2, "task_type": "OPINION", "prompt": "Discuss whether an imagined town should add more boat routes.", "minimum_recommended_words": 250}
      ]
    }
  ]
}
```
