# BÁO CÁO PHẢN BIỆN KẾ HOẠCH ĐỒ ÁN TỐT NGHIỆP (GÓC NHÌN HỘI ĐỒNG CHẤM)

**Đề tài được phản biện:** Hệ thống so sánh phiên bản hợp đồng theo cấu trúc điều khoản (*Structure-Aware Contract Version Comparison System*)  
**Tài liệu được rà soát:** [docs/ke-hoach-trien-khai-do-an.md](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md) đối chiếu trực tiếp với mã nguồn thực tế trong `app/` và `tests/`.  
**Vai trò người phản biện:** Thành viên Hội đồng chấm Đồ án Tốt nghiệp (chuyên ngành Khoa học Máy tính / Xử lý Ngôn ngữ Tự nhiên & Kỹ thuật Phần mềm).

---

## Tóm tắt Đánh giá Tổng quan của Ủy viên Phản biện

Bản kế hoạch được viết rất bài bản về mặt hình thức, nắm bắt đúng nỗi đau thực tế của bài toán rà soát hợp đồng và khảo sát đúng hiện trạng mã nguồn cơ sở (`weakfish` hiện chỉ có **~185 dòng code Python** trải trên 10 file trong `app/`, trong khi [app/api/routes/health.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/api/routes/health.py), [requirements.txt](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/requirements.txt), [README.md](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/README.md), [tests/test_comparison_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/tests/test_comparison_service.py), [tests/test_comparison_api.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/tests/test_comparison_api.py) đều đang trống rỗng 0 byte, và [tests/test_text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/tests/test_text_diff.py#L1-L12) chưa có bất kỳ hàm `test_*` nào).

Tuy nhiên, dưới góc nhìn khắt khe của Hội đồng chấm khóa luận, bản kế hoạch đang mắc **4 vấn đề cốt tử**:
1. **Lỗ hổng phương pháp luận (Vòng lặp tự chứng minh - Circularity/Tautology):** Dùng bộ quy tắc phân đoạn và bộ toán tử thay thế thực thể/từ khóa để tự sinh dữ liệu kiểm thử (Synthetic Benchmark), rồi lại dùng chính bộ quy tắc/từ điển tương đương để chấm điểm hệ thống trên tập dữ liệu đó.
2. **Đứt gãy giữa Phát biểu Lý thuyết và Thuật toán Thực tế:** Phát biểu bài toán là so sánh hai **cây cấu trúc có thứ tự** $T_{old}, T_{new}$ và viện dẫn lý thuyết Tree Edit Distance, nhưng công thức ở Mục 4.3 lại làm phẳng thành danh sách rồi giải bài toán phân công lưỡng phân (Hungarian) mà không có ràng buộc bảo toàn cấu trúc phân cấp cha-con.
3. **Giả thuyết và Bất biến Kiểm thử bị hổng về mặt toán học:** Giả thuyết H3 đánh tráo thời gian chạy của riêng hàm `SequenceMatcher` với độ trễ toàn cục của cả pipeline (RQ4); 2/3 bất biến kiểm thử (`Reconstruction` và `Symmetry`) ở Mục 7.1 sẽ lập tức thất bại nếu đối chiếu với cách cài đặt [app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py#L4-L54) và thuật toán LIS ở Mục 4.3.
4. **Phạm vi quá tải nghiêm trọng (Scope Creep):** Ôm đồm cùng lúc 7 bài toán lớn (PDF Layout + OCR tiếng Việt + Phân tích cú pháp 6 cấp + Semantic/Hungarian Alignment + Table Diff + Legal NER/chuyển đổi tiền chữ sang số + Web UI/Redline Exporter + Đa ngôn ngữ Việt-Anh) cho **1 sinh viên trong 16 tuần** xuất phát từ con số 0 về dữ liệu.

---

## PHẦN 1: CHI TIẾT CÁC PHÁT HIỆN PHẢN BIỆN

### Nhóm A: Đóng góp Khoa học & Tính Mới (Scientific Contribution & Defensibility)

#### Phát hiện 1: Mâu thuẫn giữa tuyên bố "Đối sánh theo cấu trúc cây phân cấp (Tree Diff)" và thuật toán thực tế là "Ghép cặp lưỡng phân trên tập phẳng (Flat Bipartite Matching)"
* **Mức độ:** **Nghiêm trọng**
* **Mục trong kế hoạch:** Mục 1.2 ([ke-hoach-trien-khai-do-an.md](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L24-L26)), Mục 1.5 ([dòng 45](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L45)), Mục 2.1 ([dòng 77](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L77)), Mục 4.3 ([dòng 320-337](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L320-L337)) và Mục 9.2 ([dòng 610](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L610)).
* **Vấn đề:**
  * Ở Mục 1.2 và 1.5, đề tài phát biểu đầu vào của pha Alignment là hai cây có thứ tự $T_{old} = (V_{old}, E_{old})$ và $T_{new} = (V_{new}, E_{new})$, tuyên bố đóng góp khoa học là *"kiến trúc pipeline phân tích và đối sánh hợp đồng theo cấu trúc cây phân cấp"*, đồng thời viện dẫn thuật toán chỉnh sửa cây của Zhang & Shasha (1989) và LaDiff của Chawathe et al. (1996).
  * Thế nhưng đến Mục 4.3 (dòng 320), thuật toán lại định nghĩa đầu vào là hai tập phẳng $U = \{u_1, \dots, u_m\}$ và $V = \{v_1, \dots, v_n\}$ rồi chạy thẳng `scipy.optimize.linear_sum_assignment(-S)` (Hungarian Algorithm). Tập cạnh $E_{old}, E_{old}$ (quan hệ cha-con giữa `PART` $\rightarrow$ `CHAPTER` $\rightarrow$ `ARTICLE` $\rightarrow$ `CLAUSE` $\rightarrow$ `POINT`) hoàn toàn biến mất khỏi công thức toán học!
  * Bản thân tác giả kế hoạch ở Mục 9.2 Câu hỏi 3 (dòng 610) vẫn chưa chốt được nên ghép đệ quy từ `ARTICLE` xuống `CLAUSE` hay làm phẳng (flatten) toàn bộ.
* **Vì sao nguy hiểm:**
  * Hội đồng sẽ hỏi vặn ngay: *"Cấu trúc cây nằm ở đâu trong hàm mục tiêu $\sum S(u_i, v_j)$ của em? Nếu em làm phẳng toàn bộ các nút ở mọi cấp vào chung ma trận $S$, nội dung văn bản của nút cha (`ARTICLE`) có chứa toàn bộ văn bản của các nút con (`CLAUSE`, `POINT`) hay không? Nếu chứa thì bị tính trùng (double counting); nếu không chứa thì khi một Khoản bị chuyển sang Điều khác, việc ghép đệp quy top-down sẽ bỏ sót, còn việc ghép phẳng không ràng buộc sẽ ghép nhầm nút cấp Điều với nút cấp Khoản hoặc phá vỡ tính lồng nhau của cây."*
* **Đề xuất sửa cụ thể:**
  1. Quy định rõ trong `StructuralNode` ([dòng 246-256](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L246-L256)): trường `content` của nút cha (`ARTICLE`) chỉ chứa phần dẫn nhập của Điều đó, không lặp lại toàn văn của các `CLAUSE` con (hoặc tách thành `own_text` và `subtree_text`).
  2. Thiết kế tường minh **Thuật toán Ghép cặp Phân cấp 2 Pha (Two-Stage Hierarchical Alignment)**:
     * **Pha 1 (Top-down Constrained Matching):** Ghép cặp các nút cùng cấp `ARTICLE` dựa trên `subtree_text` và `title`. Với mỗi cặp `(Article_old, Article_new)` đã ghép, chạy Hungarian cục bộ giữa các `CLAUSE` con trực tiếp của hai Điều đó.
     * **Pha 2 (Cross-Article Orphan Matching):** Thu thập toàn bộ các `CLAUSE`/`POINT` chưa được ghép ở Pha 1 ($U_{\text{orphan}}, V_{\text{orphan}}$) và chạy một lượt Hungarian toàn cục **chỉ giữa các nút cùng `node_type`** để bắt trường hợp một Khoản bị di chuyển từ Điều 3 sang Điều 8.

---

#### Phát hiện 2: Đóng góp khoa học thực chất là tích hợp kỹ thuật (Engineering Integration), còn Bảng khoảng trống nghiên cứu (Mục 2.3) mang tính so sánh thiên lệch ("Bù nhìn" - Strawman Matrix)
* **Mức độ:** **Quan trọng**
* **Mục trong kế hoạch:** Mục 1.5 ([dòng 44-50](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L44-L50)) và Mục 2.3 ([dòng 111-121](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L111-L121)).
* **Vấn đề:**
  * Ba "đóng góp khoa học/học thuật" ở Mục 1.5 là sự kết hợp tuần tự các kỹ thuật tiêu chuẩn đã có sẵn: Regex/FSM + TF-IDF + Pretrained Sentence Embedding + thuật toán Hungarian (1955) + LIS + `difflib.SequenceMatcher` (1988) + Regex NER.
  * Bảng 2.3 (dòng 114–121) đặt hệ thống đề xuất đạt chữ **"Có"** tuyệt đối ở cả 6 tiêu chí, trong khi chỉ thiết kế thí nghiệm đối sánh với duy nhất một baseline là hàm `diff_words` phẳng hiện có trong [app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py#L14-L54).
* **Vì sao nguy hiểm:**
  * So sánh một hệ thống 6 tầng có tách đoạn và Hungarian với một hàm `SequenceMatcher` chạy trên chuỗi phẳng nối bằng `"\n\n"` ([app/services/comparison_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/services/comparison_service.py#L18-L19)) là một phép so sánh không cân sức (Strawman Baseline). Hội đồng sẽ nhận xét: *"Chỉ cần tách văn bản theo dấu xuống dòng `\n\n` rồi ghép đoạn bằng TF-IDF là đã thắng `diff_words` toàn cục rồi. Làm sao em chứng minh được bộ phân tích cú pháp phân cấp HFSM và đặc trưng hình học PDF thực sự tạo ra sự khác biệt?"*
* **Đề xuất sửa cụ thể:**
  1. Điều chỉnh lại ngôn từ ở Mục 1.5: Không nhận vơ việc dùng Hungarian hay Hybrid TF-IDF + Embedding là đóng góp lý thuyết mới; hãy định vị đóng góp ở góc độ **Thiết kế quy trình chuyên biệt cho cấu trúc văn bản pháp lý/hợp đồng tiếng Việt** và **Xây dựng bộ dữ liệu kiểm chuẩn mở (Open Benchmark) đầu tiên cho bài toán so sánh phiên bản hợp đồng tiếng Việt**.
  2. Bổ sung vào Mục 5.5 một **Baseline trung gian công bằng (Baseline 2: Structure-agnostic Paragraph Alignment)**: tách văn bản đơn giản theo dòng trống `\n\n` (không dùng HFSM nhận diện Điều/Khoản/Điểm, không dùng BBox) rồi vẫn chạy Hungarian để chứng minh giá trị thực sự của tầng Phân đoạn cấu trúc pháp lý.

---

### Nhóm B: Câu hỏi Nghiên cứu (RQs) & Giả thuyết (Hypotheses)

#### Phát hiện 3: Giả thuyết H3 đánh tráo độ phức tạp của riêng bước `SequenceMatcher` với tổng thời gian xử lý toàn hệ thống trong RQ4
* **Mức độ:** **Nghiêm trọng**
* **Mục trong kế hoạch:** Mục 1.3 - RQ4 ([dòng 36](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L36)) và Mục 1.4 - H3 ([dòng 41](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L41)).
* **Vấn đề:**
  * **RQ4** hỏi: *"So với baseline `difflib.SequenceMatcher` trên toàn văn bản hiện có, pipeline so sánh theo cấu trúc cải thiện bao nhiêu phần trăm về Precision/Recall/F1... và **chi phí thời gian xử lý (latency) thay đổi như thế nào**?"*
  * Nhưng **H3** lại phát biểu: *"Độ phức tạp thời gian thực tế của việc chạy `SequenceMatcher` cục bộ trên từng cặp điều khoản đã ghép thấp hơn hoặc tương đương so với chạy `SequenceMatcher` một lần trên toàn bộ văn bản hợp đồng dài ($\ge 20$ trang)..."*
* **Vì sao nguy hiểm:**
  * Về mặt toán học, nếu chỉ xét riêng hàm `SequenceMatcher` (vốn có chi phí gần bậc hai theo số lượng token $N$ trong trường hợp xấu), việc chia thành $K$ điều khoản kích thước $N/K$ làm giảm chi phí bước diff từ $O(N^2)$ xuống $O(N^2/K)$.
  * **NHƯNG** khi chạy thực nghiệm trả lời RQ4, tổng thời gian (End-to-End Latency) của pipeline đề xuất bao gồm: `pdfplumber.extract_words()` + `find_tables()` + suy luận mô hình học sâu `sentence-transformers` trên $(m + n)$ điều khoản + tính ma trận Cosine + giải Hungarian + Regex NER. Trên CPU tiêu chuẩn, việc mã hóa 100 điều khoản bằng `sentence-transformers` và quét bảng PDF 20 trang sẽ tốn **hàng giây**, trong khi `diff_words` phẳng của baseline hiện tại chỉ tốn **vài chục mili-giây**! Nếu dùng H3 để biện luận rằng hệ thống mới nhanh hơn baseline, hội đồng sẽ bác bỏ ngay lập tức vì che giấu chi phí của 5 tầng còn lại.
* **Đề xuất sửa cụ thể:**
  * Sửa lại **H3** thành hai giả thuyết con minh bạch:
    * **H3a (Chi phí pha Intra-clause Diff):** Thời gian chạy riêng của bước `SequenceMatcher` cục bộ giảm tỷ lệ nghịch với số lượng điều khoản $K$ so với chạy `SequenceMatcher` toàn văn trên tài liệu $\ge 20$ trang.
    * **H3b (Đánh đổi độ trễ toàn cục - End-to-End Trade-off):** Dù tổng độ trễ toàn pipeline tăng thêm do chi phí trích xuất bảng và tính vector ngữ nghĩa, thời gian xử lý tổng thể cho một cặp hợp đồng 20 trang (digital-born PDF) trên CPU vẫn duy trì dưới ngưỡng tương tác thực tế ($\le 3\text{ giây}$ với chế độ TF-IDF và $\le 10\text{ giây}$ với chế độ Hybrid Embedding).

---

#### Phát hiện 4: RQ3 đặt câu hỏi về việc "giảm tỷ lệ cảnh báo nhiễu (false alarms)" nhờ nhận diện thực thể, nhưng thiết kế thí nghiệm (Mục 5.4 & 5.5) không có độ đo và không có Ablation Study để kiểm chứng
* **Mức độ:** **Quan trọng**
* **Mục trong kế hoạch:** Mục 1.3 - RQ3 ([dòng 35](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L35)), Mục 4.5 ([dòng 352-367](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L352-L367)), Mục 5.4 ([dòng 409-411](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L409-L411)) và Mục 5.5 ([dòng 418-421](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L418-L421)).
* **Vấn đề:**
  * RQ3 hỏi: *"Việc bổ sung tầng nhận diện thực thể pháp lý (số tiền, ngày tháng, tỷ lệ, bên, từ khóa nghĩa vụ) giúp **giảm tỷ lệ cảnh báo nhiễu (false alarms)** và tăng khả năng phát hiện thay đổi trọng yếu (critical changes) ra sao?"*
  * Tuy nhiên, tầng nhận diện thực thể ở Tầng 4–5 **không hề lọc bỏ** các thay đổi từ vựng mà chỉ gắn nhãn `SemanticChangeType` và `SeverityLevel`. Hơn nữa, trong Mục 5.5 (Thí nghiệm Ablation Study chỉ có A1, A2, A3), hoàn toàn **không có biến thể Ablation nào tắt/bật bộ nhận diện thực thể** để đo mức giảm "false alarms"!
* **Vì sao nguy hiểm:**
  * Đến Chương 4 (Mục 4.5, dòng 559: *"Trả lời RQ3 & RQ4"*), sinh viên sẽ không có bất kỳ con số đối chứng nào để kết luận tầng thực thể giúp giảm bao nhiêu phần trăm cảnh báo nhiễu, dẫn đến việc một trong bốn câu hỏi nghiên cứu chính của khóa luận bị bỏ lửng.
* **Đề xuất sửa cụ thể:**
  1. Định nghĩa chính xác khái niệm **"Cảnh báo nhiễu mức độ rủi ro cao (High/Critical False Alarm Rate - FAR)"**: tỷ lệ các thay đổi vô hại về mặt pháp lý (ví dụ: đổi cách viết `"100.000.000 VNĐ"` $\rightarrow$ `"100.000.000 đồng"`, thêm dấu phẩy, đánh lại số thứ tự điều khoản) bị hệ thống không có bộ lọc thực thể/ngữ nghĩa xếp nhầm vào nhóm cần cảnh báo ngang hàng với thay đổi nội dung.
  2. Bổ sung **Biến thể Ablation A4 (Entity Normalization vs. Raw Token Change)** vào Mục 5.5: So sánh hệ thống có chuẩn hóa giá trị thực thể (`EntityDelta.normalized_old != normalized_new`) với biến thể chỉ bắt thay đổi dựa trên khớp chuỗi thô.

---

### Nhóm C: Thiết kế Đánh giá, Vòng lặp Tự chứng minh & Độ tin cậy Thực nghiệm

#### Phát hiện 5: Vòng lặp tự chứng minh (Circularity / Tautology) nghiêm trọng trong thiết kế Tập dữ liệu tổng hợp (Controlled Synthetic Dataset)
* **Mức độ:** **Nghiêm trọng**
* **Mục trong kế hoạch:** Mục 1.5 ([dòng 47](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L47)), Mục 4.5 ([dòng 353-362](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L353-L362)), Mục 5.2 ([dòng 387-391](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L387-L391)) và Mốc 3–4 ([dòng 443-444](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L443-L444)).
* **Vấn đề:**
  * Kế hoạch mô tả cách tạo 100 cặp hợp đồng tổng hợp tại Mục 5.2 (dòng 388–390): *"Viết kịch bản Python (`scripts/generate_synthetic_dataset.py`) áp dụng các toán tử biến đổi ngẫu nhiên có kiểm soát lên các hợp đồng gốc đã được phân tích cấu trúc chuẩn... Thay đổi số tiền ($\pm 10\%, \times 10$), đổi ngày giao hàng/thời hạn thanh toán ($30\text{ ngày} \rightarrow 45\text{ ngày}$), đổi lãi suất phạt ($0.05\%/\text{ngày} \rightarrow 0.02\%/\text{ngày}$), đảo từ khóa nghĩa vụ (`"Bên B phải"` $\rightarrow$ `"Bên B có thể"`)."*
  * Ngay tại Mục 4.5 (dòng 353–361), hệ thống lại dùng đúng bộ Regex bắt mẫu `dd/mm/yyyy`, `%\s*/(năm|tháng|ngày)` và đúng từ điển `{"phải", ...}` $\rightarrow$ `{"có thể", ...}` để nhận diện các thay đổi đó!
  * Chưa hết: nếu kịch bản `generate_synthetic_dataset.py` sử dụng chính `contract_parser.py` để "phân tích cấu trúc chuẩn" của hợp đồng gốc trước khi hoán đổi/xóa/tách điều khoản, rồi sau đó lại đưa 100 cặp hợp đồng đã biến đổi này vào hệ thống để chấm điểm phân đoạn và ghép cặp, thì toàn bộ thực nghiệm biến thành **bài toán tự sinh - tự giải (Self-fulfilling Prophecy)**.
* **Vì sao nguy hiểm:**
  * Đây là lỗi phương pháp luận nặng nhất khi bảo vệ trước hội đồng. Một ủy viên phản biện sẽ hỏi ngay: *"Em viết hàm `generate_synthetic_dataset.py` tìm chuỗi `'phải'` đổi thành `'có thể'`, rồi em viết hàm `change_classifier.py` kiểm tra nếu `'phải'` đổi thành `'có thể'` thì gán nhãn `OBLIGATION_CHANGE`, sau đó em báo cáo độ chính xác đạt 95–100%. Vậy em đang đánh giá trí thông minh của hệ thống hay chỉ đang kiểm tra xem hai file code của em có dùng chung một danh sách từ khóa hay không?"*
* **Đề xuất sửa cụ thể:**
  1. **Tách biệt tuyệt đối nguồn cấu trúc gốc:** Hợp đồng gốc dùng làm hạt giống cho `generate_synthetic_dataset.py` phải được **con người rà soát và hiệu chỉnh cây cấu trúc JSON bằng tay (Human-verified Gold Trees)** trước khi áp dụng toán tử biến đổi.
  2. **Giới hạn vai trò của Tập Synthetic:** Nêu rõ trong Chương 4 rằng tập Synthetic (100 cặp) **chỉ được dùng để đánh giá thuật toán Ghép cặp điều khoản (RQ2 - Alignment & Move Detection) và phân tích độ nhạy (Sensitivity Analysis)** khi tăng dần tỷ lệ nhiễu từ vựng/vị trí; **tuyệt đối không** dùng tập Synthetic làm thước đo chính cho RQ1 (Phân đoạn cấu trúc) và RQ3 (Nhận diện thực thể & nghĩa vụ).
  3. **Chống rò rỉ quy tắc trên Tập Bán thủ công (Human-Curated Dataset):** Khi tạo các bản sửa đổi bán thủ công, người biên tập phải thực hiện chỉnh sửa tự nhiên theo tình huống đàm phán (ví dụ: diễn đạt lại câu, dùng từ đồng nghĩa ngoài từ điển cơ bản, thay đổi cấu trúc câu chủ động - bị động) và bộ từ điển trong `entity_extractor.py` phải được thiết kế khóa cố định trước khi xem dữ liệu test (Blind Test Set).

---

#### Phát hiện 6: Hai trong ba bất biến kiểm thử toán học (Property-Based Testing Invariants) ở Mục 7.1 bị sai khi đối chiếu với mã nguồn hiện tại và thuật toán đề xuất
* **Mức độ:** **Nghiêm trọng**
* **Mục trong kế hoạch:** Mục 7.1 ([dòng 458-461](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L458-L461)), đối chiếu với [app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py#L4-L54), [app/services/comparison_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/services/comparison_service.py#L4-L12) và Mục 4.3 ([dòng 339-344](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L339-L344)).
* **Vấn đề:**
  1. **Sai lầm ở "Tính bảo toàn văn bản (Reconstruction)" ([dòng 461](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L461)):**
     * Kế hoạch khẳng định: *"Từ chuỗi `old_text` và danh sách opcodes/spans của `diff_words`, áp dụng các phép biến đổi phải tái tạo chính xác `new_text`."*
     * Hãy nhìn vào mã nguồn thực tế tại [app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py#L4-L28): `tokenize_with_spans` tách từ bằng `re.finditer(r"\S+", text)` (bỏ qua mọi khoảng trắng) và `diff_words` bỏ qua mọi khối `if tag == "equal": continue`. Do đó:
       * Nếu `old_text = "Điều 1: Giá trị"` và `new_text = "Điều   1:\nGiá trị"`, danh sách token `\S+` của hai chuỗi giống hệt nhau nên `diff_words` trả về `changes = []`. Từ `old_text` và `changes = []`, ta chỉ nhận lại được `old_text`, **không thể tái tạo được `new_text`**!
       * Thậm chí ngay trong [app/services/comparison_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/services/comparison_service.py#L7-L12), hàm `compare_text` đang trả về `"is_identical": old_text == new_text` (`False`) cùng lúc với `"changes": []` (rỗng) khi hai văn bản chỉ khác nhau khoảng trắng — một lỗi mâu thuẫn logic có sẵn trong codebase mà bản kế hoạch chưa phát hiện ra!
  2. **Sai lầm ở "Tính đối xứng nghịch đảo (Symmetry)" ([dòng 460](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L460)):**
     * Kế hoạch khẳng định: *"số lượng điều khoản `MOVED` giữa `compare(A, B)` và `compare(B, A)` phải bằng nhau"*, và nút `ADDED` ở `compare(A, B)` phải là `DELETED` ở `compare(B, A)`.
     * Nhưng ở Mục 4.3 Bước 3 ([dòng 339](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L339)), thuật toán phát hiện Tách/Gộp chỉ được định nghĩa một chiều: kiểm tra xem $u_i \in U_{\text{unmatched}}$ có được bao phủ bởi hợp của 2 nút liên tiếp $v_j, v_{j+1}$ hay không (`SPLIT` $1 \rightarrow 2$), mà chưa định nghĩa chiều ngược lại khi 2 nút cũ gộp thành 1 nút mới (`MERGE` $2 \rightarrow 1$) hay điều kiện ưu tiên khi cả hai chiều xảy ra. Hơn nữa, khi có bước Coalescing (gom cụm các thay đổi cách nhau $\le 2$ ký tự ở [dòng 350](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L350)), nếu điều kiện gom cụm chỉ xét độ dài từ nối ở bản cũ hoặc bản mới thì tính đối xứng giữa `compare(A, B)` và `compare(B, A)` cũng sẽ bị phá vỡ.
* **Vì sao nguy hiểm:**
  * Việc đưa `hypothesis` Property-Based Testing vào kế hoạch nghe rất ấn tượng về mặt học thuật, nhưng nếu bất biến đưa ra bị sai về mặt toán học, chỉ cần chạy `pytest tests/test_properties.py` lần đầu tiên là `hypothesis` sẽ tìm ra phản ví dụ (`"a b"` vs `"a  b"`) trong chưa đầy 0.1 giây và làm gãy toàn bộ test suite.
* **Đề xuất sửa cụ thể:**
  1. Phát biểu lại bất biến **Reconstruction**: Với `old_text` và `changes`, nếu áp dụng thay thế các `old_span` bằng `new_text` tương ứng theo thứ tự từ cuối lên đầu, chuỗi kết quả sau khi **chuẩn hóa khoảng trắng (`re.sub(r"\s+", " ", text).strip()`)** phải bằng chính xác `new_text` đã chuẩn hóa khoảng trắng.
  2. Sửa [app/services/comparison_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/services/comparison_service.py#L8): bổ sung trường `is_exact_match: bool` (`old_text == new_text`) và `is_token_identical: bool` (`len(changes) == 0`) hoặc phát sinh thay đổi loại `FORMATTING_ONLY` khi `old_text != new_text` nhưng `changes == []`.
  3. Định nghĩa đối xứng hoàn toàn cho toán tử `SPLIT` ($u_i \rightarrow \{v_j, v_{j+1}\}$) và `MERGE` ($\{u_i, u_{i+1}\} \rightarrow v_j$) bằng cùng một hàm `token_containment_ratio`.

---

#### Phát hiện 7: Cỡ mẫu của Tập kiểm thử bán thủ công (15–20 cặp, gồm cả 5 cặp PDF quét) quá nhỏ để kiểm chứng thống kê các ngưỡng mục tiêu ($F_1 \ge 0.90, 0.92, 0.85$)
* **Mức độ:** **Quan trọng**
* **Mục trong kế hoạch:** Mục 1.4 ([dòng 39-40](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L39-L40)), Mục 5.2 ([dòng 392-393](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L392-L393)), Mục 5.3 ([dòng 400](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L400)) và Mục 6 ([dòng 442-444](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L442-L444)).
* **Vấn đề:**
  * Tập kiểm thử thực tế bán thủ công chỉ có **15–20 cặp hợp đồng**, trong đó đã cắt ra **5 cặp là PDF quét/ảnh chụp** để kiểm thử nhánh OCR (chỉ còn 10–15 cặp PDF số hóa chuẩn).
  * Hệ thống cần đánh giá tới **7 nhãn `ChangeCategory`** (`UNCHANGED`, `ADDED`, `DELETED`, `MODIFIED`, `MOVED`, `MOVED_AND_MODIFIED`, `RENUMBERED`) và **7 nhãn `SemanticChangeType`** bằng độ đo **Macro-$F_1$** ([dòng 410](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L410)).
  * Trong 15 cặp hợp đồng thực tế, các lớp hiếm như `MOVED`, `MOVED_AND_MODIFIED`, hoặc `PARTY_CHANGE` có thể chỉ xuất hiện vài lần (ví dụ 5–10 mẫu trên toàn tập). Với mẫu số $N = 8$, chỉ cần hệ thống đoán sai 2 mẫu (rất dễ xảy ra trên 5 bản PDF quét OCR tiếng Việt bị nhầm dấu hoặc mất dòng), điểm $F_1$ của lớp đó sẽ sụt xuống $\le 0.75$, kéo tụt toàn bộ Macro-$F_1$ xuống dưới ngưỡng cam kết!
* **Vì sao nguy hiểm:**
  * Hội đồng chấm sẽ yêu cầu xem bảng thống kê phân bố nhãn (Label Distribution Table) của tập dữ liệu kiểm thử. Nếu có những lớp chỉ có 3–5 mẫu mà sinh viên vẫn tính Macro-$F_1$ và kết luận hệ thống đạt hiệu quả cao, hội đồng sẽ đánh giá thực nghiệm thiếu độ tin cậy thống kê.
* **Đề xuất sửa cụ thể:**
  1. Đặt chỉ tiêu kích thước dữ liệu ở **cấp độ nút cấu trúc và phép biến đổi (Clause-level & Change-instance quota)** thay vì chỉ đếm số lượng file PDF: tập kiểm thử bán thủ công (20–25 cặp hợp đồng) phải đảm bảo tối thiểu **$\ge 500$ nút điều khoản/khoản**, với mỗi nhãn trong 7 lớp `ChangeCategory` và 7 lớp `SemanticChangeType` xuất hiện tối thiểu **$\ge 25$ lần**.
  2. Tách riêng bảng đánh giá cho **Digital-born PDF** (cam kết $F_{1,\text{seg}} \ge 0.90, F_{1,\text{align}} \ge 0.90$) và **Scanned PDF qua OCR** (đánh giá riêng độ suy giảm hiệu năng do lỗi OCR, không gộp chung vào một ngưỡng cứng).

---

### Nhóm D: Lỗ hổng Thiết kế Thuật toán & Kỹ thuật (Algorithmic & Technical Flaws)

#### Phát hiện 8: Công thức tính điểm tương đồng $S(u_i, v_j)$ và ngưỡng cắt $\tau$ trong thuật toán Ghép cặp (Mục 4.3) bị lỗi khi nút không có tiêu đề (`title = None`) và bất nhất với Sơ đồ Kiến trúc (Mục 3.1)
* **Mức độ:** **Quan trọng**
* **Mục trong kế hoạch:** Mục 3.1 ([dòng 145](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L145)), Mục 3.3 ([dòng 250-252](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L250-L252)) và Mục 4.3 ([dòng 323-336](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L323-L336)).
* **Vấn đề:**
  1. **Lỗi hụt 25% thang điểm cho các nút cấp Khoản/Điểm:** Trong schema `StructuralNode` ([dòng 251](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L251)), `title` có kiểu `str | None = None` vì trong hợp đồng Việt Nam, cấp `ARTICLE` (*"Điều 5. Phương thức thanh toán"*) có tiêu đề, nhưng cấp `CLAUSE` (*"5.1. Bên A thanh toán cho Bên B..."*) và `POINT` (*"a) Đợt 1 thanh toán 30%..."*) hầu như **không có tiêu đề**. Thế nhưng công thức ở Mục 4.3 ([dòng 324-325](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L324-L325)) cố định trọng số $w_{\text{title}} = 0.25$. Khi hai Khoản không có tiêu đề được so sánh với nhau, $\text{Sim}_{\text{title}}(u_i, v_j) = 0$, dẫn tới điểm tối đa của $S(u_i, v_j)$ bị chặn trên ở $0.75$! Khi so với ngưỡng $\tau_{\text{high}} = 0.65$ ([dòng 334](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L334)), một Khoản chỉ cần sửa vài chữ là rơi ngay xuống dưới $0.65$ và bị gắn cờ `AMBIGUOUS_CLAUSE_ALIGNMENT`.
  2. **Bất nhất giữa Sơ đồ Mục 3.1 và Thuật toán Mục 4.3:** Sơ đồ Mermaid ở Mục 3.1 ([dòng 145](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L145)) và mô tả module ở Mục 3.2 ([dòng 182](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L182)) nêu rõ có **Stage 1: Exact / Anchor Match (Số hiệu + Tiêu đề)** trước khi tính ma trận tương đồng. Nhưng sang Mục 4.3 ([dòng 320-337](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L320-L337)), bước Anchor Match hoàn toàn biến mất, thay vào đó tính ma trận $S \in [0, 1]^{m \times n}$ cho toàn bộ các cặp ngay từ Bước 1.
* **Vì sao nguy hiểm:**
  * Sự thiếu nhất quán giữa sơ đồ kiến trúc và mô tả thuật toán làm giảm tính chặt chẽ của Chương 3 khóa luận; còn lỗi không chuẩn hóa lại trọng số khi `title is None` sẽ gây ra tỷ lệ báo động giả (`AMBIGUOUS_CLAUSE_ALIGNMENT`) rất cao ở cấp Khoản và Điểm.
* **Đề xuất sửa cụ thể:**
  * Viết lại công thức tính điểm tương đồng ở Mục 4.3 dưới dạng trọng số thích nghi (Adaptive Weight Normalization):
    $$S(u_i, v_j) = \frac{\sum_{k \in \mathcal{F}(u_i, v_j)} w_k \cdot \text{Sim}_k(u_i, v_j)}{\sum_{k \in \mathcal{F}(u_i, v_j)} w_k}$$
    trong đó tập đặc trưng khả dụng $\mathcal{F}(u_i, v_j)$ chỉ bao gồm $\text{title}$ khi cả $u_i$ và $v_j$ đều có `title` khác rỗng. Đồng thời mô tả rõ Bước 0 (Exact Content/Anchor Match) trong Mục 4.3 để khớp 100% với sơ đồ Mục 3.1.

---

#### Phát hiện 9: Thuật toán dùng LIS đơn thuần để phân biệt `MOVED` và `RENUMBERED` (Mục 4.3) mâu thuẫn với chính Kịch bản Demo 1 (Mục 8.2) và sai lệch khi di chuyển khối điều khoản
* **Mức độ:** **Quan trọng**
* **Mục trong kế hoạch:** Mục 4.3 Bước 3 ([dòng 340-344](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L340-L344)) và Mục 8.2 Kịch bản Demo 1 ([dòng 570-575](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L570-L575)).
* **Vấn đề:**
  1. **Mâu thuẫn ngay trong Kịch bản Demo 1:** Ở Mục 8.2 ([dòng 570](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L570)), kịch bản giả định *"Điều 4 (Phương thức thanh toán) và Điều 7 (Trách nhiệm bảo mật) bị đảo vị trí cho nhau"*. Khi Điều 4 và Điều 7 hoán đổi vị trí cho nhau (trong khi Điều 5 và Điều 6 vẫn nằm ở vị trí 5 và 6), dãy chỉ số mới ứng với $i = (1, 2, 3, 4, 5, 6, 7)$ sẽ là $j = (1, 2, 3, 7, 5, 6, 4)$. Dãy con tăng dài nhất (LIS) bắt buộc phải đi qua $(1, 2, 3, 5, 6)$, tức là **cả Điều 4 ($j=7$) lẫn Điều 7 ($j=4$) đều nằm ngoài LIS** và cả hai đều bị gán nhãn `MOVED` (hoặc `MOVED_AND_MODIFIED`). Thế nhưng ở [dòng 575](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L575), kế hoạch lại mô tả hệ thống chỉ *"gắn nhãn `MOVED` cho Điều 7"*!
  2. **Lỗi khi di chuyển khối điều khoản (Block Move Inversion):** Nếu một cụm 4 điều khoản ngắn liên tiếp (ví dụ Điều 2, 3, 4, 5) được dời xuống sau 2 điều khoản dài (Điều 6, 7), chuỗi chỉ số mới của $(2, 3, 4, 5, 6, 7)$ là $(4, 5, 6, 7, 2, 3)$. Vì LIS không có trọng số chỉ đếm số lượng nút, nó sẽ chọn $(4, 5, 6, 7)$ (độ dài 4) thuộc LIS (`RENUMBERED`) và kết luận ngược rằng Điều 6, 7 (độ dài 2) mới là các điều khoản bị `MOVED`!
* **Vì sao nguy hiểm:**
  * Nếu hội đồng yêu cầu chạy thử đúng kịch bản Demo 1 hoặc hỏi tại sao dời một cụm điều khoản phụ lại làm các điều khoản chính bị báo `MOVED`, sinh viên sẽ lúng túng vì chưa lường trước đặc tính toán học của LIS không trọng số.
* **Đề xuất sửa cụ thể:**
  1. Thay LIS thuần túy bằng **Weighted LIS (Dãy con tăng có tổng trọng số cực đại)**, trong đó trọng số của mỗi cặp ghép $(u_i, v_j)$ tỷ lệ thuận với độ dài văn bản (số lượng token) hoặc độ tương đồng vị trí neo để ưu tiên giữ các khối văn bản lớn làm khung tham chiếu cố định.
  2. Sửa lại mô tả Kịch bản Demo 1 ở Mục 8.2 ([dòng 570-575](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L570-L575)): hoặc nói rõ cả Điều 4 và Điều 7 đều được đánh dấu di chuyển (hoán vị), hoặc sửa tình huống demo thành *"Chuyển Điều 4 xuống đặt sau Điều 7"* (khi đó chỉ duy nhất Điều 4 mang nhãn `MOVED`, còn Điều 5, 6, 7 mang nhãn `RENUMBERED`).

---

#### Phát hiện 10: Quy tắc khử nhập nhằng số thứ tự Khoản ($k = k_{prev} + 1$) và Schema `BoundingBox` đơn lẻ không xử lý được dữ liệu thực tế
* **Mức độ:** **Quan trọng**
* **Mục trong kế hoạch:** Mục 3.3 ([dòng 239-256](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L239-L256)), Mục 4.1 ([dòng 295-298](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L295-L298)) và Mục 4.2 ([dòng 313-315](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L313-L315)).
* **Vấn đề:**
  1. **Điều kiện liên tục $k = k_{prev} + 1$ ([dòng 314](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L314)):** Trong dự thảo hợp đồng sửa đổi, người soạn thảo rất hay xóa một khoản ở giữa mà quên đánh lại số (ví dụ còn `1.1`, `1.3`, mất `1.2`) hoặc đánh trùng số (`1.1`, `1.2`, `1.2`). Với đầu vào là văn bản thuần (Plain Text qua endpoint `/api/v1/comparisons/text`), hệ thống **không có tọa độ lề trái `x0`**. Khi đó điều kiện $k = k_{prev} + 1$ sẽ bác bỏ tiêu đề Khoản `1.3` và gộp toàn bộ nội dung của Khoản `1.3` vào bên trong Khoản `1.1`!
  2. **Schema `bbox: BoundingBox | None = None` ([dòng 256](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L256)):** `StructuralNode` có `page_numbers: list[int]` (cho phép một điều khoản nằm vắt qua nhiều trang), nhưng trường `bbox` lại chỉ là **1 đối tượng `BoundingBox` duy nhất** gắn với `page: int` đơn lẻ ([dòng 240](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L240)). Khi một Điều bắt đầu ở cuối trang 2 và kết thúc ở đầu trang 3, một hộp `BoundingBox` duy nhất không thể biểu diễn được vị trí của nó trên cả 2 trang.
  3. **Ngưỡng khử Header/Footer $P \ge 3$ trang và $\ge 60\%$ ([dòng 296-298](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L296-L298)):** Hợp đồng ngắn 2 trang hoặc phụ lục hợp đồng 2 trang sẽ bị bỏ qua hoàn toàn, khiến chuỗi `"Trang 1/2"` chui thẳng vào nội dung điều khoản cuối trang 1.
* **Vì sao nguy hiểm:**
  * Lỗi ở tầng trích xuất và phân đoạn (Tầng 1 & Tầng 2) sẽ gây hiệu ứng dây chuyền (Domino Effect): gộp nhầm 2 khoản làm một sẽ khiến cả thuật toán Hungarian ở Tầng 3 lẫn Diff ở Tầng 4 cho ra kết quả sai lệch.
* **Đề xuất sửa cụ thể:**
  1. Đổi `bbox: BoundingBox | None = None` trong `StructuralNode` thành `bboxes: list[BoundingBox] = Field(default_factory=list)` (mỗi trang mà điều khoản đi qua có 1 bounding box riêng).
  2. Nới lỏng quy tắc kiểm tra số hiệu Khoản $k$: chấp nhận $k_{prev} \le k \le k_{prev} + 3$ (b
*(Tiếp tục từ Mục Đề xuất sửa cụ thể của Phát hiện 10)*

  2. Nới lỏng quy tắc kiểm tra số hiệu Khoản $k$: chấp nhận $k_{prev} \le k \le k_{prev} + 3$ (bắt được cả trường hợp đánh trùng số hoặc bỏ sót 1–2 số do quên đánh lại số thứ tự), kết hợp kiểm tra ngữ cảnh âm tiết đứng ngay sau dấu chấm/ngoặc (không phải là đơn vị tiền tệ `đồng`, `VNĐ`, `USD` và không phải định dạng ngày tháng `dd/mm/yyyy`).
  3. Bổ sung bộ mẫu Regex độc lập để khử dòng số trang tiêu chuẩn (`^Trang\s+\d+(\s*/\s*\d+)?$`, `^Page\s+\d+(\s+of\s+\d+)?$`, `^-\s*\d+\s*-$`) ở đáy trang ngay cả khi tài liệu chỉ có $P = 1$ hoặc $P = 2$ trang.

---

#### Phát hiện 11: Nhận diện `OBLIGATION_CHANGE` chỉ bằng khớp từ khóa đơn lẻ trong từ điển sẽ sinh ra lượng lớn Dương tính giả (False Positives) trên tiếng Việt
* **Mức độ:** **Quan trọng**
* **Mục trong kế hoạch:** Mục 4.5 ([dòng 357-361](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L357-L361)).
* **Vấn đề:**
  * Kế hoạch định nghĩa:
    * Nhóm bắt buộc: `{"phải", "bắt buộc", "cam kết", "chịu trách nhiệm", "nghĩa vụ"}`
    * Nhóm cho phép/tùy nghi: `{"có thể", "được quyền", "có quyền", "tùy thuộc"}`
    * Nhóm phủ định/miễn trừ: `{"không", "không phải", "miễn trừ", "loại trừ"}`
  * Trong tiếng Việt, từ `"phải"` và `"không"` là các từ đa nghĩa xuất hiện với tần suất cực cao trong các cụm từ không mang tính tình thái nghĩa vụ:
    * Từ `"phải"`: *"bên **phải**"*, *"không **phải** là"*, *"gặp **phải** sự cố bất khả kháng"*.
    * Từ `"không"`: *"vận chuyển đường **không**"*, *"trong thời gian **không** quá 05 ngày"*, *"nếu **không** có thỏa thuận khác"*.
    * Từ `"có thể"`: *"trong phạm vi sớm nhất **có thể**"*.
* **Vì sao nguy hiểm:**
  * Nếu chỉ kiểm tra sự xuất hiện/biến mất của các từ trong tập hợp trên ở `old_fragment` và `new_fragment`, mọi câu sửa diễn đạt thông thường có chứa chữ `"không"` hoặc `"phải"` đều bị gán nhãn `OBLIGATION_CHANGE` kèm mức độ `CRITICAL`! Điều này đi ngược lại hoàn toàn mục tiêu giảm cảnh báo nhiễu của RQ3.
* **Đề xuất sửa cụ thể:**
  * Thay vì khớp từ rời rạc (unigram keyword matching), bắt buộc áp dụng **Mẫu cấu trúc ngữ cảnh (Contextual Phrase Patterns)**:
    1. Loại trừ các cụm từ cố định không mang nghĩa tình thái (`"bên phải"`, `"gặp phải"`, `"trong phạm vi có thể"`, `"không quá"`, `"không muộn hơn"`).
    2. Yêu cầu từ khóa tình thái phải nằm trong cửa sổ ngữ cảnh liền sau danh từ chỉ chủ thể (`Bên A`, `Bên B`, `Bên Mua`, `Bên Bán`, `Các Bên`, `Nhà thầu`, `Chủ đầu tư`) trong phạm vi $\le 5$ token hoặc đi kèm động từ hành vi pháp lý (`thanh toán`, `bồi thường`, `bàn giao`, `bảo mật`, `chịu phạt`).

---

#### Phát hiện 12: Một số chi tiết bất nhất nhỏ về đường dẫn script và kiểm thử tĩnh
* **Mức độ:** **Nhỏ**
* **Mục trong kế hoạch:** Mục 5.2 ([dòng 388](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L388)), Mục 6 ([dòng 441-443](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L441-L443)) và Mục 7.2 ([dòng 470-512](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L470-L512)).
* **Vấn đề:**
  1. Tên và đường dẫn script sinh dữ liệu bị viết khác nhau ở 3 nơi: Mục 5.2 ([dòng 388](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L388)) ghi `scripts/generate_synthetic_dataset.py`, Mốc 3 ([dòng 443](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L443)) ghi `generate_synthetic_dataset.py`, còn cây thư mục ở Mục 7.2 ([dòng 510](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L510)) lại ghi `experiments/generate_dataset.py`.
  2. Tên thư mục dữ liệu ở Mốc 1 ([dòng 441](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L441)) ghi `data/raw/`, ở Mục 9.1 ([dòng 595](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L595)) ghi `data/sample/`, còn ở Mục 7.2 ([dòng 505](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L505)) ghi `data/raw_templates/`.
  3. Mục 7.1 ([dòng 455-465](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L455-L465)) chia thư mục test thành 4 thư mục con (`tests/unit/`, `tests/property/`, `tests/regression/`, `tests/integration/`), nhưng cây thư mục ở Mục 7.2 ([dòng 513-520](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L513-L520)) lại để phẳng tất cả các file `test_*.py` ngay dưới `tests/`.
  4. Trong mã nguồn hiện tại, nhiều hàm như `extract_document(filename, file_stream)` trong [app/services/document_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/services/document_service.py#L3) hay `tokenize_with_spans(text)` trong [app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py#L4) chưa có type annotations đầy đủ; nếu bật `mypy` nghiêm ngặt trong GitHub Actions CI ngay Tuần 1 ([dòng 473](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L473)) sẽ báo lỗi nếu không bổ sung type hints cho code cũ.
* **Vì sao nguy hiểm:**
  * Không làm hỏng thuật toán nhưng thể hiện sự thiếu đồng bộ trong tài liệu thiết kế kỹ thuật và làm mất thời gian khi viết script tự động hóa.
* **Đề xuất sửa cụ thể:**
  * Chuẩn hóa thống nhất một cấu trúc thư mục duy nhất trong toàn văn bản kế hoạch (`experiments/generate_synthetic_dataset.py`, `data/raw_templates/`, giữ cấu trúc phẳng trong `tests/` kết hợp `@pytest.mark.unit`, `@pytest.mark.property`, `@pytest.mark.integration`).

---

### Nhóm E: Phạm vi Đề tài & Lộ trình 16 Tuần cho 1 Sinh viên (Scope & Feasibility)

#### Phát hiện 13: Phạm vi quá rộng (Scope Creep nghiêm trọng) — khối lượng công việc thực tế tương đương 2.5 đến 3 đồ án tốt nghiệp cộng lại
* **Mức độ:** **Nghiêm trọng**
* **Mục trong kế hoạch:** Mục 1.6 ([dòng 53-62](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L53-L62)), Mục 3.2 ([dòng 173-189](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L173-L189)), Mục 4.1–4.5 ([dòng 293-367](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L293-L367)) và Mục 6 ([dòng 432-446](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L432-L446)).
* **Vấn đề:**
  * Kế hoạch giả định **1 sinh viên làm việc 20–25 giờ/tuần trong 16 tuần** (tổng cộng **320–400 giờ công**, trong đó đã mất ít nhất 80–100 giờ để viết khóa luận 5 chương, làm slide, thu thập và gán nhãn dữ liệu; chỉ còn **~240–300 giờ lập trình & thực nghiệm**).
  * Thế nhưng trong 240–300 giờ đó, sinh viên tự đặt mục tiêu giải quyết đồng thời:
    1. **OCR tiếng Việt + Phục hồi lỗi bảng mã font PDF (TCVN3/VNI/CID) + Khử Header/Footer hình học** (Mốc 2).
    2. **Parser phân tích cú pháp hợp đồng 6 cấp + Tách bảng biểu từ PDF (`find_tables`)** (Mốc 2).
    3. **Thuật toán Alignment đa đặc trưng (TF-IDF + Sentence Embeddings) + Hungarian + LIS + Phát hiện Tách/Gộp (`SPLIT`/`MERGE`)** (Mốc 3).
    4. **Thuật toán So sánh Bảng biểu (`table_diff.py`) xử lý khớp hàng/cột** (Mốc 4).
    5. **Trích xuất và chuẩn hóa thực thể pháp lý (bao gồm cả chuyển đổi số tiền viết bằng chữ tiếng Việt `"một trăm triệu đồng"` sang số thực) + Phân loại tình thái nghĩa vụ** (Mốc 4).
    6. **Xây dựng bộ dữ liệu từ con số 0:** Thu thập & ẩn danh hóa PII cho 30–50 hợp đồng + Viết bộ sinh 100 cặp Synthetic + Tự biên tập & gán nhãn thủ công 15–20 cặp hợp đồng nhiều vòng + Thuê/nhờ người thứ hai gán nhãn độc lập để tính Cohen's Kappa $\kappa \ge 0.80$.
    7. **Xây dựng Exporter HTML Side-by-Side Redline + Giao diện Web Demo + Property-based testing + CI/CD** (Mốc 5).
    8. Thậm chí còn để ngỏ khả năng **mở rộng sang tiếng Anh (tập dữ liệu CUAD)** ([dòng 54, 382, 427](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L382)).
* **Vì sao nguy hiểm:**
  * Chỉ riêng **Mốc 2 (Tuần 3–5, tức ~60–75 giờ làm việc)** đã yêu cầu vừa làm trích xuất tọa độ/font/bảng PDF, vừa làm khử header/footer, vừa viết HFSM Parser 6 cấp đạt $F_1 \ge 0.90$, vừa tích hợp nhánh OCR (`VietOCR`/`Tesseract`). Trong thực tế, khi chạy OCR trên trang PDF quét, đầu ra là văn bản thuần bị mất thông tin font chuẩn của PDF gốc và thường bị gãy dòng/sai dấu câu đầu dòng (`"Điều 1"` thành `"Điêu I"` hoặc `"Ðiểu 1"`), làm cho bộ Regex/HFSM viết cho PDF chuẩn bị vỡ hoàn toàn!
  * Việc dàn trải sức lực cho cả OCR, Table Diff và Đa ngôn ngữ sẽ khiến các mô-đun cốt lõi (Segmentation & Clause Alignment) chỉ dừng ở mức chắp vá, không kịp làm thực nghiệm sâu cho Chương 4.
* **Đề xuất sửa cụ thể:**
  * Cắt giảm mạnh các nhánh phụ (xem chi tiết ở **Phần 4** bên dưới) để dồn 100% nguồn lực vào luồng cốt lõi: **Digital-born PDF / Text tiếng Việt $\rightarrow$ Phân đoạn cấu trúc Điều/Khoản/Điểm $\rightarrow$ Ghép cặp phân cấp 2 pha $\rightarrow$ Diff mức từ & Thực thể cốt lõi $\rightarrow$ Báo cáo Redline**.

---

## PHẦN 2: CÁC CÂU HỎI HỘI ĐỒNG CHẤM SẼ HỎI VẶN (VIVA / DEFENSE QUESTIONS)

Khi đứng trước hội đồng bảo vệ, sinh viên chắc chắn sẽ đối mặt với 8 câu hỏi xoáy trực diện sau đây:

1. **Câu hỏi vặn về Tính mới & Baseline (Xoáy vào Mục 1.5 & 2.3):**
   > *"Baseline mà em dùng để so sánh là `difflib.SequenceMatcher` chạy trên toàn bộ văn bản phẳng nối bằng `\n\n`. Ai cũng biết chạy diff phẳng trên văn bản có điều khoản đổi chỗ thì kết quả sẽ hỏng. Tại sao em không so sánh với một baseline công bằng hơn, ví dụ tách đoạn theo dấu xuống dòng `\n\n` rồi ghép đoạn bằng Cosine TF-IDF, hoặc dùng thuật toán Tree Edit Distance có sẵn như `xmldiff` / Zhang-Shasha? Phần trăm cải thiện bao nhiêu là nhờ cây cấu trúc pháp lý của em, và bao nhiêu chỉ đơn giản là nhờ việc chia nhỏ văn bản thành đoạn?"*

2. **Câu hỏi vặn về Vòng lặp tự chứng minh (Xoáy vào Mục 5.2 & 4.5):**
   > *"Trong Mục 5.2, kịch bản `generate_synthetic_dataset.py` của em dùng quy tắc để đổi số tiền, đổi ngày tháng và thay từ `'phải'` thành `'có thể'`. Sau đó ở Mục 4.5, module `change_classifier.py` lại dùng đúng bộ quy tắc và từ điển đó để bắt các thay đổi này. Em giải thích thế nào về tính khách quan của thực nghiệm khi dữ liệu kiểm thử và thuật toán giải được sinh ra từ cùng một bộ quy tắc?"*

3. **Câu hỏi vặn về Cấu trúc cây trong Thuật toán Hungarian (Xoáy vào Mục 1.2 & 4.3):**
   > *"Ở Chương 1 em phát biểu bài toán trên hai cây $T_{old} = (V_{old}, E_{old})$ và $T_{new} = (V_{new}, E_{new})$. Nhưng ở Mục 4.3, hàm mục tiêu của thuật toán Hungarian $\sum S(u_i, v_j)$ không hề chứa tập cạnh $E$ (quan hệ cha-con). Vậy nếu Khoản 3.1 của Điều 3 và Khoản 3.2 của Điều 3 ở bản cũ bị thuật toán Hungarian ghép lần lượt vào Điều 5 và Điều 9 ở bản mới chỉ vì có vài từ giống nhau, hệ thống của em xử lý sự phá vỡ cấu trúc phân cấp này như thế nào?"*

4. **Câu hỏi vặn về Độ phức tạp tính toán & Thời gian thực thi (Xoáy vào RQ4 & H3):**
   > *"Giả thuyết H3 của em nói rằng chia nhỏ văn bản ra từng điều khoản để chạy `SequenceMatcher` sẽ nhanh hơn hoặc tương đương chạy `SequenceMatcher` toàn văn. Nhưng để chia nhỏ và ghép cặp được, em phải chạy `pdfplumber` lấy tọa độ từng từ, chạy `sentence-transformers` (mô hình học sâu 12 lớp Transformer) cho hàng chục điều khoản, rồi giải bài toán Hungarian $O(K^3)$. Tổng thời gian thực tế của cả pipeline so với baseline tăng lên gấp bao nhiêu lần? Tại sao H3 lại chỉ tính thời gian của bước cuối cùng mà bỏ qua chi phí của các bước trước?"*

5. **Câu hỏi vặn về Thuật toán LIS và Phát hiện `MOVED` (Xoáy vào Mục 4.3 & 8.2):**
   > *"Giả sử hợp đồng có 10 điều khoản. Người soạn thảo chuyển một khối gồm 6 điều khoản ngắn từ cuối hợp đồng lên đầu hợp đồng, vượt qua 4 điều khoản dài. Thuật toán Dãy con tăng dài nhất (LIS) của em sẽ giữ cụm 6 điều khoản ngắn làm chuẩn (`RENUMBERED`) và báo rằng 4 điều khoản dài mới là các điều khoản bị `MOVED`. Điều này có hợp lý với tư duy của người đọc hợp đồng không?"*

6. **Câu hỏi vặn về Độ nhạy lỗi lan truyền (Error Propagation từ Tầng 2 sang Tầng 3–4):**
   > *"Hệ thống của em là một pipeline 6 tầng nối tiếp nhau. Nếu ở Tầng 2 (`contract_parser.py`), một lỗi định dạng PDF khiến hệ thống không nhận ra tiêu đề `Điều 6` mà gộp luôn toàn bộ nội dung của `Điều 6` vào cuối `Điều 5`, thì ở Tầng 3 (`clause_aligner.py`), ma trận tương đồng và kết quả ghép cặp sẽ bị ảnh hưởng như thế nào? Em có cơ chế tự phục hồi (error recovery) nào giữa Tầng 2 và Tầng 3 không?"*

7. **Câu hỏi vặn về Ngưỡng cứng (Magic Numbers) trong hệ thống:**
   > *"Trong kế hoạch của em xuất hiện rất nhiều con số cố định: vùng header/footer $8\%$, tần suất lặp $\ge 60\%$, trọng số $(0.25, 0.35, 0.30, 0.10)$, ngưỡng ghép cặp $\tau_{\text{high}} = 0.65, \tau_{\text{low}} = 0.40$, ngưỡng bao phủ tách/gộp $0.75$. Các con số này lấy từ cơ sở lý thuyết nào hay chỉ chọn cảm tính? Nếu tối ưu chúng trên tập dữ liệu của em (vốn chỉ có vài chục hợp đồng) thì làm sao tránh được hiện tượng học vẹt (overfitting)?"*

8. **Câu hỏi vặn về Bất biến Kiểm thử `Reconstruction` (Xoáy vào Mục 7.1 & `text_diff.py`):**
   > *"Trong Mục 7.1 em tuyên bố dùng thư viện `hypothesis` kiểm chứng tính chất: từ `old_text` và đầu ra của `diff_words` có thể tái tạo chính xác `new_text`. Nhưng hàm `tokenize_with_spans` của em dùng `r'\S+'` bỏ qua mọi khoảng trắng. Nếu `new_text` thay đổi dấu xuống dòng hoặc thêm khoảng trắng ở những vùng không có từ nào thay đổi (`tag == 'equal'`), làm sao em tái tạo lại chính xác `new_text` được?"*

---

## PHẦN 3: TOP 5 RỦI RO LỚN NHẤT CỦA ĐỒ ÁN

| Hạng | Tên Rủi ro | Mức độ Tác động | Khả năng Xảy ra | Phân tích Nguyên nhân & Hậu quả |
| :---: | :--- | :---: | :---: | :--- |
| **1** | **Sa lầy vào thu thập, ẩn danh hóa và gán nhãn dữ liệu (Data Bottleneck)** | **Chí mạng** | **Rất cao** | Hiện tại thư mục `data/` chưa tồn tại. Việc tìm 30–50 hợp đồng thực tế đa dạng bố cục, ẩn danh hóa PII, biên tập 15–20 cặp đàm phán nhiều vòng và gán nhãn chuẩn ở cả 3 mức (Segmentation, Alignment, Entity/Severity) cùng người thứ hai tính Cohen's Kappa có thể ngốn mất 5–6 tuần, làm tê liệt thời gian viết code và chạy thực nghiệm. |
| **2** | **Bác bỏ kết quả thực nghiệm do Vòng lặp tự chứng minh (Synthetic Evaluation Bias)** | **Chí mạng** | **Cao** | Nếu dùng chung quy tắc giữa `generate_synthetic_dataset.py` và `contract_parser.py` / `change_classifier.py`, hội đồng sẽ bác bỏ độ tin cậy của các con số $F_1 \ge 0.90 - 0.92$ trong Chương 4. |
| **3** | **Vỡ tiến độ ở Mốc 2 & Mốc 4 do xử lý PDF phức tạp (OCR tiếng Việt & Bảng biểu gộp ô)** | **Nghiêm trọng** | **Rất cao** | Xử lý PDF quét bằng OCR (`VietOCR`/`Tesseract`) và so sánh cấu trúc bảng biểu (`table_diff.py`) là hai bài toán cực kỳ tốn thời gian gỡ lỗi các ca biên (lỗi dấu tiếng Việt, mất tọa độ font, bảng vắt qua 2 trang, ô gộp ngang/dọc). Làm cả hai trong 2–3 tuần là bất khả thi cho 1 người. |
| **4** | **Lan truyền lỗi từ Bộ phân đoạn sang Bộ ghép cặp (Cascading Pipeline Failure)** | **Nghiêm trọng** | **Cao** | Khi gặp hợp đồng có cách đánh số không chuẩn (ví dụ dùng `1.`, `a.`, `-`, `+` lộn xộn hoặc thiếu số thứ tự), HFSM + Regex cứng sẽ dựng cây sai (gộp nhầm nhiều điều khoản hoặc tách nhầm số tiền/ngày tháng thành khoản mới), kéo theo điểm Alignment và Diff sụt giảm dây chuyền. |
| **5** | **Quá tải tài nguyên và độ trễ khi tích hợp mô hình Học sâu (`sentence-transformers` + `VietOCR`)** | **Quan trọng** | **Trung bình - Cao** | Tải đồng thời `vietnamese-bi-encoder` ($\sim 400 - 500\text{MB}$) và `VietOCR` lên CPU không chỉ làm chậm thời gian khởi động FastAPI và CI/CD (`pytest`), mà còn khiến thời gian xử lý 1 cặp hợp đồng dài vượt quá 15–30 giây, gây rủi ro treo khi Live Demo trước hội đồng. |

---

## PHẦN 4: NHỮNG GÌ NÊN CẮT KHỎI PHẠM VI (RECOMMENDED SCOPE CUTS)

Để đảm bảo 1 sinh viên có thể hoàn thành xuất sắc trong 16 tuần với chất lượng học thuật và kỹ thuật cao nhất, **khuyến nghị cắt bỏ dứt khoát 5 hạng mục sau khỏi phạm vi bắt buộc (chuyển sang Mục "Ngoài phạm vi" hoặc "Hướng phát triển tương lai"):**

1. **CẮT BỎ nhánh tích hợp OCR (`ocr_extractor.py`, `VietOCR` / `Tesseract`) cho PDF quét:**
   * *Lý do:* OCR văn bản hành chính/pháp lý tiếng Việt là một đề tài riêng biệt. Khi tài liệu là ảnh quét, các đặc trưng hình học của font chữ từ `pdfplumber` không còn tồn tại và lỗi nhận dạng ký tự của OCR sẽ làm nhiễu loạn toàn bộ đánh giá về thuật toán So sánh Cấu trúc (vốn là cốt lõi của đề tài).
   * *Cách xử lý thay thế:* Giữ lại cơ chế **Phát hiện trang quét/lỗi font** (`EMPTY_TEXT`, `NULL_CHARACTER`, `CID_FONT_ERROR`) trong `pdf_extractor.py` để tự động bật cờ `needs_review = True` kèm mã `ReviewReason.EMPTY_OR_SCANNED_PAGE` và dừng xử lý trang đó (Fail-safe Detection thay vì cố chạy OCR). Chỉ tốn 20 dòng code nhưng vẫn giữ trọn vẹn Kịch bản Demo 2!
2. **CẮT BỎ tập dữ liệu tiếng Anh (`CUAD`) và cấu hình đa ngôn ngữ Việt - Anh:**
   * *Lý do:* Hợp đồng Anh - Mỹ theo hệ thống Thông luật (Common Law) có cấu trúc câu và hệ thống đề mục (`WHEREAS`, `NOW, THEREFORE`, `Section`, `Exhibit`) hoàn toàn khác hợp đồng Việt Nam. Đưa `CUAD` (vốn là bộ dữ liệu gán nhãn thực thể trên **1 bản hợp đồng đơn lẻ**, không phải bộ dữ liệu gồm **cặp phiên bản cũ - mới** để diff!) vào Mục 5.1 là không đúng bản chất bài toán.
   * *Cách xử lý thay thế:* Tập trung **100% vào hợp đồng tiếng Việt**.
3. **CẮT BỎ thuật toán so sánh cấu trúc bảng biểu phức tạp theo khóa hàng/cột (`table_diff.py`):**
   * *Lý do:* Bảng biểu trong PDF không có cấu trúc DOM như HTML/Excel; việc căn chỉnh hàng/cột khi bảng bị ngắt qua trang hoặc có ô gộp (merged cells) sẽ ngốn hàng tuần lễ mà đóng góp vào câu hỏi nghiên cứu chính lại rất thấp.
   * *Cách xử lý thay thế:* Khi `pdfplumber` phát hiện vùng bảng (`find_tables()`), chỉ cần gom nội dung bảng thành một nút `TableNode` theo từng dòng chuẩn hóa ký tự phân cách `|` rồi chạy `diff_tokens_legal` trên từng dòng của bảng; nếu số dòng/cột thay đổi bất thường thì bật cờ `ReviewReason.COMPLEX_TABLE_STRUCTURE`.
4. **CẮT BỎ bài toán phân tích cú pháp chuyển đổi số tiền viết bằng chữ tiếng Việt sang số thực:**
   * *Lý do:* Ở Mục 4.5 ([dòng 354](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/docs/ke-hoach-trien-khai-do-an.md#L354)), việc viết parser đổi mọi biến thể chuỗi chữ tiếng Việt (*"một tỷ hai trăm linh năm triệu bốn trăm nghìn đồng chẵn"*) thành số thực để đối chiếu với số Ả Rập rất dễ phát sinh lỗi biên.
   * *Cách xử lý thay thế:* Chuẩn hóa giá trị số cho các cụm số Ả Rập có đơn vị (`100.000.000 VNĐ` == `100.000.000 đồng` == `100 triệu đồng`), còn với phần số tiền viết bằng chữ trong ngoặc đơn thì chỉ cần bắt sự kiện có chỉnh sửa từ vựng bên trong cụm tiền bằng chữ để gắn cờ `MONEY_CHANGE` / `CRITICAL_VALUE_MODIFIED`.
5. **THU GỌN mô hình biểu diễn ngữ nghĩa về chế độ nhẹ trên CPU làm mặc định:**
   * *Lý do:* Không bắt buộc tải mô hình học sâu nặng trong luồng CI/CD.
   * *Cách xử lý thay thế:* Thiết kế `SimilarityEngine` theo mẫu Strategy Pattern: mặc định dùng **Hybrid Word/Char n-gram TF-IDF + Title Levenshtein + BM25/SVD** (chạy dưới 50ms, không cần tải trọng số hàng trăm MB), và chỉ nạp `sentence-transformers` như một cấu hình tùy chọn trong thí nghiệm Ablation A3 để so sánh trong Chương 4.

---

## PHẦN 5: KẾT LUẬN VỀ TÍNH KHẢ THI (FEASIBILITY VERDICT)

### Kết luận của Hội đồng Phản biện: **KHẢ THI CÓ ĐIỀU KIỆN (Conditionally Feasible)**

* **Nếu giữ nguyên bản kế hoạch hiện tại:** **KHÔNG KHẢ THI (High Risk of Failure)** cho 1 sinh viên trong 16 tuần. Sinh viên sẽ bị quá tải ở khâu xử lý OCR, bảng biểu PDF và xây dựng dữ liệu đa nguồn, đồng thời có nguy cơ bị hội đồng phản biện bắt bẻ nặng nề về vòng lặp tự chứng minh trên tập dữ liệu tổng hợp (Synthetic Dataset) và sự vênh nhau giữa phát biểu bài toán cây với thuật toán Hungarian phẳng.
* **Nếu thực hiện 4 điều chỉnh cốt lõi sau đây, đề tài sẽ trở thành một Đồ án Tốt nghiệp XUẤT SẮC, hoàn toàn khả thi trong 16 tuần và bảo vệ rất vững chắc trước Hội đồng:**
  1. **Thu gọn phạm vi kỹ thuật:** Cắt bỏ OCR thực thi, cắt bỏ đa ngôn ngữ/CUAD, đơn giản hóa Table Diff về mức dòng, tập trung 100% vào hợp đồng tiếng Việt định dạng văn bản thuần và Digital-born PDF.
  2. **Sửa thuật toán Ghép cặp (Mục 4.3):** Chuyển từ Hungarian phẳng sang **Ghép cặp phân cấp 2 pha (Top-down Article-constrained Matching + Cross-Article Orphan Matching)** kết hợp ** chuẩn hóa trọng số thích nghi (khi không có `title`)** và **Weighted LIS** (ưu tiên khối văn bản lớn).
  3. **Sửa thiết kế Thực nghiệm (Mục 5.2 & 5.5):**
     * Bổ sung **Baseline trung gian (Paragraph-split + TF-IDF Alignment)** bên cạnh baseline `diff_words` phẳng hiện tại.
     * Bổ sung **Ablation A4** cho tầng thực thể pháp lý để trả lời trọn vẹn RQ3.
     * Tách bạch vai trò của Tập Synthetic (chỉ dùng đo độ nhạy Alignment/Move từ cây chuẩn do người duyệt) và Tập Bán thủ công (dùng đánh giá toàn diện End-to-End, đảm bảo mỗi lớp nhãn có tối thiểu $\ge 25$ mẫu).
  4. **Sửa lại Giả thuyết H3 & Bất biến Kiểm thử (Mục 1.4 & 7.1):** Phát biểu trung thực sự đánh đổi giữa thời gian chạy bước `SequenceMatcher` cục bộ và tổng độ trễ toàn pipeline; hiệu chỉnh lại bất biến `Reconstruction` (trên văn bản đã chuẩn hóa khoảng trắng) và `Symmetry` (định nghĩa đối xứng `SPLIT`/`MERGE`).

---

> **Gợi ý bước tiếp theo cho bạn:** Bạn đang sử dụng chế độ `/plan`. Nếu bạn đồng ý với các đề xuất phản biện và cắt giảm phạm vi ở trên, hãy cho tôi biết quyết định của bạn đối với 5 hạng mục cắt giảm (ở Phần 4) để tôi lập **Bản Kế hoạch Triển khai Kỹ thuật Đã Hiệu chỉnh (Implementation Plan Artifact)** và bắt đầu triển khai từng bước.
