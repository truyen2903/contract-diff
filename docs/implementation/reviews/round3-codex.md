# Round 3 — Codex rebuttal

Đã đọc brief Round 3, toàn bộ báo cáo Round 2 tổng hợp, coding style profile, mã nguồn, test và §3.2 của kế hoạch v2. Không sửa/tạo/xóa file, không chạy git ghi; `git status --short` trước/sau giống nhau.

**[CONFIRMED]** Đã chạy đúng lệnh pytest với cấu hình không ghi bytecode/cache:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_ADDOPTS='--capture=sys'
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Output: **`5 passed in 1.57s`**. Đây là test baseline, chưa nghiệm thu các phương án hardening.

Các probe dưới đây chạy bằng `.venv\Scripts\python.exe -c $probe`, với `$probe` chỉ tồn tại trong bộ nhớ và `PYTHONDONTWRITEBYTECODE=1`. Mỗi lệnh hoàn tất dưới 60 giây. Prototype không phải thay đổi đã được triển khai trong repository.

## Phản hồi phản biện

Các mục đã xử lý bằng self-correction Round 2: `CL/ADV-CL-007`, `CL/ADV-CL-008`, `CL/ADV-CL-013`, `AG/ADV-CX-004`, `AG/ADV-CX-008`; ngưỡng cụ thể trong `CL/ADV-CL-001` và `AG/ADV-CX-001` cũng đã được rút. Phản hồi các phần còn lại:

- **CL/ADV-CL-001 — ACCEPT —** Ngoài việc rút ngưỡng 4.000.000, nay chấp nhận hoãn admission guard ở Phase A vì chưa có ngưỡng đạt yêu cầu tương thích; xem O6.
- **AG/ADV-CX-001 — PARTIAL —** Chấp nhận bác bỏ tích token 4.000.000; chưa chấp nhận ngưỡng thay thế 40.000–50.000 token vì chưa có bằng chứng bảo vệ latency hoặc phù hợp corpus.
- **CL/ADV-CL-003 — ACCEPT —** Chấp nhận PDF mở được bằng mật khẩu rỗng; cách diễn giải trước đây của tôi về brief quá chặt, trong khi v2 nêu cụ thể `PDFPasswordIncorrect`; xem O1.
- **CL/ADV-CL-005 — ACCEPT —** Middleware có sẵn xử lý được cả header và byte thực, đồng thời cleanup multipart đã được kiểm chứng; rút đề xuất tự viết limiter; xem O2.
- **AG/ADV-CX-002 — ACCEPT —** Đã tái hiện `PDF.close()` dựng đủ 2.000 `Page` sau khi iterator dừng ở 101; chuyển tiền kiểm ra trước `pdfplumber.open`; xem O4.
- **AG/ADV-CX-003 — ACCEPT —** Đã tái hiện đủ bốn loại lỗi bị bỏ lọt; mở rộng phân loại tại ranh giới thư viện, giữ lỗi hạ tầng theo luồng 500; xem O5.
- **AG/ADV-CX-005 — ACCEPT —** Encryption dictionary tồn tại không đủ để kết luận phải từ chối; rút yêu cầu kiểm `doc.encryption is not None`; xem O1.
- **AG/ADV-CX-006 — ACCEPT —** Phần HTTP trong extractor đã rút ở Round 2; nay rút thêm trần text dùng chung cho `/extract` và việc extractor tự tính separator. Chỉ kiểm fulltext tại service so sánh PDF; xem O6.
- **AG/ADV-CX-007 — PARTIAL —** Chấp nhận trần toàn cục cho phép `/text` và `/extract` nhận nhiều byte hơn nhu cầu tối thiểu; không chọn bảng path 31/16/4 MiB vì tăng cấu hình và 4 MiB sai với JSON escape. Hai mã 413 khác nhau không tự thân là lỗi contract, nhưng tôi rút cặp mã đó để đơn giản hóa; xem O2.

## Lập trường O1–O8

### O1 — ACCEPT: chấp nhận PDF mở được bằng mật khẩu rỗng

Mở bằng `password=""`; không từ chối chỉ vì có encryption dictionary. `PDFPasswordIncorrect` và lỗi PDF thuộc tập phân loại ở O5 được chuyển thành **400 `INVALID_OR_ENCRYPTED_PDF`**.

**[CONFIRMED]** Probe dùng PDF RC4 dựng trong bộ nhớ, gọi:

```python
with pdfplumber.open(BytesIO(raw), password="") as pdf:
    print(pdf.doc.encryption is not None, pdf.pages[0].extract_text())
```

Output: **`True ABC`**.

V2 §3.2 nêu `PDFPasswordIncorrect`; brief không xác định rõ ngoại lệ owner-only. Vì vậy, tôi chọn cách hiểu giữ hành vi trích xuất hiện có. Thí nghiệm chứng minh khả năng đọc mẫu này, không chứng minh mức phổ biến của owner-only PDF trong hợp đồng thực tế.

### O2 — ACCEPT: middleware có sẵn, một trần toàn cục 31 MiB

Chọn:

```python
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_size=31 * 1024 * 1024,
)
```

Giữ kiểm tra **15 MiB/tệp** tại service. Không thêm bảng giới hạn theo path trong Phase A.

**[CONFIRMED]** Starlette **1.8.0** đã cài có middleware này. Probe ASGI đặt trần 1.000 byte cho kết quả:

| Request | Kết quả |
|---|---|
| Đúng 1.000 byte | 200 |
| `Content-Length: 1001` | 413, không gọi `receive` gốc |
| Hai chunk 600 + 500, thiếu `Content-Length` | 413 |
| Hai chunk 600 + 500, khai `Content-Length: 1` | 413 |
| Multipart vượt trần giữa stream | 413; stream tạm đã đóng |

Cleanup được kiểm chứng bằng thay `SpooledTemporaryFile` bằng `BytesIO`: **`CLEANUP 1 [True]`**.

**[CONFIRMED]** `json.dumps(..., ensure_ascii=True).encode()` với hai chuỗi 500.000 ký tự:

```text
"ệ" →  6.000.032 byte
"😀" → 12.000.032 byte
```

Do đó 4 MiB không phù hợp; chỉ nâng lên khoảng 6 MiB cũng chưa bao phủ ký tự ngoài BMP.

**Chốt 413:** bỏ hai mã `REQUEST_TOO_LARGE`/`UPLOAD_TOO_LARGE`; service dùng một mã **`PAYLOAD_TOO_LARGE`**. Chấp nhận ngoại lệ transport của middleware có sẵn: response có thể là plain text hoặc `{"detail":"Content Too Large"}`, không có `error_code`. Client nhận diện chung bằng HTTP 413; tài liệu phải ghi rõ ngoại lệ này.

31 MiB là giới hạn body độc lập, không bảo đảm mọi JSON có lượng whitespace tùy ý đều được nhận, cũng không phải trần RAM sau khi giải mã JSON.

### O3 — ACCEPT: yêu cầu `%PDF-` tại byte 0

Kiểm `stream.read(5) == b"%PDF-"`, sau đó tua về đầu.

**[CONFIRMED]** Ghép tiền tố HTML/JS trước fixture PDF rồi mở bằng pdfplumber cho:

```text
BYTE0 False FIRST1024 True PAGES 2
```

Quét 1.024 byte sẽ nhận mẫu này. Chọn byte 0 để có chính sách upload đơn giản, rõ ràng, chấp nhận việc từ chối một số file parser vẫn đọc được.

Đây không phải biện pháp chống mọi polyglot. Phản ví dụ chỉ chứng minh tiền tố HTML vượt cửa kiểm 1.024 byte; chưa chứng minh khai thác XSS trong ứng dụng hiện tại.

### O4 — ACCEPT: tiền kiểm bằng pdfminer trước pdfplumber

Chọn luồng:

```python
doc = PDFDocument(PDFParser(stream), password="")
count = sum(1 for _ in islice(PDFPage.create_pages(doc), 101))
```

`count == 0` → **400**; `count > 100` → **422 `PDF_TOO_MANY_PAGES`**. Chỉ khi hợp lệ mới `seek(0)` rồi mở bằng pdfplumber.

**[CONFIRMED]** Probe PDF 2.000 trang, mock constructor `pdfplumber.pdf.Page`:

```text
Trong with: count=101, PAGE_OBJECTS=2000, 0,6513 giây
Tiền kiểm:  count=101, PAGE_OBJECTS=0,    0,0732 giây
```

`inspect.getsource(PDF.close)` xác nhận vòng `for page in self.pages`. Bằng chứng Round 2 của tôi chỉ đo trước lúc đóng nên bỏ sót chi phí quan trọng này.

Tiền kiểm tránh dựng toàn bộ `pdfplumber.Page` cho tài liệu vượt trần; không bảo đảm chi phí đọc xref hoặc xử lý cấu trúc PDF luôn nhỏ.

### O5 — PARTIAL: mở rộng lỗi parser tại phạm vi gọi thư viện

Chốt tập nhận diện:

```text
PDFException, PSException, MalformedPDFException,
ValueError, TypeError, IndexError, AttributeError
```

`PSException` bao gồm `PSEOF` và `PSSyntaxError`. Với `PdfminerException`, tháo wrapper qua exception trong `args[0]` đã được xác minh; chỉ chuyển thành `InvalidPDFError` khi nguyên nhân thuộc tập trên. Wrapper không phân loại được tiếp tục là lỗi server.

Chỉ đặt `try/except` quanh thao tác thư viện: dựng document/parser, tiêu thụ iterator trang, dựng trang, `extract_text` và cleanup. Việc tạo warnings, dict kết quả và kiểm chính sách của ứng dụng nằm ngoài các khối này. Service chỉ ánh xạ exception miền đã xác định.

**[CONFIRMED]** Gọi extractor hiện tại trên PDF dựng trong bộ nhớ:

```text
/MediaBox [0 0 (x) 100] → MalformedPDFException
/Rotate /Invalid       → TypeError
/CropBox [0 0]          → IndexError
/Pages là inline dict  → AttributeError tại create_pages
```

**[CONFIRMED]** Stream lỗi I/O tạo **`PdfminerException` với `args[0]` là `OSError`**. Prototype phân loại giữ wrapper chứa `OSError`, `MemoryError`, `RuntimeError` theo luồng server; chuyển wrapper chứa `TypeError` sang `InvalidPDFError`. `TypeError` phát sinh trong code ứng dụng sau lời gọi thư viện vẫn truyền ra ngoài.

Giới hạn còn lại: kiểu `TypeError` không thể phân biệt tuyệt đối dữ liệu hỏng với bug nội bộ thư viện. Phạm vi bắt hẹp và các mẫu tái hiện giảm việc che lỗi; không tạo bảo đảm tuyệt đối.

### O6 — PARTIAL: hoãn trần token; áp trần fulltext cho `/pdf`

**Không thêm admission guard token/độ phức tạp trong Phase A.** Tôi rút lập trường bắt buộc phải có guard ngay khi chưa đưa ra được ngưỡng đủ bằng chứng.

**[CONFIRMED]** Chạy `diff_words` thật:

```text
2.000 token lặp:     tích 4.000.000 → 0,8394 giây
3.000 token gần riêng biệt: 9.000.000 → 0,0091 giây
```

Tích token phân loại sai rõ rệt. Fixture nhỏ và dữ liệu nhân bản chưa đủ chứng minh ngưỡng nào không từ chối hợp đồng thực tế tới 100 trang.

Chốt cụ thể:

- Giữ `MAX_TEXT_CHARS = 500_000` cho `/text`.
- Áp cùng trần cho **mỗi fulltext `/pdf`**, tính cả separator do `build_document_text` tạo, tại `comparison_service.compare_document`; vượt → **422 `TEXT_TOO_LONG`**.
- Không áp trần này lên `/documents/extract`; extractor không cần biết separator.
- Sau kiểm giới hạn, dùng fast path chuỗi bằng nhau/token bằng nhau cho cả hai đường so sánh.
- Giữ `autojunk=False`, không cắt văn bản, không thêm hard timeout.

Trần trang và trần ký tự là hai điều kiện độc lập: PDF dưới 100 trang vẫn có thể vượt 500.000 ký tự. Đây là lựa chọn chính sách theo v2, chưa có bằng chứng rằng mọi hợp đồng 100 trang đều nằm dưới trần.

CPU DoS với hai chuỗi khác nhau, nhiều token lặp **vẫn chưa được giải quyết**; không mô tả Phase A là đã kiểm soát thời gian diff.

### O7 — ACCEPT: schema health và prefix tại router tổng

Chọn `HealthResponse` có `status: Literal["ok"]`, đăng ký `prefix="/health"`, route con `""`, không cần service chuyển tiếp.

**[CONFIRMED]** Prototype FastAPI:

```text
GET /api/v1/health → 200 {"status":"ok"}, không Location
OpenAPI status → type:string, const:"ok"
```

Lựa chọn này khớp quy ước `response_model` và prefix trong coding style profile, với chi phí rất nhỏ.

### O8 — ACCEPT: kiểm dùng chung tại document service và kiểm cả hai file trước

Đặt helper kiểm size/magic tại `document_service`, gọi từ `extract_document`. Dùng `seek(0, 2)`/`tell()`, tua đầu, đọc đúng 5 byte rồi tua đầu; không đọc toàn file để tính kích thước.

Với `/pdf`, `compare_document` gọi helper cho **cả hai stream trước khi trích xuất file đầu**. Có thể giữ kiểm tra lặp trong `extract_document` để lời gọi độc lập luôn được bảo vệ; chi phí thêm chỉ là seek và đọc header.

**[CONFIRMED]** Prototype với stream theo dõi số byte đọc:

```text
0 byte       → 400
15.728.640   → chấp nhận, read(5), vị trí cuối kiểm tra = 0
15.728.641   → 413, không đọc nội dung
File thứ hai sai magic → extractor được gọi 0 lần
```

Không thấy phản biện nào trong Round 2 bác bỏ vị trí service này. Kiểm cả hai file trước giúp tránh trích xuất vô ích, còn middleware O2 mới giới hạn body trước khi service được gọi.