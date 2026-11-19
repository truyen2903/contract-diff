# Báo cáo phản biện kế hoạch đồ án

**Kết luận sơ bộ: kế hoạch hiện tại không đủ cơ sở để cam kết hoàn thành trong 16 tuần với một sinh viên làm 20–25 giờ/tuần.** Vấn đề chính là phạm vi quá rộng, thiết kế alignment còn lỗi logic, và phương pháp đánh giá chưa đủ để chứng minh các giả thuyết.

Tôi đã đối chiếu các file trong workspace với mã nguồn được cung cấp, chạy một số phản chứng trực tiếp trên `diff_words`, và kiểm tra tài liệu chính thức cho các điểm kỹ thuật quan trọng. Không sửa file. Môi trường Python hiện thiếu FastAPI, pdfplumber và SciPy, nên chưa xác nhận được hành vi API/PDF bằng thực thi toàn bộ ứng dụng. Kiểm tra thu thập test báo không có ca kiểm thử.

Các ngưỡng chất lượng, thời gian chạy và quy mô dữ liệu trong kế hoạch hiện là **mục tiêu hoặc giả định**, chưa phải kết quả thực nghiệm.

## 1. Đối chiếu hiện trạng mã nguồn

### F01. Kế hoạch mô tả sai một phần nhiễu mà baseline thực sự phát hiện

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 1.1, hạn chế 1 và 3; Mục 5.5; Mục 8.2.
- **Vấn đề cụ thể:** Baseline bỏ qua khoảng trắng khi tạo token. Chạy mã thật cho kết quả:

  ```text
  diff_words("a b", "a  b")  → []
  diff_words("a b", "a\nb")  → []
  ```

  Vì vậy, ngắt dòng hoặc ngắt trang chỉ làm thay đổi khoảng trắng **không tự động tạo ra hàng loạt diff giả**. Header/footer thay đổi, sai thứ tự đọc hoặc từ bị tách mới là các trường hợp khác cần đo riêng.
- **Vì sao nguy hiểm:** Kế hoạch đang lấy một phần hạn chế không đúng làm động cơ nghiên cứu, rồi dự kiến chứng minh cải thiện trên hạn chế đó. Kịch bản baseline “đỏ rực toàn bộ từ Điều 4 đến Điều 7” cũng chưa được kiểm chứng.
- **Đề xuất sửa cụ thể:** Tách benchmark thành các nhóm: chỉ thay khoảng trắng; thêm header/footer; tách một từ thành nhiều token; thay thứ tự đọc; di chuyển điều khoản. Ghi nhận đầu ra baseline thật trước khi viết nhận định hoặc kịch bản demo. Bằng chứng nằm ở [text_diff.py](C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py:6).

### F02. Mô tả `SequenceMatcher` thành thuật toán LCS là thiếu chính xác

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 1.1, hạn chế 2; Mục 2.1; Chương 2 dự kiến.
- **Vấn đề cụ thể:** `SequenceMatcher` tìm khối khớp liên tiếp dài nhất rồi xử lý đệ quy hai phía; không phải thuật toán giải LCS tổng quát hay bảo đảm edit script ngắn nhất. Quan hệ với Ratcliff–Obershelp cũng cần trình bày đúng mức. [Tài liệu Python](https://docs.python.org/3/library/difflib.html).
- **Vì sao nguy hiểm:** Suy luận sai về thuật toán nền dẫn đến giải thích sai kết quả baseline và lựa chọn đối chứng.
- **Đề xuất sửa cụ thể:** Mô tả chính xác thuật toán đang dùng, tách nó khỏi LCS và Myers. Khẳng định được từ code là **không có nhãn `MOVED`**; điều khoản đổi vị trí có thể được biểu diễn bằng thêm/xóa, nhưng không nên khẳng định một mẫu đầu ra cố định cho mọi hợp đồng.

### F03. Baseline không cung cấp edit script đủ để tái tạo nguyên văn tài liệu mới

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 7.1, tính chất Reconstruction; Mục 3.2, giữ baseline.
- **Vấn đề cụ thể:** Với cùng `old_text = "a b"`, hai đích `"a b"` và `"a  b"` đều cho `changes == []`. Không thể dùng cùng đầu vào và cùng danh sách thay đổi để khôi phục chính xác cả hai đích. `compare_text` còn có thể trả `is_identical=False` nhưng `changes=[]`, do hai trường dùng hai khái niệm tương đương khác nhau. Xem [comparison_service.py](C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/services/comparison_service.py:4).
- **Vì sao nguy hiểm:** Property test được đề xuất chắc chắn thất bại nếu yêu cầu tái tạo nguyên văn. Người dùng cũng có thể hiểu danh sách rỗng là hai bản giống hệt.
- **Đề xuất sửa cụ thể:** Định nghĩa riêng “giống nguyên văn” và “giống sau chuẩn hóa”. Giữ hành vi baseline để đối chứng, nhưng bổ sung edit script không mất dữ liệu cho engine mới; lưu cả khoảng trắng và vị trí chèn.

### F04. Kế hoạch chưa xử lý đầy đủ lỗi và giới hạn tài nguyên ở đầu vào

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.2; Mục 7.1; Mục 9.1, việc 3.
- **Vấn đề cụ thể:** Code hiện không có lớp xử lý lỗi PDF tại route/service, không đặt giới hạn nghiệp vụ cho số trang, kích thước hay thời gian xử lý. `min_length=1` vẫn nhận chuỗi chỉ có khoảng trắng. Filename có thể thiếu là vấn đề thật vì schema yêu cầu chuỗi, nhưng thêm `"old.pdf"` không xác nhận nội dung là PDF. Xem [comparisons.py](C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/api/routes/comparisons.py:14) và [comparison.py](C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/schemas/comparison.py:4).
- **Vì sao nguy hiểm:** File hỏng hoặc quá lớn có thể làm hỏng demo, chiếm tài nguyên và phá phép đo latency. Kiểm tra đuôi file không giải quyết lỗi parser.
- **Đề xuất sửa cụ thể:** Quy định file hợp lệ, chính sách PDF mã hóa, giới hạn byte/trang/thời gian OCR, mã lỗi và phản hồi khi trích xuất thất bại. Kiểm tra nội dung thực bằng parser; kiểm tra riêng văn bản chỉ có khoảng trắng.

**Các mô tả hiện trạng được xác nhận:** `requirements.txt` và `README.md` trống; `health.py` trống và chưa được gắn router; ba file test không có hàm `test_*`; PDF được nối bằng `"\n\n"`; extractor chỉ tạo hai cảnh báo đã nêu. Tuy nhiên, baseline **đã có `needs_review` cấp tài liệu** khi một trong hai bản có cảnh báo; không nên mô tả cơ chế này như hoàn toàn chưa tồn tại.

## 2. Kiến trúc và alignment

### F05. Phát biểu một–nhiều không được schema và loại thay đổi hỗ trợ

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 1.2; Mục 1.5; Mục 3.3; Mục 4.3, Bước 3; Mốc 3.
- **Vấn đề cụ thể:** `AlignedClauseDiff` chỉ chứa một `old_node` và một `new_node`; enum không có `SPLIT` hoặc `MERGED`. Một quan hệ nhị phân có thể mã hóa nhiều cạnh, nhưng chưa biểu diễn được **một sự kiện tách/gộp**, độ bao phủ và phần nội dung còn dư.
- **Vì sao nguy hiểm:** API, ground truth và metric sẽ sử dụng ba cách hiểu khác nhau. Một khoản có thể vừa bị tính là đã ghép vừa bị tính là xóa/thêm.
- **Đề xuất sửa cụ thể:** Cắt tách/gộp khỏi phiên bản bắt buộc. Nếu giữ, cần sự kiện riêng với `old_node_ids`, `new_node_ids`, loại quan hệ và quy tắc mỗi node được sử dụng bao nhiêu lần; sửa cả annotation và metric trước khi cài đặt.

### F06. Chưa có quy ước nội dung cây, dễ báo trùng và làm sai similarity

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 1.2; Mục 3.3; Mục 4.3; Mục 9.2, quyết định 3.
- **Vấn đề cụ thể:** Không rõ `content` của Điều chỉ chứa văn bản trực tiếp hay bao gồm toàn bộ Khoản/Điểm con. Chưa quy định ghép cấp nào trước, nội dung nào được chấm điểm và cấp nào sở hữu một thay đổi.
- **Vì sao nguy hiểm:** Nếu nội dung con nằm trong cha, một sửa đổi có thể bị báo ở Điều, Khoản và Điểm. Nếu cha chỉ chứa tiêu đề, alignment cấp Điều lại thiếu tín hiệu nội dung. Ghép toàn cục độc lập có thể làm cha–con mâu thuẫn.
- **Đề xuất sửa cụ thể:** Tách `own_text` và văn bản tổng hợp dùng cho truy hồi. Mỗi span chỉ có một nơi sở hữu trong báo cáo. Chọn trước một chiến lược: ghép Điều rồi Khoản trong cha đã ghép; tìm xuyên cha chỉ là bước phục hồi có điều kiện.

### F07. Ghép tối ưu rồi mới cắt ngưỡng có thể phá nghiệm hợp lệ tốt hơn

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 4.3, Bước 2.
- **Vấn đề cụ thể:** Xét ma trận minh họa, không phải số liệu thực nghiệm:

  ```text
             v1     v2
  u1        0.95   0.65
  u2        0.65   0.39
  ```

  Assignment đầy đủ chọn đường chéo vì tổng `1.34 > 1.30`. Sau khi loại cạnh dưới `0.40`, chỉ còn cặp `0.95`. Trong khi đó, hai cạnh chéo đều hợp lệ và có tổng `1.30`.
- **Vì sao nguy hiểm:** Bước lọc sau tối ưu không còn tối ưu cho bài toán ghép tùy chọn mà hệ thống thực sự cần. Thêm/xóa có thể bị tạo giả.
- **Đề xuất sửa cụ thể:** Đưa lựa chọn không ghép vào chính bài toán bằng dummy node và chi phí thêm/xóa được định nghĩa rõ; cấm cạnh không hợp lệ trước khi tối ưu. Có test cho ma trận vuông, chữ nhật, rỗng và trường hợp trên. SciPy hỗ trợ assignment chữ nhật, nhưng không tự cung cấp chính sách từ chối ghép của ứng dụng. [Tài liệu SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html).

### F08. Bước neo được nhấn mạnh nhưng chưa được thiết kế

- **Mức độ:** Quan trọng.
- **Vị trí:** H2; Mục 3.1; Mục 4.3.
- **Vấn đề cụ thể:** Pipeline có “Exact / Anchor Match — số hiệu + tiêu đề”, nhưng thuật toán chi tiết bắt đầu ngay bằng ma trận similarity. Không có điều kiện khóa neo, xử lý neo trùng hoặc mở khóa neo sai.
- **Vì sao nguy hiểm:** Khi chèn một Điều ở đầu, số hiệu cũ có thể trỏ sang nội dung khác. Neo cứng theo số hiệu sẽ gây lỗi dây chuyền; tiêu đề lặp cũng không đủ phân biệt.
- **Đề xuất sửa cụ thể:** Chỉ khóa neo có nội dung chuẩn hóa trùng và duy nhất, hoặc có nhiều bằng chứng nhất quán. Dùng số hiệu làm đặc trưng hỗ trợ. Lưu lý do ghép và kiểm tra xung đột trước khi loại node khỏi tập ứng viên.

### F09. Blocking có thể loại bỏ chính các cặp `MOVE` cần tìm

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.4; Mục 4.3; Mục 9.2, quyết định 3.
- **Vấn đề cụ thể:** “Blocking theo cấp độ” chưa nói có chặn theo cha, vị trí hoặc số hiệu không. Ghép Khoản chỉ trong Điều cũ sẽ không tìm được Khoản chuyển sang Điều khác; ghép mọi cấp chung lại dễ ghép Điều với Khoản có nội dung gần giống.
- **Vì sao nguy hiểm:** Recall bị chặn ngay từ bước tạo ứng viên, embedding hay Hungarian không thể phục hồi.
- **Đề xuất sửa cụ thể:** Công bố chính sách ứng viên: cùng loại node; ưu tiên trong cha đã ghép; node chưa ghép mới tìm toàn cục; cho phép từ chối khi nhập nhằng. Đo cả recall của tập ứng viên trước khi đo alignment cuối.

### F10. Điểm similarity chưa có miền giá trị và quy tắc kết hợp nhất quán

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.3; Mục 3.4; Mục 4.3, Bước 1.
- **Vấn đề cụ thể:** Cosine embedding không mặc nhiên thuộc `[0,1]`; BM25 không cùng thang với cosine; thay embedding bằng SVD/BM25 không giữ được ngữ nghĩa của ngưỡng `0.40/0.65`. Chưa nói xử lý tiêu đề thiếu, vector rỗng và cách kết hợp word/char TF-IDF.
- **Vì sao nguy hiểm:** Cùng ngưỡng nhưng mỗi chế độ tạo một hệ thống khác. Nếu tiêu đề thiếu và trả similarity bằng 0, ngay cả cặp giống hệt cũng không có tổng điểm 1.
- **Đề xuất sửa cụ thể:** Đặc tả miền từng đặc trưng, xử lý giá trị thiếu, chuẩn hóa và phân bổ lại trọng số. Chốt phạm vi fit TF-IDF. Mỗi chế độ có cấu hình/ngưỡng riêng được chọn trên validation; không gọi fallback là tương đương.

### F11. Similarity cao không đồng nghĩa ghép cặp đáng tin

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 1.2, bước 4; Mục 3.3; Mục 4.3.
- **Vấn đề cụ thể:** Quyết định `needs_review` chủ yếu dựa vào điểm tuyệt đối. Hai ứng viên có thể cùng đạt `0.95`; điểm cao không cho biết cặp nào đúng. Schema cũng chưa tách `similarity_score` và confidence.
- **Vì sao nguy hiểm:** Điều khoản mẫu lặp lại có thể bị ghép sai với điểm cao, sau đó hệ thống không cảnh báo người dùng.
- **Đề xuất sửa cụ thể:** Dùng thêm khoảng cách giữa ứng viên tốt nhất và thứ hai, kiểm tra cạnh tranh hai chiều, trùng nội dung và xung đột cha–con. Gọi đây là độ tin cậy theo heuristic nếu chưa hiệu chuẩn xác suất. Giữ các ứng viên thay thế cho ca cần rà soát.

### F12. LIS không xác định duy nhất lịch sử di chuyển

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 4.3, Bước 3; Mục 5.2; Mục 5.4.
- **Vấn đề cụ thể:** Với `A B C → B A C`, có thể giữ `A,C` và coi B di chuyển, hoặc giữ `B,C` và coi A di chuyển. Hai LIS cùng dài. Hai tài liệu cuối không cho biết người biên tập thực sự kéo A hay B.
- **Vì sao nguy hiểm:** Nhãn `MOVED` phụ thuộc tie-break. Ground truth ghi “hoán đổi hai điều khoản” có thể đánh dấu cả hai, trong khi phương pháp LIS chỉ đánh dấu một; Move F1 khi đó không đo cùng khái niệm.
- **Đề xuất sửa cụ thể:** Định nghĩa `MOVE` là quy ước biểu diễn thay đổi, không suy ra lịch sử chỉnh sửa. Quy định tie-break hoặc chấp nhận nhiều nghiệm tương đương. Phân biệt “đổi thứ tự tương đối”, “đổi cha” và “đổi số hiệu”.

### F13. Phát hiện tách/gộp bằng token containment dễ báo sai và bỏ sót

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 4.3, Bước 3.
- **Vấn đề cụ thể:** Phần mô tả chỉ cụ thể hóa một nút cũ với hai nút mới liên tiếp. Chưa có định nghĩa coverage hai chiều, kiểm tra thứ tự, xử lý từ lặp, gộp chiều ngược và giải quyết ứng viên dùng chung node. Nhánh này chỉ chạy sau một–một nên một nửa của phép tách có thể đã bị ghép mất.
- **Vì sao nguy hiểm:** Các điều khoản mẫu chứa nhiều từ chung có thể bị nhận nhầm là tách/gộp. Nội dung bị xóa thật có thể bị che khuất.
- **Đề xuất sửa cụ thể:** Nếu chưa cắt tính năng, giới hạn rõ chỉ tách 1→2 liên tiếp, kiểm tra coverage hai phía theo span/thứ tự và chỉ phát gợi ý cần xác nhận. Không dùng ngưỡng `0.75` như bằng chứng về quan hệ ngữ nghĩa.

### F14. `RENUMBERED` và `MOVED` nguyên văn vẫn có thể thay đổi nghĩa

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 1.2; Mục 4.3; Mục 4.5.
- **Vấn đề cụ thể:** Kế hoạch chưa xét dẫn chiếu như “theo Khoản 2 Điều 5”, hoặc nội dung phụ thuộc Điều cha. Giữ nguyên câu chữ nhưng chuyển cha có thể đổi phạm vi áp dụng; đánh lại số mà không cập nhật dẫn chiếu có thể làm dẫn chiếu trỏ sai.
- **Vì sao nguy hiểm:** Gán mặc định `LOW` cho đổi số hoặc coi nguyên văn là an toàn có thể bỏ sót lỗi đáng chú ý.
- **Đề xuất sửa cụ thể:** Giữ nguyên dẫn chiếu trong văn bản diff. Nếu chưa xây bộ phân giải dẫn chiếu, bật cờ khi đổi số/đổi cha liên quan đến dẫn chiếu nội bộ. Không cam kết đánh giá đầy đủ hệ quả pháp lý của di chuyển.

### F15. Hai embedding đề xuất có yêu cầu tiền xử lý khác nhau

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.4; Mục 4.3; Mốc 3; Mục 9.2.
- **Vấn đề cụ thể:** Model card MiniLM nêu `max_seq_length=128`, nên đưa nguyên Điều dài vào có thể bỏ phần cuối. Model `vietnamese-bi-encoder` yêu cầu đầu vào đã tách từ khi dùng Sentence Transformers; kế hoạch chưa bố trí bước này. [MiniLM](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), [Vietnamese bi-encoder](https://huggingface.co/bkai-foundation-models/vietnamese-bi-encoder).
- **Vì sao nguy hiểm:** Hai điều khoản giống phần đầu nhưng khác nghĩa vụ ở cuối có thể gần như giống nhau trong embedding. Kết quả kém do dùng sai model lại có thể bị kết luận là embedding không hữu ích.
- **Đề xuất sửa cụ thể:** Chọn một model cho nhánh thử nghiệm; khóa revision, tokenizer và tiền xử lý. Đo độ dài token, tỷ lệ cắt ngắn; thử chia đoạn và tổng hợp điểm. Không ghi “CPU tốc độ cao” trước khi đo trên máy mục tiêu.

### F16. H3 chưa phân biệt chi phí local diff và chi phí toàn pipeline

- **Mức độ:** Quan trọng.
- **Vị trí:** H3; RQ4; Mục 3.4; Mục 5.4.
- **Vấn đề cụ thể:** Chia nhỏ có thể giảm chi phí diff, nhưng còn extraction, embedding, ma trận cặp và assignment. Với các cặp có độ dài \(a_i,b_i\), cần xét cả \(\sum_i a_i b_i\), số ứng viên và phần nội dung bị xử lý lặp. `SequenceMatcher` có trường hợp xấu bậc hai. [Tài liệu Python](https://docs.python.org/3/library/difflib.html).
- **Vì sao nguy hiểm:** Local diff nhanh hơn không chứng minh hệ thống nhanh hơn. Khẳng định assignment `<5ms` chưa có cấu hình máy hay phép đo; \(K=20–150\) cũng chưa có căn cứ nếu ghép tới Khoản/Điểm.
- **Đề xuất sửa cụ thể:** Tách giả thuyết hiệu năng local diff khỏi end-to-end. Đo cold/warm, CPU/RAM, số token/node và dữ liệu lặp nhiều. Ghi đúng SciPy hiện dùng biến thể Jonker–Volgenant, dù vẫn giải bài toán assignment. [Tài liệu SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html).

## 3. Trích xuất PDF, OCR và phân đoạn

### F17. NFC không sửa được mọi lỗi bảng mã/font tiếng Việt

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.2; Mục 4.1.
- **Vấn đề cụ thể:** NFC xử lý các biểu diễn Unicode tương đương; không phải bộ chuyển TCVN3/VNI hay khôi phục ánh xạ glyph sai. Đếm ký tự ngoài tập Latin cũng không bắt được lỗi như số `0` thành chữ `O`.
- **Vì sao nguy hiểm:** Văn bản sai nhưng nhìn “hợp lệ” có thể đi thẳng vào alignment, tạo thay đổi giả hoặc che mất thay đổi số.
- **Đề xuất sửa cụ thể:** Tách normalization, chuyển bảng mã có điều kiện và đánh giá chất lượng extraction thành các bước riêng. Không tự chuyển bảng mã khi chưa nhận diện chắc chắn; giữ raw text và ghi lý do chọn OCR. [Tài liệu Unicode normalization của Python](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize).

### F18. Điều kiện kích hoạt OCR và ngưỡng confidence chưa dùng được như đặc tả

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 4.1; Mục 3.3; Mốc 2.
- **Vấn đề cụ thể:** `<20` ký tự/trang không phải “mật độ”; trang chữ ký ít chữ không nhất thiết lỗi. Trang có text layer sai nhưng nhiều ký tự có thể không kích hoạt OCR. Tesseract TSV trả confidence theo thang thể hiện quanh 0–100 và có giá trị `-1` ở các cấp không phải từ; không thể áp trực tiếp ngưỡng `0.85`. [Tài liệu Tesseract TSV](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html#tsv-output).
- **Vì sao nguy hiểm:** Hệ thống có thể OCR sai trang, bỏ sót trang hỏng hoặc coi trang có một chữ số quan trọng sai là đáng tin vì điểm trung bình cao.
- **Đề xuất sửa cụ thể:** Định nghĩa tín hiệu riêng cho trang ảnh, lỗi text layer và trang ít chữ. Chuẩn hóa confidence theo engine, lọc giá trị không hợp lệ, kiểm tra riêng vùng tiền/ngày/tỷ lệ. Đo CER/WER và độ đúng chữ số trên tập OCR, cùng hiệu quả thực tế của cờ rà soát.

### F19. VietOCR chưa phải phương án thay thế tương đương cho OCR cả trang

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.1; Mục 3.2; Mục 3.4; Mục 9.2.
- **Vấn đề cụ thể:** Nhánh VietOCR còn cần giải quyết phát hiện vùng chữ, cắt dòng, thứ tự đọc và gắn tọa độ. `Predictor` nhận ảnh đã xử lý kích thước để nhận dạng; mã này không cung cấp toàn bộ pipeline phân tích trang. [Mã Predictor của VietOCR](https://raw.githubusercontent.com/pbcquoc/vietocr/master/vietocr/tool/predictor.py).
- **Vì sao nguy hiểm:** Ước lượng chỉ tính thời gian tích hợp model nhận dạng, bỏ qua các thành phần tạo đầu vào và cây cấu trúc.
- **Đề xuất sửa cụ thể:** Chọn Tesseract làm nhánh OCR duy nhất nếu bắt buộc giữ OCR. Chốt DPI, xoay/deskew, page segmentation mode, ngôn ngữ và chuyển tọa độ pixel sang tọa độ PDF. Đưa VietOCR ra phần mở rộng.

### F20. Bộ lọc header/footer có thể xóa nội dung hợp đồng thật

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 4.1, bước 2.
- **Vấn đề cụ thể:** Nằm trong vùng 8% mép trang và lặp trên 60% trang không chứng minh là nhiễu. Chuẩn hóa mọi chữ số thành `<NUM>` có thể làm các dòng khác nhau trở thành cùng mẫu.
- **Vì sao nguy hiểm:** Một dòng nghĩa vụ hoặc giá trị lặp bị loại bỏ sẽ không còn được diff. Đây là mất dữ liệu trước khi alignment, không thể khắc phục bằng engine phía sau.
- **Đề xuất sửa cụ thể:** Chỉ đánh dấu vùng nghi nhiễu trước; lưu nguyên nội dung và nguồn. Kết hợp vị trí, kiểu chữ và mẫu số trang; cho phép tắt lọc. Đo riêng tỷ lệ xóa nhầm nội dung và kiểm thử hai phiên bản có header khác nhau.

### F21. Regex mẫu đã bỏ sót cách đánh số phổ biến ngay trong phạm vi

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 4.2; H1.
- **Vấn đề cụ thể:** Regex Khoản yêu cầu dấu `.` hoặc `)` sau nhóm số, nên:
  
  ```text
  "1.1 Nội dung"   → không khớp
  "1.1. Nội dung"  → khớp
  ```

  Quy tắc \(k=k_{prev}+1\) chưa định nghĩa cho nhãn phân cấp `1.1`, `1.2`; hợp đồng cũng có thể bỏ số, dùng Điều 5a, tiêu đề xuống dòng hoặc nội dung bắt đầu bằng một số.
- **Vì sao nguy hiểm:** F1 cao trên mẫu chuẩn không chứng minh parser xử lý được phạm vi đã hứa. Giả định hợp đồng tuân thể thức rất chặt chưa được dữ liệu của đồ án chứng minh.
- **Đề xuất sửa cụ thể:** Thu hẹp profile cú pháp hỗ trợ; parse nhãn thành tuple số/cấp. Thêm fixture cho từng biến thể và quy tắc phục hồi khi sai thứ tự. Bảo toàn đoạn không phân loại được dưới dạng `PARAGRAPH`, không bỏ âm thầm.

### F22. Schema không đủ thông tin truy ngược highlight về tài liệu gốc

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 1.2; Mục 3.3; Mục 4.1; Mục 4.4; Mục 8.2.
- **Vấn đề cụ thể:** Một `bbox` chỉ gắn với một trang không biểu diễn được điều khoản nhiều dòng/nhiều trang. Không có ánh xạ từ text đã NFC, bỏ header/footer, bỏ bảng sang raw text hoặc vùng PDF.
- **Vì sao nguy hiểm:** Hệ thống có thể phát hiện đúng thay đổi nhưng highlight sai vị trí. Demo “đi tới đúng trang/điều khoản” và việc kiểm chứng extraction sẽ thiếu căn cứ.
- **Đề xuất sửa cụ thể:** Lưu source span theo dòng/token gồm trang, bbox, nguồn PDF/OCR và raw offset. Mỗi node tham chiếu danh sách span; transformation phải giữ ánh xạ. Nếu không đủ thời gian, giới hạn highlight trong báo cáo văn bản và chỉ cung cấp số trang.

### F23. Thiết kế bảng chưa giải quyết cả extraction lẫn alignment hàng/cột

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.2–3.3; Mục 4.2; Mốc 4.
- **Vấn đề cụ thể:** Schema không có cells, row/column span hay khóa hàng. “Gắn vào điều khoản ngay phía trên” sai với bảng tiếp diễn qua trang. Cùng số cột không bảo đảm cùng ngữ nghĩa cột; hàng có thể không có khóa duy nhất.
- **Vì sao nguy hiểm:** Lệch một cột có thể tạo hàng loạt thay đổi tiền giả. Loại text trong bbox bảng trước khi xác nhận extraction thành công còn có thể làm mất nội dung.
- **Đề xuất sửa cụ thể:** Cắt cell diff khỏi lõi; bảo toàn bảng dưới dạng vùng văn bản có cờ. Nếu giữ, chỉ hỗ trợ bảng một trang, có đường kẻ, header rõ và khóa hàng duy nhất; xác thực nội dung trước khi loại khỏi luồng thường. `pdfplumber` có công cụ lấy cells/bbox nhưng không tự giải quyết các ràng buộc nghiệp vụ này. [Tài liệu pdfplumber](https://github.com/jsvine/pdfplumber#extracting-tables).

## 4. Diff thực thể và phân loại mức độ quan trọng

### F24. Trích thực thể chỉ trên fragment thay đổi sẽ mất đơn vị và ngữ cảnh

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 4.4–4.5.
- **Vấn đề cụ thể:** Chạy code hiện tại:

  ```text
  "100.000.000 VNĐ" → "200.000.000 VNĐ"
  fragment thay đổi: "100.000.000" → "200.000.000"
  ```

  Regex đòi số kèm đơn vị sẽ không thấy `VNĐ`. Với `"15 ngày làm việc" → "45 ngày"`, code tạo một thay đổi số và một thay đổi xóa `"làm việc"` riêng biệt.
- **Vì sao nguy hiểm:** Thay đổi thực thể trọng yếu bị hạ xuống `TEXT_EDIT`, dù word diff đúng. Coalescing theo một từ ngắn không bảo đảm khôi phục đầy đủ ngữ cảnh.
- **Đề xuất sửa cụ thể:** Trích thực thể trên toàn câu hoặc toàn điều khoản ở cả hai bản trước; giữ span và thuộc tính. Sau đó giao các span thực thể với vùng diff và ghép thực thể theo ngữ cảnh. Coalescing chỉ phục vụ trình bày.

### F25. Chuẩn hóa tiền và thời hạn đang đánh đồng giá trị số với ý nghĩa

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 4.5, bước 1–3.
- **Vấn đề cụ thể:** `"100 USD" → "100 VND"` giữ cùng số nhưng thay tiền tệ; `"30 ngày" → "30 ngày làm việc"` giữ số nhưng đổi loại thời hạn. Dùng số thực cho tiền cũng không phải lựa chọn thích hợp cho so sánh chính xác. Chưa có thiết kế xử lý nhiều số tiền trong một câu, số bằng chữ mâu thuẫn với số bằng chữ số.
- **Vì sao nguy hiểm:** Chuẩn hóa có thể xóa chính khác biệt cần phát hiện.
- **Đề xuất sửa cụ thể:** Biểu diễn tiền bằng `Decimal` và currency; thời hạn bằng giá trị, đơn vị, loại ngày và mốc tính; phần trăm có kỳ tính nếu nhận diện được. Khi nhập nhằng, giữ nguyên giá trị và bật cờ. Cắt parser tiền bằng chữ khỏi phiên bản bắt buộc.

### F26. Từ điển tình thái không đủ để phân loại thay đổi nghĩa vụ

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 1.3, RQ3; Mục 3.3; Mục 4.5.
- **Vấn đề cụ thể:** Nhóm từ khóa chồng lấn: “không phải” chứa cả “không” và “phải”; “không được” là cấm đoán. Các thay đổi “và” thành “hoặc”, thêm ngoại lệ, thay phạm vi chủ thể có thể không chạm từ khóa nào. Dấu câu cũng không mặc nhiên chỉ là định dạng. `PARTY_CHANGE` được hứa nhưng chưa có quy tắc nhận diện/ghép bên.
- **Vì sao nguy hiểm:** Hệ thống vừa bỏ sót thay đổi quan trọng, vừa tạo cảnh báo CRITICAL sai. Gán mặc định MEDIUM cho câu không chứa từ khóa tạo cảm giác an toàn không có căn cứ.
- **Đề xuất sửa cụ thể:** Đổi mục tiêu thành phát hiện **tín hiệu cần rà soát**. Ưu tiên cụm dài, giữ ngữ cảnh câu/chủ thể, thêm bộ phản ví dụ. Chưa phân tích được thì không suy ra mức độ thấp. Giới hạn bên tham gia ở các nhãn rõ như Bên A/B.

### F27. Mức độ quan trọng và demo tự mâu thuẫn

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 3.3; Mục 4.5; Mục 8.2.
- **Vấn đề cụ thể:** Quy tắc gán `DATE_DURATION_CHANGE` là HIGH, nhưng demo yêu cầu cả thay đổi thời hạn thuộc ba thay đổi CRITICAL. Schema ghi sửa nghĩa vụ là HIGH trong khi thuật toán có trường hợp CRITICAL; chưa có bảng quyết định thống nhất hoặc thứ tự ưu tiên.
- **Vì sao nguy hiểm:** Ground truth, code và demo có thể được chỉnh riêng để “đúng” mà không còn đánh giá cùng một hệ thống.
- **Đề xuất sửa cụ thể:** Viết một bảng quyết định duy nhất cho các tổ hợp tín hiệu và dùng chung trong code, annotation, test, báo cáo. Đổi cách gọi thành mức ưu tiên rà soát. Demo phải lấy kết quả engine, không viết sẵn mức độ mong muốn.

## 5. Dữ liệu, thực nghiệm và tái lập

### F28. Khẳng định ground truth tổng hợp “chính xác 100%” không đứng vững

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 5.2.
- **Vấn đề cụ thể:** Nhật ký toán tử chỉ biết thao tác dự định. Nó không bảo đảm cây gốc đúng, thao tác không chồng lấn, PDF render đúng, extraction giữ nguyên nội dung hay nhãn MOVE khớp quy ước LIS. Nếu dùng parser của hệ thống tạo cây chuẩn, bộ đo còn có nguy cơ tự xác nhận.
- **Vì sao nguy hiểm:** Kết quả cao có thể chỉ chứng minh hệ thống phù hợp với generator dùng chung giả định.
- **Đề xuất sửa cụ thể:** Đổi thành “nhãn thao tác sinh tự động, được kiểm chứng”. Tạo ID ổn định độc lập parser, kiểm tra hậu điều kiện từng phép biến đổi và kiểm toán thủ công mẫu đầu ra sau render. Tách ground truth nội dung khỏi ground truth extraction.

### F29. Chưa chia train/validation/test theo họ hợp đồng gốc

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** Mục 4.3; Mục 5.1–5.5; Mục 7.3.
- **Vấn đề cụ thể:** Có nhắc validation để chỉnh trọng số/ngưỡng nhưng không có quy trình chia tập. Nhiều cặp từ cùng một mẫu có thể lọt sang cả validation và test.
- **Vì sao nguy hiểm:** Hệ thống được chấm trên tiêu đề, câu chữ và bố cục gần như đã thấy. Một trăm cặp không có nghĩa là một trăm quan sát độc lập.
- **Đề xuất sửa cụ thể:** Chia theo hợp đồng gốc/họ mẫu trước khi sinh biến thể; mọi hậu duệ nằm cùng tập. Khóa curated test, tránh gần trùng nguồn. Công bố số họ mẫu, số cặp và phân bố từng loại thay đổi.

### F30. Tập “bán thực tế” vẫn do người làm đồ án tạo và chưa có lịch sản xuất

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 5.2–5.3; Mục 6.
- **Vấn đề cụ thể:** Mô phỏng đàm phán do sinh viên thực hiện không phải revision thực tế độc lập. Lộ trình không dành mốc cụ thể để tạo 15–20 cặp, quét/chụp, gán nhãn, kiểm tra chéo và phân xử bất đồng.
- **Vì sao nguy hiểm:** Tập dữ liệu khó nhất có thể được làm sau khi thuật toán hoàn thiện, dẫn đến thiên lệch theo những gì hệ thống đã xử lý được.
- **Đề xuất sửa cụ thể:** Gọi đúng là tập chỉnh sửa thủ công mô phỏng. Chuẩn bị và khóa một phần sớm, dùng checklist thay đổi độc lập với engine. Xác nhận cộng tác viên và thời gian gán nhãn từ đầu; báo cáo giới hạn nếu không có dữ liệu revision thật.

### F31. Cohen’s kappa chưa phù hợp trực tiếp với mọi loại nhãn dự kiến

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 5.3.
- **Vấn đề cụ thể:** Ranh giới là span; alignment là cạnh giữa hai tập node; semantic types là đa nhãn. Không thể gộp tất cả vào một hệ số kappa nếu chưa có cùng tập đơn vị cố định. Hai người có thể phân đoạn khác nhau nên chưa có các đơn vị tương ứng để tính.
- **Vì sao nguy hiểm:** Một con số \(\kappa\ge0.80\) có thể che mất bất đồng về ranh giới hoặc alignment; cũng không chứng minh severity đúng theo pháp lý.
- **Đề xuất sửa cụ thể:** Đo agreement riêng cho span, cạnh alignment và nhãn trên đơn vị cố định. Nêu quy tắc dung sai, cách ghép đơn vị, chọn mẫu và phân xử. Tính agreement trước phân xử; không sửa nhãn chỉ để vượt ngưỡng.

### F32. Độ đo chưa có định nghĩa vận hành cho pipeline thực tế

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** H1–H2; Mục 5.4.
- **Vấn đề cụ thể:** Chưa định nghĩa khi nào hai node dự đoán/chuẩn được coi là cùng node; ranh giới sau normalization/OCR được so thế nào; split/merge chấm theo cạnh hay sự kiện. Chưa tách alignment với cây chuẩn và alignment sau parser.
- **Vì sao nguy hiểm:** Không phân biệt được lỗi extraction, segmentation hay alignment. F1 cao cấp Điều có thể che thất bại cấp Khoản/Điểm hoặc OCR.
- **Đề xuất sửa cụ thể:** Đặc tả đơn vị, matching criterion, mẫu số và cách tính cho tập rỗng. Báo cáo theo cấp node và nhóm tài liệu. Chạy hai chế độ: đầu vào cấu trúc chuẩn để kiểm tra engine, và end-to-end để đo hệ thống.

### F33. Ít khối diff hơn không chứng minh ít cảnh báo sai hơn

- **Mức độ:** Nghiêm trọng.
- **Vị trí:** H2; RQ3–RQ4; Mục 5.5.
- **Vấn đề cụ thể:** Chỉ cần gom mọi chỉnh sửa thành một khối là số khối giảm; bỏ sót thay đổi cũng làm số khối giảm. Baseline không có nhãn cấu trúc/severity nên không thể so F1 của các nhãn này nếu thiếu quy tắc chuyển đổi.
- **Vì sao nguy hiểm:** Thí nghiệm có thể “chứng minh” cải thiện bằng thay cách trình bày thay vì tăng chất lượng phát hiện.
- **Đề xuất sửa cụ thể:** Đánh giá theo sự kiện thay đổi chuẩn và span được phát hiện, kèm precision/recall. Dùng cùng extraction để cô lập đóng góp engine, rồi mới so end-to-end. Xác định mẫu số của “giảm 50% diff giả”, kể cả trường hợp baseline không có false positive.

### F34. RQ3 và các ablation chưa đo đúng đóng góp của nhận diện thực thể

- **Mức độ:** Quan trọng.
- **Vị trí:** RQ3; Mục 5.4–5.5.
- **Vấn đề cụ thể:** Ba ablation hiện tắt layout, đổi matcher và tắt embedding; không có biến thể tắt tầng thực thể. Chỉ Critical Recall cũng chưa đủ: gán mọi thay đổi là CRITICAL sẽ đạt recall tối đa.
- **Vì sao nguy hiểm:** Không có thí nghiệm trực tiếp trả lời việc thêm tầng thực thể có giảm cảnh báo nhiễu hay không.
- **Đề xuất sửa cụ thể:** Thêm đối chứng “diff giống nhau, không có tầng thực thể”, đo precision/recall/F1 của cảnh báo trọng yếu và số cảnh báo sai. Tách Greedy với DP thành hai đối chứng vì chúng kiểm tra hai yếu tố khác nhau. Không mô tả mọi dạng DP đều bất khả thi cho MOVE; giới hạn nhận định ở DP căn chỉnh đơn điệu đang xét.

### F35. Các property test đang áp yêu cầu chưa được thuật toán bảo đảm

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 7.1.
- **Vấn đề cụ thể:** `similarity_score==1.0` với mọi node giống nhau không suy ra từ công thức khi thiếu title. Tính nghịch đảo của alignment cần quy tắc tie-break và từ chối ghép nhất quán; không tự có từ pipeline heuristic. Reconstruction của baseline đã có phản chứng ở F03.
- **Vì sao nguy hiểm:** Sinh viên có thể sửa output cho vừa test mà không giải quyết đúng bài toán, hoặc hạ yêu cầu test khi gặp thất bại.
- **Đề xuất sửa cụ thể:** Phân biệt invariant của biểu diễn với mục tiêu chất lượng. Ưu tiên: không mất text, không dùng node hai lần trong ghép một–một, không tạo chu trình cây, mọi span hợp lệ, kết quả lặp lại được, thêm/xóa đảo chiều trên các trường hợp không nhập nhằng.

### F36. Seed và pin package chưa đủ tái lập thí nghiệm PDF/OCR/embedding

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 7.3; Mục 6.
- **Vấn đề cụ thể:** Thiếu Python/OS, phụ thuộc bắc cầu, Tesseract binary và `vie.traineddata`, model revision, font, bộ chuyển DOCX→PDF, DPI, cấu hình thread và phiên bản dataset. Lazy loading làm lần chạy đầu khác các lần sau.
- **Vì sao nguy hiểm:** Cùng seed vẫn có thể sinh PDF khác, text khác hoặc latency khác. “Một lệnh” không bảo đảm máy khác chạy được.
- **Đề xuất sửa cụ thể:** Có manifest và hash đầu vào/dataset/model, lock môi trường, hướng dẫn cài binary và quy định warm-up. Lưu cấu hình đã giải quyết đầy đủ, phiên bản code, raw prediction và log theo pha. Dùng artifact PDF cố định cho benchmark chính.

### F37. Ma trận nghiên cứu đang trình bày kỳ vọng như năng lực đã được chứng minh

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 1.5; Mục 2.3; Mục 3.4.
- **Vấn đề cụ thể:** Hàng hệ thống đề xuất đánh “Có” toàn bộ khi chưa triển khai; hàng LLM cũng đánh “Có” quá tuyệt đối. Embedding không đồng nghĩa “kiểm soát hoàn toàn”. Nhận định Git diff không phát hiện chuyển chỗ quá rộng: Git có tùy chọn `--color-moved`, dù khác bài toán move điều khoản. [Tài liệu Git](https://git-scm.com/docs/git-diff#Documentation/git-diff.txt---color-movedltmodegt).
- **Vì sao nguy hiểm:** Khoảng trống nghiên cứu được dựng từ so sánh không đồng mức, dễ bị phản biện là thiên lệch. Tích hợp các thành phần đã biết cũng chưa tự tạo thành phương pháp mới.
- **Đề xuất sửa cụ thể:** Dùng “mục tiêu”, “có bằng chứng”, “chưa kiểm chứng”; ghi phiên bản và điều kiện. Định vị đóng góp ở benchmark tiếng Việt, phương pháp ghép có thể đánh giá và phân tích lỗi. Chưa có căn cứ kết luận tính mới học thuật trước khảo sát đầy đủ.

### F38. Quyền sử dụng và khả năng công bố dataset chưa được xác nhận theo từng nguồn

- **Mức độ:** Quan trọng.
- **Vị trí:** Mục 5.1; Mốc 1; Mục 7.3.
- **Vấn đề cụ thể:** Kế hoạch gọi ba nhóm nguồn là hợp pháp nhưng chưa có danh mục cụ thể, quyền tái phân phối và điều kiện sử dụng từng tài liệu. Ẩn danh không tự xác nhận quyền công bố. Các mẫu “giả lập” cũng chưa có cơ chế bảo đảm không trùng thông tin thật.
- **Vì sao nguy hiểm:** Dataset có thể không được đưa vào repo, làm người khác không tái lập được thí nghiệm.
- **Đề xuất sửa cụ thể:** Lập manifest nguồn, ngày lấy, giấy phép/điều kiện và quyết định có được phân phối hay không. Dùng placeholder rõ ràng cho định danh. Nếu quyền phân phối chưa rõ, chỉ công bố mã tạo dữ liệu từ nguồn được phép. **Tôi chưa kiểm chứng quyền của từng nguồn vì kế hoạch chưa cung cấp danh sách tài liệu cụ thể.**

## 6. Phản biện từng mốc triển khai

Tổng thời gian theo giả định là **320–400 giờ**. Đây phải bao gồm khảo sát, dữ liệu, gán nhãn, lập trình, thực nghiệm, viết báo cáo và bảo vệ. Lịch hiện tại chưa thể hiện dự phòng cho lỗi dây chuyền giữa các pha.

| Phát hiện / Mức độ / Vị trí | Vấn đề cụ thể | Vì sao nguy hiểm | Đề xuất sửa cụ thể |
|---|---|---|---|
| **M01 — Quan trọng — Tuần 1–2, Mục 6 và 9.1** | Trong 40–50 giờ phải dựng môi trường, CI, test coverage 90%, thu thập/ẩn danh 30 mẫu và viết hai chương; danh sách tuần 1 còn thêm nguyên mẫu parser và aligner. | Công việc mở rộng vượt xa “khóa baseline”; chưa có annotation protocol nhưng đã thu thập số lượng lớn. | Hai tuần đầu chốt bài toán, schema, metric, baseline và một tập mẫu nhỏ có quyền sử dụng rõ. Parser/aligner chỉ làm spike để phát hiện rủi ro. Không coi coverage 90% là bằng chứng đủ về chất lượng. |
| **M02 — Nghiêm trọng — Tuần 3–5** | 60–75 giờ cho extraction hình học, font, bảng, layout cleaning, cây nhiều cấp, OCR và API, kèm F1 0.90. | Đây là nhiều bài toán độc lập; OCR và bố cục lỗi làm thay đổi toàn bộ giao diện dữ liệu phía sau. DoD chưa nói 20 hợp đồng là dev hay test. | Chỉ cam kết PDF số một cột, Điều/Khoản, bảo toàn đoạn chưa hiểu. Bảng/OCR chỉ gắn cờ. Đánh giá trên tập đã tách trước; đo thất bại thay vì buộc đạt ngưỡng bằng thu hẹp dữ liệu âm thầm. |
| **M03 — Nghiêm trọng — Tuần 6–8** | 60–75 giờ cho lexical+dense embedding, anchor, assignment, LIS, split/merge và generator 100 cặp. | Đây là mốc phụ thuộc parser và nhãn; generator xuất hiện quá muộn để dẫn dắt thiết kế. Ngưỡng F1 dễ thành mục tiêu tối ưu trên chính dữ liệu phát triển. | Làm lexical alignment có từ chối ghép trước; kiểm chứng assignment và MOVE convention. Generator bắt đầu từ tuần 1–2. Embedding là thử nghiệm tùy chọn; bỏ split/merge. |
| **M04 — Nghiêm trọng — Tuần 9–10** | 40–50 giờ cho tokenizer, coalescing, table diff, tiền bằng chữ, ngày, tỷ lệ, bên, nghĩa vụ, severity và tích hợp schema/service. | Tập trung quá nhiều lỗi ngữ nghĩa vào mốc ngắn nhất; chỉ tiêu “đúng 90%” chưa xác định precision hay recall. | Chỉ giữ tiền bằng chữ số, tỷ lệ và một tập ngày/thời hạn rõ; trích trên toàn clause. Không cell diff, không tiền bằng chữ, không nhận diện bên tổng quát. Chốt định nghĩa độ đo trước khi làm. |
| **M05 — Quan trọng — Tuần 11–13** | 60–75 giờ cho exporter, UI và toàn bộ thực nghiệm, trong khi dữ liệu curated/gán nhãn chưa được đặt lịch trước đó. | Khi thực nghiệm lộ lỗi parser hoặc nhãn, không còn thời gian điều tra. Có nguy cơ ưu tiên demo đẹp hơn kết quả đáng tin. | Chạy harness thực nghiệm từ sớm, khóa phương pháp cuối tuần 10. Chỉ xuất HTML tĩnh; escape nội dung hợp đồng khi render. Tuần 11–13 dành chính cho đánh giá và phân tích lỗi. |
| **M06 — Quan trọng — Tuần 14–16** | Dồn hoàn chỉnh ba chương, hồi quy, README, slide, video và duyệt giảng viên vào cuối; chưa có thời gian phản hồi/sửa báo cáo. | Bất kỳ kết quả không đạt nào cũng đẩy sang thời gian bảo vệ. “Có video dự phòng” không giải quyết lỗi nghiên cứu. | Viết chương phương pháp và dữ liệu song song từ đầu. Đặt lịch duyệt, freeze tính năng và một vòng sửa báo cáo rõ ràng. Khi chậm tiến độ, cắt tính năng tùy chọn; không giảm kiểm chứng dữ liệu hoặc sửa metric để đạt DoD. |

## Top 5 rủi ro lớn nhất

1. **Alignment sai nhưng không cảnh báo:** hậu kiểm ngưỡng, neo chưa đặc tả, clause lặp và confidence chưa được thiết kế có thể tạo kết quả ghép sai với điểm cao.
2. **Mất hoặc sai nội dung trước khi diff:** layout cleaner xóa nhầm, text layer PDF sai, OCR sai chữ số và thiếu provenance khiến engine không thể phục hồi.
3. **Thực nghiệm tự xác nhận:** dữ liệu cùng họ mẫu lọt nhiều tập, generator chia sẻ giả định với parser và ground truth được coi đúng tuyệt đối.
4. **Cảnh báo mức thấp tạo cảm giác an toàn sai:** trích thực thể trên fragment, mất currency/đơn vị, từ điển nghĩa vụ thiếu phạm vi phủ định và dẫn chiếu chưa xử lý.
5. **Không đủ ngân sách thời gian:** OCR, bảng, cây nhiều cấp, split/merge, embedding, severity, UI và dataset đều nằm trong phần bắt buộc, không có nhánh cắt rõ ràng.

## Những gì nên CẮT khỏi phạm vi

- **OCR khỏi chỉ tiêu chất lượng bắt buộc:** nhận diện trang cần OCR và yêu cầu rà soát; chỉ tích hợp Tesseract nếu phần lõi hoàn thành sớm.
- **VietOCR và nhiều lựa chọn OCR song song.**
- **Split/merge tự động và alignment toàn cục tới cấp Điểm.**
- **Table cell diff:** giữ nguyên nội dung bảng và gắn cờ; không cam kết xử lý bảng nhiều trang.
- **Tiền bằng chữ, nhận diện chủ thể tổng quát và suy luận nghĩa vụ pháp lý.**
- **Song ngữ, CUAD và language profile tiếng Anh** trong phần thực nghiệm bắt buộc.
- **Web UI tương tác và xuất PDF:** một báo cáo HTML tĩnh cùng JSON là đủ cho demo.
- **Embedding như thành phần bắt buộc:** chỉ thêm sau khi lexical baseline được đánh giá; kết quả không cải thiện vẫn là kết quả nghiên cứu hợp lệ.
- **Tuyên bố dịch vụ hoàn chỉnh phục vụ kiểm toán doanh nghiệp** và “kiểm soát hoàn toàn”.

Phần lõi nên giữ: **text/PDF số một cột → Điều/Khoản → ghép một–một có lựa chọn không ghép → phát hiện đổi thứ tự theo quy ước rõ → local diff → tín hiệu tiền/ngày/tỷ lệ → HTML có nguồn trang và cờ rà soát**.

## Kết luận về khả thi trong 16 tuần

**Giữ nguyên kế hoạch: không khả thi ở mức cam kết có kiểm chứng cho một sinh viên làm 20–25 giờ/tuần.** Có thể làm được một bản demo chứa nhiều tính năng, nhưng chưa có cơ sở tin rằng tất cả sẽ được đánh giá và tái lập đúng như mô tả.

**Sau khi cắt phạm vi như trên: có thể khả thi**, với điều kiện khóa schema, dữ liệu chia tập và metric từ hai tuần đầu; có pipeline lõi chạy end-to-end trước cuối tuần 8; khóa tính năng khoảng tuần 10 để dành thời gian thực nghiệm và báo cáo. Chưa có đủ bằng chứng để cam kết trước các mức F1 0.90/0.92, giảm nhiễu 50% hay tốc độ `<5ms`; các con số này phải là đối tượng được kiểm nghiệm.