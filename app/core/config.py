MAX_UPLOAD_FILE_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_TEXT_CHARS = 500_000
MAX_REQUEST_BODY_BYTES = 2 * MAX_UPLOAD_FILE_BYTES + 1024 * 1024
# Ngân sách cho toàn bộ phần xử lý của một request (khởi động worker, trích xuất, diff).
COMPARISON_TIMEOUT_SECONDS = 30.0
# Số worker chạy đồng thời trong một API process; hết slot trả 503, không xếp hàng.
MAX_ACTIVE_WORKERS = 2
# Trần kích thước kết quả worker gửi về; kết quả hợp lệ lớn nhất cỡ vài MiB.
MAX_WORKER_RESULT_BYTES = 32 * 1024 * 1024
