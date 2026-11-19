# KẾ HOẠCH NGHIÊN CỨU VÀ TRIỂN KHAI ĐỒ ÁN TỐT NGHIỆP
**Đề tài:** Hệ thống so sánh phiên bản hợp đồng theo cấu trúc điều khoản (Structure-Aware Contract Version Comparison System)

---

## 1. Phát biểu Bài toán, Câu hỏi Nghiên cứu, Giả thuyết, Đóng góp và Phạm vi

### 1.1. Bối cảnh và Hiện trạng Codebase
Qua khảo sát mã nguồn hiện tại trong workspace (`weakfish`), hệ thống đang ở giai đoạn nguyên mẫu cơ bản (baseline sơ khai):
* **Trích xuất văn bản:** `[app/extractors/pdf_extractor.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/extractors/pdf_extractor.py#L1-L17)` sử dụng `pdfplumber` để lấy văn bản thô từng trang (`page.extract_text()`) và chỉ kiểm tra 2 cảnh báo cơ bản (`NULL_CHARACTER`, `EMPTY_TEXT`).
* **Hợp nhất và so sánh:** `[app/services/comparison_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/services/comparison_service.py#L13-L31)` nối toàn bộ văn bản các trang bằng `"\n\n"` rồi đưa thẳng vào hàm `diff_words` trong `[app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py#L14-L57)`.
* **Thuật toán hiện tại:** `diff_words` tách token theo khoảng trắng (`r"\S+"`) và chạy `difflib.SequenceMatcher(autojunk=False)` trên toàn bộ chuỗi văn bản phẳng của hai tài liệu.

**Hạn chế cốt lõi của hiện trạng (Motivation):**
1. **Mù cấu trúc (Structure-blindness):** Không nhận biết được phân cấp *Phần – Chương – Điều – Khoản – Điểm*, tiêu đề hay bảng biểu. Một thay đổi nhỏ hoặc việc đánh lại số thứ tự điều khoản làm lệch toàn bộ ngữ cảnh báo cáo.
2. **Không phát hiện được điều khoản bị di chuyển (Moved Clauses):** `SequenceMatcher` tìm dãy con chung dài nhất theo thứ tự tuyến tính. Nếu Điều 5 được chuyển xuống thành Điều 12, baseline sẽ báo *Xóa* toàn bộ Điều 5 ở vị trí cũ và *Thêm mới* ở vị trí mới, gây nhiễu nghiêm trọng cho người rà soát pháp lý.
3. **Nhiễu từ bố cục trang (Layout & Pagination Noise):** Header, footer, số trang, hoặc ngắt dòng khác nhau giữa hai bản xuất PDF sẽ tạo ra hàng loạt thay đổi giả (false positives).
4. **Thiếu ngữ nghĩa pháp lý và mức độ rủi ro:** Baseline coi việc sửa một dấu chấm câu ngang hàng với việc sửa giá trị hợp đồng từ `"100.000.000 VNĐ"` thành `"1.000.000.000 VNĐ"` hoặc đổi từ `"phải bồi thường"` thành `"không phải bồi thường"`.
5. **Thiếu kiểm thử và hạ tầng thực nghiệm:** `[requirements.txt](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/requirements.txt)` và `[README.md](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/README.md)` đang trống; `[tests/test_text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/tests/test_text_diff.py#L1-L12)` mới chỉ chứa hàm phụ trợ, chưa có ca kiểm thử (`test_*`) nào.

### 1.2. Phát biểu Bài toán Hình thức (Formal Problem Statement)
Cho hai tệp tài liệu hợp đồng đầu vào $D_{old}$ (phiên bản cũ) và $D_{new}$ (phiên bản mới) ở định dạng PDF hoặc văn bản thuần. Hệ thống cần thực hiện chuỗi ánh xạ sau:

1. **Phân đoạn cấu trúc (Structural Parsing):** Chuyển đổi $D_{old}$ và $D_{new}$ thành hai cây cấu trúc có thứ tự $T_{old} = (V_{old}, E_{old})$ và $T_{new} = (V_{new}, E_{new})$. Mỗi nút $u \in V$ đại diện cho một đơn vị cấu trúc (Tiêu đề hợp đồng, Phần, Chương, Điều, Khoản, Điểm, Đoạn văn, hoặc Bảng) với bộ thuộc tính:
   $$u = (\text{id}, \text{type}, \text{number\_label}, \text{title}, \text{text}, \text{table\_cells}, \text{page\_span}, \text{bbox})$$
2. **Ghép cặp điều khoản (Clause Alignment):** Tìm tập ánh xạ một-một (hoặc một-nhiều khi tách/gộp điều khoản) $\mathcal{M} \subseteq V_{old} \times V_{new}$ sao cho tổng độ tương đồng ngữ nghĩa và cấu trúc đạt cực đại, đồng thời xác định các tập nút không được ghép: tập bị xóa $V_{del} \subseteq V_{old}$ và tập được thêm mới $V_{ins} \subseteq V_{new}$.
3. **So sánh chi tiết và Phân loại thay đổi (Fine-grained Diff & Change Classification):** Với mỗi cặp nút đã ghép $(u, v) \in \mathcal{M}$:
   * Xác định trạng thái cấp điều khoản: `UNCHANGED` (giữ nguyên), `MODIFIED` (sửa nội dung), `MOVED` (giữ nguyên nội dung nhưng đổi vị trí/số hiệu), `MOVED_AND_MODIFIED` (vừa di chuyển vừa sửa), `RENUMBERED` (chỉ đổi số thứ tự do chèn/xóa phía trước).
   * Thực hiện diff mức từ/cụm từ bên trong $(u, v)$ và trích xuất các thay đổi trên thực thể quan trọng: số tiền (`MONEY`), ngày tháng/thời hạn (`DATE_DURATION`), tỷ lệ phần trăm (`PERCENTAGE`), chủ thể/bên tham gia (`PARTY`), và từ khóa nghĩa vụ/trách nhiệm (`MODAL_OBLIGATION`).
4. **Đánh giá mức độ quan trọng và Cờ rà soát (Severity Scoring & Review Flagging):** Gán nhãn mức độ quan trọng $s \in \{\text{LOW}, \text{MEDIUM}, \text{HIGH}, \text{CRITICAL}\}$ cho từng thay đổi dựa trên quy tắc kết hợp thực thể - loại điều khoản, và bật cờ `needs_review` (kèm mã lý do cụ thể) khi chất lượng trích xuất PDF/OCR thấp hoặc độ tự tin khi ghép cặp $(\text{confidence})$ nằm trong vùng nhập nhằng.

### 1.3. Câu hỏi Nghiên cứu (Research Questions - RQs)
* **RQ1 (Phân đoạn cấu trúc):** Làm thế nào để trích xuất chính xác cấu trúc phân cấp (*Điều/Khoản/Điểm*, tiêu đề, bảng biểu) và loại bỏ nhiễu bố cục (header/footer/số trang) từ tệp PDF hợp đồng khi định dạng trình bày không đồng nhất?
* **RQ2 (Ghép cặp điều khoản):** Phương pháp kết hợp độ đo tương đồng từ vựng - ngữ nghĩa với thuật toán tối ưu tổ hợp (như Hungarian / Quy hoạch động) cải thiện độ chính xác ghép cặp điều khoản (đặc biệt khi điều khoản bị đánh lại số thứ tự, di chuyển hoặc sửa đổi mạnh) như thế nào so với so sánh văn bản tuần tự?
* **RQ3 (Phân loại thay đổi và Mức độ quan trọng):** Việc bổ sung tầng nhận diện thực thể pháp lý (số tiền, ngày tháng, tỷ lệ, bên, từ khóa nghĩa vụ) giúp giảm tỷ lệ cảnh báo nhiễu (false alarms) và tăng khả năng phát hiện thay đổi trọng yếu (critical changes) ra sao?
* **RQ4 (Hiệu quả tổng thể & Đánh đổi hiệu năng):** So với baseline `difflib.SequenceMatcher` trên toàn văn bản hiện có, pipeline so sánh theo cấu trúc cải thiện bao nhiêu phần trăm về Precision/Recall/F1 trên tập dữ liệu kiểm thử và chi phí thời gian xử lý (latency) thay đổi như thế nào?

### 1.4. Giả thuyết Nghiên cứu (Hypotheses)
* **H1:** Bộ phân đoạn kết hợp biểu thức chính quy phân cấp (Hierarchical Regex), máy trạng thái hữu hạn (FSM) và đặc trưng hình học từ PDF (`bbox`, kích thước font, lề) đạt $F_1 \ge 0.90$ *(giả định mục tiêu thực nghiệm)* trong việc xác định ranh giới Điều/Khoản trên tập hợp đồng chuẩn.
* **H2:** Thuật toán Alignment hai giai đoạn (neo theo cấu trúc + tối ưu hóa ghép cặp toàn cục có ngưỡng) phát hiện được các điều khoản bị di chuyển (`MOVED`) và giảm ít nhất $50\%$ số lượng diff giả do lệch vị trí so với baseline `diff_words` toàn cục.
* **H3:** Độ phức tạp thời gian thực tế của việc chạy `SequenceMatcher` cục bộ trên từng cặp điều khoản đã ghép thấp hơn hoặc tương đương so với chạy `SequenceMatcher` một lần trên toàn bộ văn bản hợp đồng dài ($\ge 20$ trang), nhờ giảm kích thước đầu vào $N$ của từng lần gọi từ toàn văn xuống cấp độ điều khoản.

### 1.5. Đóng góp Khoa học và Thực tiễn
* **Đóng góp khoa học / học thuật:**
  1. Đề xuất kiến trúc pipeline phân tích và đối sánh hợp đồng theo cấu trúc cây phân cấp kết hợp ghép cặp toàn cục (Global Clause Alignment) và so sánh chi tiết cục bộ (Local Word/Entity Diff).
  2. Xây dựng bộ quy tắc và mô hình lai (Hybrid Lexical-Semantic Similarity) giải quyết bài toán điều khoản bị đánh lại số hiệu, di chuyển vị trí, hoặc tách/gộp trong hợp đồng tiếng Việt.
  3. Xây dựng quy trình tổng hợp dữ liệu có kiểm soát (Controlled Synthetic Perturbation Benchmark) và bộ dữ liệu có gán nhãn cho bài toán so sánh phiên bản hợp đồng tiếng Việt.
* **Đóng góp thực tiễn:**
  1. Nâng cấp trực tiếp hệ thống `ContractDiff` hiện có thành một dịch vụ API hoàn chỉnh, có khả năng xuất báo cáo Redline trực quan (JSON/HTML/Markdown), phân loại mức độ rủi ro và cảnh báo các vùng cần con người kiểm tra lại (`needs_review`).
  2. Cung cấp bộ công cụ kiểm thử tự động và quy trình tái lập thí nghiệm phục vụ kiểm toán/rà soát hợp đồng tại doanh nghiệp vừa và nhỏ.

### 1.6. Phạm vi (In-Scope) và Ngoài phạm vi (Out-of-Scope)
* **Trong phạm vi (In-Scope):**
  * Ngôn ngữ chính: Hợp đồng tiếng Việt (theo chuẩn thể thức văn bản/hợp đồng thương mại, lao động, dịch vụ tại Việt Nam). *(Giả định: Tập trung vào tiếng Việt làm trọng tâm; có thể mở rộng kiểm thử trên tiếng Anh nếu dùng thêm tập dữ liệu công khai quốc tế).*
  * Định dạng đầu vào: Văn bản thuần (Plain text) và PDF (bao gồm PDF xuất trực tiếp từ phần mềm soạn thảo - digital-born PDF, và tích hợp nhánh OCR dự phòng cho PDF quét cơ bản).
  * Cấu trúc nhận diện: Phần, Chương, Điều, Khoản, Điểm, đoạn mở đầu (Căn cứ/Chủ thể), và bảng biểu cơ bản.
  * Các loại thay đổi: Thêm (`ADDED`), Xóa (`DELETED`), Sửa (`MODIFIED`), Di chuyển (`MOVED`), Đổi số thứ tự (`RENUMBERED`), và thay đổi giá trị thực thể (`MONEY`, `DATE`, `PERCENTAGE`, `PARTY`, `OBLIGATION`).
* **Ngoài phạm vi (Out-of-Scope):**
  * Không tư vấn pháp lý tự động hoặc kết luận tính hợp pháp của hợp đồng theo bộ luật thực định.
  * Không xử lý chữ viết tay (handwritten annotations), con dấu đỏ đè nặng làm mất hoàn toàn chữ gốc, hoặc bảng biểu phức tạp bị xoay ngang/ghép ô đa tầng không theo lưới.
  * Không huấn luyện lại từ đầu (pre-train) các mô hình ngôn ngữ lớn (LLM); chỉ sử dụng các mô hình embedding/NLP sẵn có hoặc quy tắc xác định để đảm bảo tính minh bạch (explainability) và chạy được trên phần cứng tiêu chuẩn.

---

## 2. Khảo sát Tài liệu & Công cụ Đối sánh (Literature Review Plan)

Để tránh trích dẫn sai lệch, dưới đây là danh mục các công trình, thuật toán và công cụ **chắc chắn tồn tại** trong văn liệu khoa học, kèm theo các hướng tài liệu ghi rõ **"cần kiểm chứng"** khi sinh viên thực hiện tìm kiếm chi tiết.

### 2.1. Bốn Nhóm Chủ đề Cần Khảo sát

#### Nhóm 1: Thuật toán So sánh Văn bản và Cấu trúc Cây (Text & Tree Diffing)
* **Tài liệu & Công cụ chắc chắn tồn tại:**
  * **Myers (1986):** Eugene W. Myers, *"An O(ND) difference algorithm and its variations"*, Algorithmica (1986). Nền tảng của GNU `diff` và Git diff.
  * **Hunt & McIlroy (1976):** J. W. Hunt, M. D. McIlroy, *"An Algorithm for Differential File Comparison"*, Bell Telephone Laboratories. Bài toán dãy con chung dài nhất (LCS).
  * **Ratcliff / Obershelp (1988):** Thuật toán khớp mẫu Gestalt, nền tảng của `difflib.SequenceMatcher` trong thư viện chuẩn Python mà `[app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py)` đang sử dụng.
  * **Zhang & Shasha (1989):** Kaizhong Zhang, Dennis Shasha, *"Simple fast algorithms for the editing distance between trees and related problems"*, SIAM Journal on Computing. Thuật toán kinh điển tính khoảng cách chỉnh sửa cây (Tree Edit Distance).
  * **Chawathe et al. (1996):** Sudarshan S. Chawathe et al., *"Change detection in hierarchically structured information"*, ACM SIGMOD (1996). Đặc biệt quan trọng vì đề xuất các phép biến đổi `Insert`, `Delete`, `Update`, và **`Move`** trên dữ liệu có cấu trúc phân cấp (thuật toán *LaDiff*).
  * **Kuhn (1955) / Munkres (1957):** Thuật toán Hungarian giải bài toán phân công (Assignment Problem) trong thời gian đa thức $O(V^3)$, dùng để ghép cặp tối ưu các điều khoản giữa hai phiên bản.

#### Nhóm 2: Phân tích Bố cục Tài liệu & Trích xuất PDF (Document Layout Analysis)
* **Tài liệu & Công cụ chắc chắn tồn tại:**
  * **Công cụ trích xuất PDF mã nguồn mở:** `pdfplumber` (dựa trên `pdfminer.six`), `PyMuPDF` (`fitz`), `pypdf`/`pypdfium2`, `Docling` (IBM Research).
  * **Công cụ OCR:** `Tesseract OCR` (Google), `PaddleOCR` (Baidu), `VietOCR` (nhận dạng chữ tiếng Việt dựa trên Transformer/Seq2Seq của tác giả pbcquoc).
  * **Mô hình học sâu hiểu bố cục tài liệu:** `LayoutLM` (Xu et al., KDD 2020) và `LayoutLMv3` (Huang et al., ACM MM 2022) kết hợp văn bản, vị trí hình học (`bbox`) và hình ảnh trang tài liệu.

#### Nhóm 3: Xử lý Ngôn ngữ Tự nhiên trong Pháp lý (Legal NLP & Contract Analysis)
* **Tài liệu & Bộ dữ liệu chắc chắn tồn tại:**
  * **CUAD (Hendrycks et al., NeurIPS Datasets & Benchmarks 2021):** *"CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review"*. Bộ dữ liệu hơn 500 hợp đồng thương mại từ hệ thống EDGAR (Mỹ) với 41 loại điều khoản quan trọng.
  * **ContractNLI (Koreeda & Manning, EMNLP Findings 2021):** *"ContractNLI: A Dataset for Document-level Natural Language Inference for Contracts"*.
  * **LexGLUE (Chalkidis et al., ACL 2022):** *"LexGLUE: A Benchmark Dataset for Legal Language Understanding in English"*.
  * **LEGAL-BERT (Chalkidis et al., EMNLP Findings 2020):** Mô hình ngôn ngữ tiền huấn luyện cho miền pháp lý.
  * **NLP tiếng Việt:** `PhoBERT` (Dat Quoc Nguyen & Anh Tuan Nguyen, EMNLP Findings 2020), bộ công cụ `VnCoreNLP` (Vu et al., NAACL 2018), thư viện `underthesea`.
  * **Các bài báo cụ thể về so sánh phiên bản hợp đồng/văn bản quy phạm pháp luật tiếng Việt:** *(Cần kiểm chứng: Sinh viên cần tra cứu trên Google Scholar và kỷ yếu hội nghị RIVF, VLSP, KSE, NICS các bài báo cụ thể về phân đoạn văn bản pháp luật Việt Nam và so sánh văn bản quy phạm pháp luật để trích dẫn chính xác tên tác giả và năm xuất bản).*

#### Nhóm 4: Công cụ Redlining & So sánh Tài liệu Thực tế
* **Công cụ chắc chắn tồn tại:**
  * **Thương mại:** Microsoft Word (*Compare Documents*), Draftable Legal, Litera Compare (Workshare Compare), Adobe Acrobat Pro (*Compare Files*).
  * **Thư viện mã nguồn mở:** `google-diff-match-patch` (Neil Fraser), `xmldiff` (so sánh cấu trúc cây XML/HTML), `pdf-diff`.

### 2.2. Từ khóa Tìm kiếm Chuẩn hóa
* **Tiếng Anh:**
  * `"hierarchical document diff"` OR `"tree edit distance"` AND `"move detection"`
  * `"contract version comparison"` OR `"automated contract redlining"`
  * `"legal clause alignment"` OR `"paragraph alignment legal documents"`
  * `"contract segmentation"` OR `"legal document structure extraction"`
  * `"semantic change detection in contracts"`
* **Tiếng Việt:**
  * `"phân đoạn văn bản pháp luật"` OR `"trích xuất cấu trúc hợp đồng"`
  * `"so sánh văn bản tiếng Việt"` OR `"đối sánh điều khoản hợp đồng"`

### 2.3. Cách Ghi nhận Khoảng trống Nghiên cứu (Research Gap Matrix)
Sinh viên cần lập bảng so sánh các hướng tiếp cận hiện có theo 6 tiêu chí để làm nổi bật khoảng trống nghiên cứu trong Chương 1 & Chương 2 của khóa luận:

| Phương pháp / Công cụ | Nhận biết phân cấp Điều/Khoản | Phát hiện điều khoản di chuyển (`MOVE`) | Xử lý nhiễu Header/Footer PDF | Phân loại thực thể & rủi ro hợp đồng | Hỗ trợ đặc thù hợp đồng tiếng Việt | Minh bạch / Không phụ thuộc Black-box LLM |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Baseline hiện tại (`difflib` phẳng) | Không | Không | Không | Không | Cơ bản (tách khoảng trắng) | Có |
| Công cụ Diff văn bản (`diff-match-patch`, Git diff) | Không | Không | Không | Không | Cơ bản | Có |
| Tree Diff thuần túy (`Zhang-Shasha`, `xmldiff`) | Có (yêu cầu cây chuẩn trước) | Hạn chế (trừ họ `LaDiff`) | Không | Không | Không tích hợp sẵn | Có |
| Công cụ thương mại (MS Word Compare, Draftable) | Một phần (ưu tiên `.docx`) | Có (tùy công cụ) | Một phần | Không chấm điểm rủi ro ngữ nghĩa | Không tối ưu cấu trúc Điều/Khoản VN | Đóng (Proprietary) |
| Dùng LLM trực tiếp (Prompting GPT/Claude toàn văn) | Có | Có | Có | Có | Khá tốt | **Không** (Hallucination, chi phí cao, giới hạn ngữ cảnh, rủi ro bảo mật dữ liệu) |
| **Hệ thống đề xuất (Đồ án này)** | **Có** | **Có** | **Có** | **Có** | **Có (Thiết kế chuyên biệt)** | **Có (Kiểm soát được hoàn toàn)** |

---

## 3. Kiến trúc Hệ thống Đề xuất từ Hiện trạng Code

### 3.1. Luồng Dữ liệu Tổng thể (Pipeline 6 Tầng)

```mermaid
flowchart TD
    subgraph Tầng 1: Ingestion & Pre-processing
        A1["Tệp PDF / Text Cũ & Mới"] --> A2["PDF Extractor (pdfplumber + BBox/Table)"]
        A2 --> A3{"Trang rỗng / Lỗi Font?"}
        A3 -- "Có" --> A4["OCR Fallback (VietOCR / Tesseract)"]
        A3 -- "Không" --> A5["Layout Cleaner (Khử Header/Footer/Số trang)"]
        A4 --> A5
    end

    subgraph Tầng 2: Structural Segmentation
        A5 --> B1["Parser Phân cấp (FSM + Regex Điều/Khoản/Điểm)"]
        B1 --> B2["Cây Cấu trúc Hợp đồng T_old & T_new"]
    end

    subgraph Tầng 3: Clause Alignment
        B2 --> C1["Stage 1: Exact / Anchor Match (Số hiệu + Tiêu đề)"]
        C1 --> C2["Stage 2: Ma trận Tương đồng Lai (TF-IDF + Embedding)"]
        C2 --> C3["Stage 3: Tối ưu hóa Ghép cặp (Hungarian + Ngưỡng τ)"]
        C3 --> C4["Danh sách Cặp Ghép (Matched, Moved, Added, Deleted)"]
    end

    subgraph Tầng 4: Intra-clause & Table Diff
        C4 --> D1["Word/Phrase Diff (SequenceMatcher mở rộng)"]
        C4 --> D2["Table Cell Diff (So sánh theo Hàng/Cột)"]
        D1 --> D3["Trích xuất Thực thể Thay đổi (Số tiền, Ngày, Tỷ lệ, Bên, Nghĩa vụ)"]
        D2 --> D3
    end

    subgraph Tầng 5: Classification, Risk & Review Flagging
        D3 --> E1["Phân loại Thay đổi & Gán Mức độ Quan trọng (Severity)"]
        E1 --> E2["Bộ Đánh giá Độ tin cậy & Cờ Rà soát (needs_review)"]
    end

    subgraph Tầng 6: API & Report Exporter
        E2 --> F1["JSON Response (Pydantic Schema)"]
        E2 --> F2["Báo cáo Redline HTML / Markdown / PDF"]
    end
```

### 3.2. Thiết kế Module Mở rộng từ Codebase Hiện tại

Giữ nguyên khả năng tương thích ngược của các endpoint hiện tại trong `[app/api/routes/comparisons.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/api/routes/comparisons.py)` để phục vụ thí nghiệm đối sánh với Baseline, đồng thời tổ chức lại các tầng kỹ thuật như sau:

* **`app/extractors/`**
  * `[app/extractors/pdf_extractor.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/extractors/pdf_extractor.py)` *(Nâng cấp)*: Bổ sung trích xuất dòng kèm tọa độ hình học (`extract_words`, `extract_tables`), thông tin kích thước font (`size`, `fontname`), và phát hiện đầy đủ các mã cảnh báo chất lượng.
  * `app/extractors/ocr_extractor.py` *(Mới)*: Xử lý các trang bị cảnh báo `EMPTY_TEXT` hoặc `GARBLED_FONT` bằng `pypdfium2` (render ảnh) + `Tesseract`/`VietOCR`.
  * `app/extractors/layout_cleaner.py` *(Mới)*: Thuật toán phát hiện và loại bỏ Header/Footer lặp lại giữa các trang và chuẩn hóa bảng mã Unicode tiếng Việt (NFC).
* **`app/parsers/`** *(Mới)*
  * `app/parsers/contract_parser.py`: Bộ phân tích cú pháp chuyển văn bản đã làm sạch thành cây cấu trúc `ContractTree` gồm các nút `ClauseNode` (Phần, Chương, Điều, Khoản, Điểm) và `TableNode`.
  * `app/parsers/entity_extractor.py`: Bộ nhận diện thực thể hợp đồng (Số tiền, Ngày tháng, Tỷ lệ %, Thời hạn, Tên bên A/B, Từ khóa nghĩa vụ/chế tài).
* **`app/engines/`**
  * `[app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py)` *(Giữ hàm `diff_words` cũ làm baseline, bổ sung `diff_tokens_legal`)*: Cải tiến bộ tách từ nhận biết dấu câu và đơn vị tiền tệ/ngày tháng.
  * `app/engines/clause_aligner.py` *(Mới)*: Cài đặt thuật toán ghép cặp điều khoản giữa $T_{old}$ và $T_{new}$ (Exact Anchor + Hybrid Similarity + Hungarian Algorithm).
  * `app/engines/table_diff.py` *(Mới)*: So sánh cấu trúc bảng biểu theo khóa hàng (row key) và cột (column header).
  * `app/engines/change_classifier.py` *(Mới)*: Phân loại thay đổi ngữ nghĩa, chấm điểm mức độ quan trọng (`Severity`) và tổng hợp cờ `needs_review`.
* **`app/exporters/`** *(Mới)*
  * `app/exporters/report_exporter.py`: Xuất kết quả so sánh ra định dạng HTML Redline (hỗ trợ xem song song Side-by-Side) và Markdown.
* **`app/schemas/`**
  * Nâng cấp `[app/schemas/document.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/schemas/document.py)` và `[app/schemas/comparison.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/schemas/comparison.py)` với hệ thống kiểu tường minh (`Enum`).

### 3.3. Thiết kế Schema Dữ liệu (Pydantic Models)

```python
from enum import Enum
from pydantic import BaseModel, Field

class NodeType(str, Enum):
    PREAMBLE = "PREAMBLE"       # Quốc hiệu, tiêu ngữ, căn cứ, thông tin các bên
    PART = "PART"               # Phần (Phần I, Phần II...)
    CHAPTER = "CHAPTER"         # Chương (Chương I, Chương II...)
    ARTICLE = "ARTICLE"         # Điều (Điều 1, Điều 2...)
    CLAUSE = "CLAUSE"           # Khoản (1.1, 1., Khoản 1...)
    POINT = "POINT"             # Điểm (a), b), 1.1.1...)
    PARAGRAPH = "PARAGRAPH"     # Đoạn văn bản không đánh số
    TABLE = "TABLE"             # Bảng biểu
    SIGNATURE = "SIGNATURE"     # Khối chữ ký đại diện các bên

class ChangeCategory(str, Enum):
    UNCHANGED = "UNCHANGED"
    ADDED = "ADDED"
    DELETED = "DELETED"
    MODIFIED = "MODIFIED"
    MOVED = "MOVED"
    MOVED_AND_MODIFIED = "MOVED_AND_MODIFIED"
    RENUMBERED = "RENUMBERED"

class SemanticChangeType(str, Enum):
    MONEY_CHANGE = "MONEY_CHANGE"               # Thay đổi số tiền, giá trị thanh toán
    DATE_DURATION_CHANGE = "DATE_DURATION_CHANGE" # Thay đổi ngày tháng, thời hạn
    PERCENTAGE_CHANGE = "PERCENTAGE_CHANGE"     # Thay đổi tỷ lệ %, lãi suất, phạt
    PARTY_CHANGE = "PARTY_CHANGE"               # Thay đổi thông tin chủ thể/bên
    OBLIGATION_CHANGE = "OBLIGATION_CHANGE"     # Đổi từ khóa nghĩa vụ (phải/có quyền/không...)
    TEXT_EDIT = "TEXT_EDIT"                     # Chỉnh sửa diễn đạt thông thường
    FORMATTING_ONLY = "FORMATTING_ONLY"         # Chỉ thay đổi dấu câu/khoảng trắng/số thứ tự

class SeverityLevel(str, Enum):
    LOW = "LOW"           # Sửa chính tả, định dạng, đánh lại số thứ tự
    MEDIUM = "MEDIUM"     # Sửa câu chữ không chứa thực thể định lượng hoặc từ khóa chế tài
    HIGH = "HIGH"         # Thêm/xóa điều khoản phụ, sửa nghĩa vụ hoặc thời hạn
    CRITICAL = "CRITICAL" # Sửa số tiền, tỷ lệ phạt/lãi, chủ thể, hoặc xóa điều khoản cốt lõi

class ReviewReason(str, Enum):
    OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
    EMPTY_OR_SCANNED_PAGE = "EMPTY_OR_SCANNED_PAGE"
    GARBLED_TEXT_ENCODING = "GARBLED_TEXT_ENCODING"
    AMBIGUOUS_CLAUSE_ALIGNMENT = "AMBIGUOUS_CLAUSE_ALIGNMENT"
    COMPLEX_TABLE_STRUCTURE = "COMPLEX_TABLE_STRUCTURE"
    CRITICAL_VALUE_MODIFIED = "CRITICAL_VALUE_MODIFIED"

class BoundingBox(BaseModel):
    page: int
    x0: float
    top: float
    x1: float
    bottom: float

class StructuralNode(BaseModel):
    node_id: str
    node_type: NodeType
    parent_id: str | None = None
    number_label: str | None = None      # VD: "Điều 5", "5.1", "a)"
    title: str | None = None             # VD: "Phương thức thanh toán"
    normalized_title: str | None = None  # VD: "phuong thuc thanh toan"
    content: str                         # Nội dung văn bản của nút
    full_path: str                       # VD: "Điều 5 > Khoản 5.1 > Điểm a"
    page_numbers: list[int] = Field(default_factory=list)
    bbox: BoundingBox | None = None

class EntityDelta(BaseModel):
    entity_type: SemanticChangeType
    old_value: str | None = None
    new_value: str | None = None
    normalized_old: str | None = None
    normalized_new: str | None = None

class AlignedClauseDiff(BaseModel):
    alignment_id: str
    category: ChangeCategory
    similarity_score: float = Field(ge=0.0, le=1.0)
    old_node: StructuralNode | None = None
    new_node: StructuralNode | None = None
    word_changes: list[dict] = Field(default_factory=list)
    entity_deltas: list[EntityDelta] = Field(default_factory=list)
    semantic_types: list[SemanticChangeType] = Field(default_factory=list)
    severity: SeverityLevel = SeverityLevel.LOW
    needs_review: bool = False
    review_reasons: list[ReviewReason] = Field(default_factory=list)
```

### 3.4. Lựa chọn Công nghệ và Phân tích Đánh đổi (Trade-offs)

| Thành phần | Lựa chọn Đề xuất | Phương án Đã cân nhắc | Lý do lựa chọn & Đánh đổi |
| :--- | :--- | :--- | :--- |
| **Trích xuất PDF** | `pdfplumber` kết hợp `pypdfium2` | `PyMuPDF` (`fitz`), `Docling` | Codebase hiện tại đã dùng `pdfplumber` (rất mạnh về tọa độ ký tự và trích xuất bảng). `PyMuPDF` nhanh hơn nhưng giấy phép AGPLv3 có thể gây vướng mắc khi thương mại hóa; `pdfplumber` dùng giấy phép MIT. |
| **OCR Dự phòng** | `Tesseract OCR` (`vie`) + tùy chọn `VietOCR` | Google Cloud Vision API, AWS Textract | Tránh phụ thuộc API trả phí và đảm bảo dữ liệu hợp đồng nhạy cảm không rời khỏi máy chủ nội bộ (On-premise privacy). |
| **Phân đoạn Cấu trúc** | Máy trạng thái hữu hạn (FSM) + Regex phân cấp + Đặc trưng Font/BBox | Fine-tune mô hình Sequence Labeling (BiLSTM-CRF / PhoBERT) | Cấu trúc hợp đồng tuân theo quy ước văn bản hành chính/pháp lý rất chặt chẽ. FSM + Regex + BBox minh bạch 100%, không cần hàng ngàn mẫu gán nhãn để huấn luyện, dễ debug. |
| **Biểu diễn Ngữ nghĩa (Alignment)** | Hybrid: TF-IDF / Char n-gram + `sentence-transformers` đa ngữ (`paraphrase-multilingual-MiniLM-L12-v2` hoặc `bkai-foundation-models/vietnamese-bi-encoder`) | Chỉ dùng TF-IDF hoặc gọi OpenAI Embedding API | Kết hợp TF-IDF (bắt chính xác thuật ngữ chuyên ngành/số liệu) và Dense Embedding (bắt tương đồng khi viết lại câu) chạy hoàn toàn trên CPU với tốc độ cao. |
| **Thuật toán Ghép cặp** | Hungarian Algorithm (`scipy.optimize.linear_sum_assignment`) kết hợp Blocking theo cấp độ | Quy hoạch động (Dynamic Programming / Needleman-Wunsch), Greedy Matching | DP giả định thứ tự đơn điệu nên **không bắt được điều khoản bị hoán đổi vị trí (`MOVE`)**. Greedy dễ mắc cực trị địa phương. Hungarian giải tối ưu toàn cục trong $O(K^3)$ với $K$ là số điều khoản ($K \approx 20 - 150$, chạy mất $< 5\text{ms}$). |

---

## 4. Thiết kế Thuật toán Chi tiết

### 4.1. Tiền xử lý, Làm sạch Bố cục và Xử lý PDF Quét (OCR & Extraction Errors)
1. **Chuẩn hóa bảng mã tiếng Việt:** Văn bản trích xuất từ PDF tiếng Việt thường bị lỗi tổ hợp dấu (NFD vs NFC) hoặc bảng mã TCVN3/VNI cũ. Áp dụng `unicodedata.normalize("NFC", text)` và bộ phát hiện tỷ lệ ký tự lạ (ngoài bảng chữ cái Latin/Tiếng Việt và dấu câu chuẩn).
2. **Khử Header, Footer và Số trang tự động:**
   * Với tài liệu có $P \ge 3$ trang, thu thập các dòng văn bản nằm trong vùng $8\%$ đỉnh trang (`top < 0.08 * page_height`) và $8\%$ đáy trang (`bottom > 0.92 * page_height`).
   * Chuẩn hóa chuỗi (thay thế chữ số bằng ký hiệu `<NUM>`, ví dụ `"Trang 1 / 12"` $\rightarrow$ `"Trang <NUM> / <NUM>"`).
   * Nếu một mẫu dòng xuất hiện trên $\ge 60\%$ số trang, đánh dấu là `HEADER`/`FOOTER` và loại bỏ khỏi luồng văn bản điều khoản.
3. **Phát hiện lỗi trích xuất và kích hoạt OCR:**
   * Mở rộng danh sách `warnings` trong `[app/extractors/pdf_extractor.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/extractors/pdf_extractor.py#L7-L11)`:
     * `EMPTY_TEXT`: Mật độ ký tự $< 20$ ký tự/trang.
     * `NULL_CHARACTER` / `CID_FONT_ERROR`: Xuất hiện chuỗi `(cid:xx)` hoặc ký tự `\x00`, `\ufffd` vượt ngưỡng $2\%$.
     * `BROKEN_VIETNAMESE_DIACRITICS`: Dấu thanh điệu bị tách rời thành ký tự độc lập do lỗi font PDF.
   * Khi gặp các cảnh báo trên, hệ thống tự động chuyển trang đó sang nhánh `ocr_extractor.py`, đồng thời gắn cờ `ReviewReason.OCR_LOW_CONFIDENCE` nếu độ tin cậy trung bình của từ OCR $< 0.85$.

### 4.2. Phân đoạn Cấu trúc Hợp đồng (Hierarchical Structural Segmentation)
Sử dụng **Máy trạng thái hữu hạn phân cấp (Hierarchical Finite State Machine - HFSM)** duyệt qua từng dòng văn bản đã gắn kèm đặc trưng hình học:
* **Bộ mẫu nhận diện đầu mục (Heading Patterns):**
  * Cấp `PART` / `CHAPTER`: `^(PHẦN|CHƯƠNG)\s+([IVXLCDM]+|\d+)[\.:\-\s]*(.*)$`
  * Cấp `ARTICLE` (Điều): `^(ĐIỀU|Điều|ARTICLE|Article)\s+(\d+)[\.:\-\s]*(.*)$`
  * Cấp `CLAUSE` (Khoản): `^(\d+\.\d+|\d+)[\.\)]\s+(.*)$` hoặc `^(Khoản)\s+(\d+)[\.:\-\s]*(.*)$`
  * Cấp `POINT` (Điểm): `^([a-zđ]\)|\d+\.\d+\.\d+)\s+(.*)$`
* **Khử nhập nhằng (Disambiguation Rules):**
  * Tránh nhầm số tiền/ngày tháng ở đầu dòng (ví dụ `"100.000.000 đồng..."` hoặc `"15/08/2026..."`) thành số thứ tự Khoản bằng điều kiện: nhãn số hiệu Khoản $k$ phải có giá trị hợp lý ($1 \le k \le 100$) và liên tục hoặc tăng dần so với nút anh em liền trước ($k = k_{prev} + 1$), hoặc có tọa độ lề trái (`x0`) thẳng hàng với các Khoản cùng cấp.
* **Trích xuất Bảng biểu:**
  * Sử dụng `page.find_tables()` của `pdfplumber` để lấy bounding box của các bảng.
  * Loại bỏ các từ nằm trong bounding box của bảng khỏi luồng văn bản thường (tránh lặp nội dung), và tạo một nút `TableNode` gắn làm con của `ClauseNode`/`ArticleNode` chứa nó ngay phía trên.

### 4.3. Thuật toán Ghép cặp Điều khoản (Clause Alignment)
Cho tập các nút cấp Điều (hoặc Khoản) của bản cũ $U = \{u_1, u_2, \dots, u_m\}$ và bản mới $V = \{v_1, v_2, \dots, v_n\}$. Quá trình ghép cặp gồm 3 bước:

#### Bước 1: Tính Ma trận Tương đồng Đa đặc trưng $S \in [0, 1]^{m \times n}$
Với mỗi cặp $(u_i, v_j)$, điểm tương đồng tổng hợp $S(u_i, v_j)$ được tính bởi:
$$S(u_i, v_j) = w_{\text{title}} \cdot \text{Sim}_{\text{title}}(u_i, v_j) + w_{\text{lex}} \cdot \text{Sim}_{\text{lex}}(u_i, v_j) + w_{\text{sem}} \cdot \text{Sim}_{\text{sem}}(u_i, v_j) + w_{\text{pos}} \cdot \text{Sim}_{\text{pos}}(u_i, v_j)$$
Trong đó *(trọng số khởi tạo giả định: $w_{\text{title}}=0.25, w_{\text{lex}}=0.35, w_{\text{sem}}=0.30, w_{\text{pos}}=0.10$, sẽ được tinh chỉnh trên tập Validation)*:
* $\text{Sim}_{\text{title}}(u_i, v_j)$: Độ tương đồng chuẩn hóa giữa tiêu đề điều khoản (kết hợp Token Jaccard và tỷ lệ Levenshtein trên tiêu đề đã bỏ tiền tố `"Điều X"`).
* $\text{Sim}_{\text{lex}}(u_i, v_j)$: Độ tương đồng Cosine trên vector TF-IDF của word $n$-gram ($n \in \{1, 2\}$) và character $n$-gram ($n \in \{3, 4\}$).
* $\text{Sim}_{\text{sem}}(u_i, v_j)$: Độ tương đồng Cosine giữa hai vector embedding ngữ nghĩa của nội dung điều khoản. *(Ở chế độ nhẹ không dùng GPU/mô hình lớn, có thể fallback về LSA/SVD hoặc BM25).*
* $\text{Sim}_{\text{pos}}(u_i, v_j) = 1 - \left|\frac{i}{m} - \frac{j}{n}\right|$: Ưu tiên nhẹ cho các điều khoản có vị trí tương đối gần nhau khi nội dung tương đương.

#### Bước 2: Giải Bài toán Phân công Toàn cục và Lọc Ngưỡng
* Áp dụng thuật toán Hungarian (`linear_sum_assignment(-S)`) để tìm bộ ghép cặp một-một $\mathcal{M}_0$ cực đại hóa $\sum_{(i, j) \in \mathcal{M}_0} S(u_i, v_j)$.
* **Cắt ngưỡng (Thresholding):** Với mỗi cặp $(u_i, v_j) \in \mathcal{M}_0$:
  * Nếu $S(u_i, v_j) \ge \tau_{\text{high}}$ (giả định $\tau_{\text{high}} = 0.65$): Chấp nhận ghép cặp chính thức.
  * Nếu $\tau_{\text{low}} \le S(u_i, v_j) < \tau_{\text{high}}$ (giả định $\tau_{\text{low}} = 0.40$): Chấp nhận ghép cặp nhưng bật cờ `ReviewReason.AMBIGUOUS_CLAUSE_ALIGNMENT`.
  * Nếu $S(u_i, v_j) < \tau_{\text{low}}$: Hủy ghép cặp; đưa $u_i$ vào tập ứng viên bị xóa $U_{\text{unmatched}}$ và $v_j$ vào tập ứng viên mới $V_{\text{unmatched}}$.

#### Bước 3: Phát hiện Tách/Gộp (Split/Merge) và Di chuyển (`MOVED` vs `RENUMBERED`)
* **Kiểm tra Tách/Gộp (1-to-N / N-to-1):** Với mỗi nút $u_i \in U_{\text{unmatched}}$, kiểm tra xem nội dung của $u_i$ có được bao phủ bởi hợp của 2 nút liên tiếp $v_{j}, v_{j+1}$ hay không dựa trên độ bao phủ tập token (Token Containment Ratio $\ge 0.75$).
* **Phân biệt `MOVED` và `RENUMBERED`:**
  * Xét dãy chỉ số của các cặp đã ghép $(i_1, j_1), (i_2, j_2), \dots, (i_k, j_k)$ với $i_1 < i_2 < \dots < i_k$.
  * Tìm **Dãy con tăng dài nhất (Longest Increasing Subsequence - LIS)** trên chuỗi chỉ số mới $(j_1, j_2, \dots, j_k)$.
  * Các cặp thuộc LIS giữ nguyên thứ tự tương đối: nếu số hiệu điều khoản thay đổi (ví dụ `"Điều 5"` $\rightarrow$ `"Điều 6"` do chèn thêm 1 điều ở trên) nhưng nội dung giống nhau $\rightarrow$ gán nhãn `RENUMBERED`.
  * Các cặp **không thuộc LIS** (bị đảo thứ tự tương đối so với các điều khoản khác, ví dụ chuyển từ đầu hợp đồng xuống cuối hợp đồng) $\rightarrow$ gán nhãn `MOVED` (hoặc `MOVED_AND_MODIFIED` nếu nội dung có chỉnh sửa).

### 4.4. So sánh Chi tiết Mức Từ bên trong Điều khoản (Intra-clause Fine-grained Diff)
Thay vì tách từ bằng `r"\S+"` như `[app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py#L6)` hiện tại (khiến `"100.000.000đ."` dính liền cả chữ và dấu chấm), bộ tách token mới `tokenize_legal_spans(text)` sẽ:
1. Giữ nguyên các cụm số tiền, ngày tháng, tỷ lệ phần trăm và số hiệu điều khoản (ví dụ `15/08/2026`, `100.000.000`, `12,5%`) thành một token nguyên tử (atomic token).
2. Tách riêng các dấu câu (`,`, `.`, `;`, `:`, `(`, `)`) thành các token độc lập để khi chỉ thêm dấu phẩy, hệ thống không báo thay đổi cả từ đứng trước.
3. Chạy `SequenceMatcher` cục bộ trên cặp điều khoản $(u_i, v_j)$ và thực hiện bước **Coalescing (Gom cụm)**: nếu hai vùng thay đổi (`replace`/`insert`/`delete`) chỉ cách nhau bởi 1 khoảng trắng hoặc 1 từ nối ngắn ($\le 2$ ký tự), gộp chúng thành một cụm thay đổi duy nhất để người đọc dễ theo dõi.

### 4.5. Phân loại Thay đổi, Nhận diện Thực thể & Đánh giá Mức độ Quan trọng
Trên các đoạn `old_fragment` và `new_fragment` của mỗi thay đổi, chạy bộ trích xuất thực thể biểu thức chính quy kết hợp từ điển pháp lý:
1. **`MONEY_CHANGE`:** Bắt các mẫu số đi kèm đơn vị tiền tệ (`VNĐ`, `VND`, `đồng`, `USD`, `tỷ`, `triệu`, `nghìn`) và cụm số tiền viết bằng chữ (`"một trăm triệu đồng"`). Chuẩn hóa về giá trị số thực để so sánh (ví dụ `"100.000.000 VNĐ"` và `"100.000.000 đồng"` có cùng giá trị số $\rightarrow$ chỉ là `TEXT_EDIT`, không phải `MONEY_CHANGE`).
2. **`DATE_DURATION_CHANGE`:** Bắt mẫu ngày (`dd/mm/yyyy`, `ngày ... tháng ... năm ...`) và thời hạn (`30 ngày`, `06 tháng`, `02 năm`, `ngày làm việc`).
3. **`PERCENTAGE_CHANGE`:** Bắt mẫu `\d+([\.,]\d+)?\s*(%|phần trăm)/?(năm|tháng|ngày)?`.
4. **`OBLIGATION_CHANGE`:** Kiểm tra sự thay đổi trong từ điển từ khóa tình thái pháp lý (Legal Modality Lexicon):
   * Nhóm bắt buộc: `{"phải", "bắt buộc", "cam kết", "chịu trách nhiệm", "nghĩa vụ"}`
   * Nhóm cho phép/tùy nghi: `{"có thể", "được quyền", "có quyền", "tùy thuộc"}`
   * Nhóm phủ định/miễn trừ: `{"không", "không phải", "miễn trừ", "loại trừ"}`
   * Nếu một phép sửa làm đổi nhóm tình thái (ví dụ thêm/xóa từ `"không"` trước `"chịu trách nhiệm"`, hoặc đổi `"phải"` $\rightarrow$ `"có thể"`), gắn nhãn `OBLIGATION_CHANGE` với mức độ `CRITICAL`.

**Quy tắc gán mức độ quan trọng (`SeverityLevel`):**
* **`CRITICAL`:** Có `MONEY_CHANGE` (thay đổi giá trị số), `PERCENTAGE_CHANGE`, `PARTY_CHANGE`, `OBLIGATION_CHANGE` đảo chiều phủ định, hoặc `DELETED`/`ADDED` toàn bộ một Điều liên quan đến *Thanh toán, Phạt vi phạm, Bồi thường thiệt hại, Chấm dứt hợp đồng, Bảo mật*.
* **`HIGH`:** Có `DATE_DURATION_CHANGE`, `ADDED`/`DELETED` một Khoản/Điểm có chứa nghĩa vụ, hoặc `MOVED_AND_MODIFIED`.
* **`MEDIUM`:** `MODIFIED` câu chữ thông thường (`TEXT_EDIT`) hoặc `MOVED` nguyên vẹn điều khoản.
* **`LOW`:** `FORMATTING_ONLY` hoặc `RENUMBERED` đơn thuần.

---

## 5. Dữ liệu và Phương pháp Đánh giá (Dataset & Evaluation)

### 5.1. Nguồn Dữ liệu Hợp đồng Công khai & Vấn đề Pháp lý / Bảo mật
> **Lưu ý về Bản quyền và Quyền riêng tư (Privacy & Copyright):** Hợp đồng thực tế của doanh nghiệp thường chứa bí mật kinh doanh và dữ liệu cá nhân (PII: CCCD, số tài khoản, địa chỉ, họ tên). Đồ án **tuyệt đối không** thu thập trái phép hợp đồng nội bộ chưa được phép công bố.

**3 Nguồn dữ liệu hợp pháp sử dụng cho đồ án:**
1. **Nguồn 1 – Mẫu hợp đồng chuẩn ban hành kèm Văn bản Quy phạm Pháp luật Việt Nam (Public Domain):**
   * Các mẫu hợp đồng mua bán hàng hóa, hợp đồng dịch vụ, hợp đồng xây dựng, hợp đồng lao động, hợp đồng thuê nhà... được ban hành công khai trong phụ lục của các Nghị định, Thông tư (Bộ Tư pháp, Bộ Xây dựng, Bộ Lao động - Thương binh và Xã hội, Bộ Công Thương).
2. **Nguồn 2 – Hợp đồng mẫu công khai từ các cổng thông tin pháp lý / trường đại học:**
   * Thu thập khoảng 30–50 mẫu hợp đồng tiếng Việt đa dạng lĩnh vực, thực hiện **Ẩn danh hóa (PII Anonymization)**: thay thế toàn bộ tên công ty thật, mã số thuế, số tài khoản, tên cá nhân bằng thực thể giả lập chuẩn hóa (`Công ty TNHH Thương mại Sao Mai`, `MST: 0101234567`, v.v.).
3. **Nguồn 3 – Tập dữ liệu học thuật quốc tế (phục vụ kiểm thử khả năng tổng quát hóa đa ngôn ngữ nếu cần):**
   * Tập dữ liệu **CUAD** (Hendrycks et al., 2021 - giấy phép CC BY 4.0) từ hệ thống báo cáo công khai SEC EDGAR của Hoa Kỳ.

### 5.2. Quy trình Tạo Cặp Phiên bản Có Nhãn (Controlled Synthetic + Semi-Real Revisions)
Do các cặp phiên bản đàm phán hợp đồng thực tế $(D_{old}, D_{new})$ rất hiếm khi được công khai kèm nhãn chuẩn (ground-truth), đồ án thiết kế quy trình tạo dữ liệu kiểm thử gồm 2 tập:

1. **Tập Benchmark Tổng hợp có Kiểm soát (Controlled Synthetic Dataset - dự kiến 100 cặp hợp đồng):**
   * Viết kịch bản Python (`scripts/generate_synthetic_dataset.py`) áp dụng các toán tử biến đổi ngẫu nhiên có kiểm soát lên các hợp đồng gốc đã được phân tích cấu trúc chuẩn. Vì chính kịch bản tạo ra thay đổi nên **nhãn Ground-Truth đạt độ chính xác 100% tự động**:
     * *Toán tử cấp cấu trúc:* Chèn điều khoản mới (`INSERT_CLAUSE`), xóa điều khoản (`DELETE_CLAUSE`), hoán đổi vị trí 2 điều khoản (`MOVE_CLAUSE` + tự động đánh lại số thứ tự các điều khoản ở giữa), tách 1 khoản dài thành 2 khoản (`SPLIT_CLAUSE`).
     * *Toán tử cấp thực thể & ngữ nghĩa:* Thay đổi số tiền ($\pm 10\%, \times 10$), đổi ngày giao hàng/thời hạn thanh toán ($30 \text{ ngày} \rightarrow 45 \text{ ngày}$), đổi lãi suất phạt ($0.05\%/\text{ngày} \rightarrow 0.02\%/\text{ngày}$), đảo từ khóa nghĩa vụ (`"Bên B phải"` $\rightarrow$ `"Bên B có thể"`).
     * *Toán tử nhiễu định dạng PDF:* Xuất ra 2 bản PDF với lề trang khác nhau, chèn Header/Footer khác nhau để đổi vị trí ngắt trang.
2. **Tập Kiểm thử Thực tế Bán thủ công (Human-Curated Revision Dataset - dự kiến 15–20 cặp hợp đồng):**
   * Mô phỏng kịch bản đàm phán thực tế giữa Bên Mua và Bên Bán qua 2–3 vòng chỉnh sửa (Redline thực tế trên Word rồi xuất ra PDF, bao gồm cả 5 cặp PDF quét/ảnh chụp để test nhánh OCR).

### 5.3. Quy trình Gán nhãn (Annotation Protocol)
* Với tập 15–20 cặp biên tập bán thủ công, xây dựng tài liệu hướng dẫn gán nhãn (`Annotation Guideline`) quy định rõ:
  1. Cách xác định ranh giới Điều/Khoản/Điểm.
  2. Cách nối cặp `(old_node_id, new_node_id)` và gán nhãn `ChangeCategory`.
  3. Cách đánh dấu các `EntityDelta` và `SeverityLevel`.
* **Kiểm tra độ đồng thuận (Inter-Annotator Agreement):** Nhờ 1 sinh viên/cộng tác viên thứ hai gán nhãn độc lập trên một mẫu con (ví dụ 5 cặp hợp đồng, khoảng 150 điều khoản) và tính hệ số **Cohen's Kappa ($\kappa$)**. Mục tiêu $\kappa \ge 0.80$ để chứng minh tính khách quan của bộ dữ liệu đánh giá.

### 5.4. Hệ thống Độ đo Đánh giá (Evaluation Metrics)
1. **Đánh giá Phân đoạn Cấu trúc (Segmentation Metrics):**
   * $\text{Precision}_{\text{seg}}, \text{Recall}_{\text{seg}}, F_{1,\text{seg}}$ trên ranh giới bắt đầu/kết thúc và nhãn cấp độ (`ARTICLE`, `CLAUSE`, `POINT`, `TABLE`) của từng nút.
2. **Đánh giá Ghép cặp Điều khoản (Alignment Metrics):**
   * **Alignment Precision ($P_{\text{align}}$):** Tỷ lệ cặp điều khoản hệ thống ghép đúng trên tổng số cặp hệ thống dự đoán.
   * **Alignment Recall ($R_{\text{align}}$):** Tỷ lệ cặp điều khoản hệ thống ghép đúng trên tổng số cặp thực tế trong Ground-Truth.
   * **Alignment $F_1$ ($F_{1,\text{align}}$)** và **Move Detection $F_1$ ($F_{1,\text{move}}$)** (đánh giá riêng khả năng bắt điều khoản bị di chuyển).
3. **Đánh giá Phân loại Thay đổi & Nhận diện Thực thể:**
   * **Macro-$F_1$ và Micro-$F_1$** theo 7 nhãn `ChangeCategory` và theo 7 nhãn `SemanticChangeType`.
   * **Critical Recall ($R_{\text{critical}}$):** Tỷ lệ phát hiện đúng các thay đổi mức `CRITICAL` (độ đo quan trọng nhất trong bài toán pháp lý vì bỏ sót thay đổi số tiền/nghĩa vụ nguy hiểm hơn báo dư).
4. **Đánh giá Hiệu năng (Performance Metrics):**
   * Thời gian xử lý trung bình (ms/trang và giây/tài liệu) phân rã theo từng pha (Extraction, Segmentation, Alignment, Diff) trên các độ dài hợp đồng: Ngắn ($1-5$ trang), Trung bình ($6-15$ trang), Dài ($16-50$ trang).

### 5.5. Thiết kế Thí nghiệm: Baseline, Ablation Study & Phân tích Lỗi
* **Thí nghiệm 1 (So sánh với Baseline hiện tại):**
  * Đối sánh trực tiếp hệ thống đề xuất với `diff_words` hiện có trong `[app/engines/text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/engines/text_diff.py)` về: (1) Tổng số khối thay đổi báo cáo (chứng minh giảm nhiễu khi có điều khoản di chuyển hoặc khác header/footer), (2) Khả năng định vị chính xác điều khoản bị sửa, và (3) Thời gian thực thi khi văn bản dài.
* **Thí nghiệm 2 (Ablation Study - Nghiên cứu loại bỏ thành phần):**
  * *Biến thể A1 (Không có Layout Cleaner):* Tắt bộ lọc Header/Footer để đo mức độ sụt giảm Precision.
  * *Biến thể A2 (Alignment tuần tự vs. Hungarian):* Thay thuật toán Hungarian bằng Greedy Matching hoặc Quy hoạch động (DP) để đo mức sụt giảm $F_{1,\text{move}}$.
  * *Biến thể A3 (Chỉ dùng Lexical vs. Hybrid Lexical + Semantic):* Tắt vector embedding ngữ nghĩa, chỉ giữ TF-IDF + Title similarity để đánh giá đóng góp của embedding khi điều khoản bị diễn đạt lại (paraphrased) và đánh đổi tốc độ.
* **Phân tích lỗi (Error Analysis):**
  * Thống kê ma trận nhầm lẫn (Confusion Matrix) của các lớp thay đổi; phân tích các ca thất bại điển hình (ví dụ: bảng biểu bị ngắt qua 2 trang, điều khoản đánh số La Mã lẫn số Ả Rập, lỗi OCR nhận diện nhầm số `0` thành chữ `O` hoặc số `1` thành chữ `l`).

### 5.6. Các Mối đe dọa tới Tính hợp lệ (Threats to Validity)
1. **Tính hợp lệ nội tại (Internal Validity):** Dữ liệu tổng hợp (Synthetic data) có thể tuân theo các quy luật biến đổi quá "sạch" so với cách con người sửa hợp đồng thực tế. *Cách giảm thiểu:* Bổ sung tập kiểm thử biên tập bán thủ công và chèn nhiễu bố cục/OCR thực tế.
2. **Tính hợp lệ ngoại tại (External Validity):** Quy tắc phân đoạn Điều/Khoản tiếng Việt có thể không áp dụng nguyên trạng cho hợp đồng tiếng Anh (vốn dùng cấu trúc `Section 1.1`, `WHEREAS`, `NOW, THEREFORE`). *Cách giảm thiểu:* Thiết kế các mẫu Regex/FSM theo kiến trúc cấu hình đa ngôn ngữ (Language Profile Config).
3. **Tính hợp lệ cấu trúc (Construct Validity):** Việc gán nhãn mức độ quan trọng (`SeverityLevel`) phụ thuộc vào ngữ cảnh giao dịch thực tế. *Cách giảm thiểu:* Nêu rõ trong báo cáo rằng `SeverityLevel` là gợi ý ưu tiên rà soát dựa trên thực thể và từ khóa pháp lý, không thay thế phán quyết của luật sư.

---

## 6. Lộ trình Triển khai 16 Tuần (1 Người Thực hiện)

> **Giả định lập kế hoạch:**
> * Thời gian thực hiện: **16 tuần** (1 học kỳ đồ án tốt nghiệp tiêu chuẩn).
> * Nhân sự: **01 sinh viên** làm việc trung bình **20–25 giờ/tuần**.
> * Hạ tầng: Máy tính cá nhân (CPU đa nhân, RAM $\ge 16\text{GB}$, không bắt buộc GPU rời cho luồng chính).

| Giai đoạn / Tuần | Mục tiêu & Công việc Chính | Đầu ra Cụ thể (Deliverables) | Tiêu chí Hoàn thành (DoD) | Rủi ro & Kế hoạch Dự phòng (Fallback) |
| :--- | :--- | :--- | :--- | :--- |
| **Mốc 1: Khởi tạo, Chuẩn hóa Baseline & Khảo sát**<br>*(Tuần 1 – Tuần 2)* | - Khóa phiên bản thư viện trong `[requirements.txt](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/requirements.txt)`.<br>- Viết bộ unit test đầy đủ cho baseline hiện có.<br>- Thu thập 30 mẫu hợp đồng gốc công khai & hoàn thành khảo sát tài liệu. | - File `requirements.txt`, `pyproject.toml`, GitHub Actions CI.<br>- Test coverage cho baseline $\ge 90\%$.<br>- Bản nháp Chương 1 & Chương 2 báo cáo. | `pytest` chạy xanh 100%; có 30 file hợp đồng mẫu đã ẩn danh hóa PII trong `data/raw/`. | *Rủi ro:* Khó tìm hợp đồng PDF đa dạng bố cục.<br>*Dự phòng:* Chuyển đổi các mẫu hợp đồng `.docx` từ Thông tư/Nghị định sang PDF với nhiều template font/lề khác nhau. |
| **Mốc 2: Trích xuất PDF Nâng cao, Làm sạch Bố cục & Phân đoạn Cấu trúc**<br>*(Tuần 3 – Tuần 5)* | - Nâng cấp `pdf_extractor.py` lấy tọa độ, font, bảng.<br>- Xây dựng `layout_cleaner.py` khử header/footer.<br>- Xây dựng `contract_parser.py` (FSM + Regex tách Phần/Chương/Điều/Khoản/Điểm).<br>- Tích hợp nhánh OCR dự phòng. | - Module `extractors/` và `parsers/` hoàn chỉnh.<br>- Endpoint `/api/v1/documents/parse` trả về cây cấu trúc JSON.<br>- Bộ test phân đoạn cấu trúc. | Đạt $F_{1,\text{seg}} \ge 0.90$ trên 20 hợp đồng mẫu chuẩn; khử đúng header/footer lặp lại. | *Rủi ro:* OCR tiếng Việt (`VietOCR`) chạy chậm trên CPU.<br>*Dự phòng:* Mặc định dùng `Tesseract (vie)` cho luồng nhanh và chỉ chạy OCR trên những trang có cờ `EMPTY_TEXT`. |
| **Mốc 3: Thuật toán Ghép cặp Điều khoản (Clause Alignment)**<br>*(Tuần 6 – Tuần 8)* | - Xây dựng bộ tính độ tương đồng lai (Title + TF-IDF + Embedding).<br>- Cài đặt thuật toán Hungarian + ngưỡng cắt + LIS phát hiện `MOVED` vs `RENUMBERED` và `SPLIT`/`MERGE`. | - Module `app/engines/clause_aligner.py`.<br>- Kịch bản sinh dữ liệu tổng hợp `generate_synthetic_dataset.py` (100 cặp). | Đạt $F_{1,\text{align}} \ge 0.92$ và $F_{1,\text{move}} \ge 0.85$ trên tập Synthetic Benchmark. | *Rủi ro:* Model `sentence-transformers` làm tăng RAM và thời gian khởi động API.<br>*Dự phòng:* Tải model dạng lazy-loading singleton hoặc dùng TF-IDF char/word n-gram + SVD làm chế độ mặc định nhẹ. |
| **Mốc 4: Diff Mức Từ, Bảng biểu, Phân loại Thực thể & Mức độ Rủi ro**<br>*(Tuần 9 – Tuần 10)* | - Nâng cấp `text_diff.py` tách token pháp lý & gom cụm.<br>- Xây dựng `table_diff.py` cho bảng biểu.<br>- Xây dựng `entity_extractor.py` và `change_classifier.py` (Số tiền, Ngày, Tỷ lệ, Nghĩa vụ, `Severity`, `needs_review`). | - Hoàn thiện toàn bộ tầng Engine.<br>- Cập nhật `schemas/comparison.py` và `services/comparison_service.py`. | Phát hiện đúng $\ge 90\%$ các thay đổi thực thể số tiền/ngày tháng/tỷ lệ trên tập kiểm thử. | *Rủi ro:* Bảng phức tạp bị gộp ô (merged cells) gây lệch cột.<br>*Dự phòng:* Nếu số cột giữa 2 bảng không khớp hoặc độ tự tin thấp, fallback về so sánh văn bản từng dòng trong bảng và bật cờ `COMPLEX_TABLE_STRUCTURE`. |
| **Mốc 5: Xuất Báo cáo, Giao diện Demo & Thực nghiệm Đánh giá**<br>*(Tuần 11 – Tuần 13)* | - Xây dựng `report_exporter.py` xuất HTML Redline (Side-by-Side) & Markdown.<br>- Xây dựng giao diện Web nhẹ (FastAPI Jinja2/HTMX hoặc Streamlit) để Demo.<br>- Chạy toàn bộ thí nghiệm Baseline, Ablation Study, đo thời gian chạy. | - Giao diện Demo trực quan.<br>- Thư mục `experiments/` chứa script chạy thực nghiệm và bảng số liệu/biểu đồ tự động xuất ra CSV/LaTeX. | Toàn bộ số liệu RQ1–RQ4 được tạo tự động bằng 1 lệnh chạy script duy nhất. | *Rủi ro:* Không kịp làm frontend phức tạp bằng React/Vue.<br>*Dự phòng:* Dùng HTML template tĩnh kết hợp TailwindCSS/HTMX render trực tiếp từ FastAPI hoặc Streamlit — gọn nhẹ, vẫn đảm bảo tính năng highlight & điều hướng điều khoản. |
| **Mốc 6: Hoàn thiện Khóa luận, Kiểm thử Hồi quy & Chuẩn bị Bảo vệ**<br>*(Tuần 14 – Tuần 16)* | - Viết hoàn chỉnh Chương 3, 4, 5 của báo cáo.<br>- Rà soát toàn bộ test suite, tài liệu hóa `README.md`.<br>- Chuẩn bị slide thuyết trình và kịch bản live demo. | - Quyển báo cáo Đồ án tốt nghiệp hoàn chỉnh.<br>- Slide bảo vệ & Video quay sẵn màn hình demo dự phòng. | Báo cáo được giảng viên hướng dẫn duyệt; repo sạch, CI xanh, hoàn thành chạy thử bảo vệ. | *Rủi ro:* Phát sinh lỗi bất ngờ khi demo trực tiếp.<br>*Dự phòng:* Chuẩn bị sẵn 3 cặp file PDF mẫu đa kịch bản và video backup chất lượng cao. |

---

## 7. Chiến lược Kiểm thử, CI/CD, Cấu trúc Repo và Tái lập Thí nghiệm

### 7.1. Chiến lược Kiểm thử Đa tầng (Testing Strategy)
Hiện tại các file trong `tests/` gần như trống. Hệ thống cần xây dựng chiến lược kiểm thử 4 lớp với `pytest` và `hypothesis`:

1. **Unit Tests (`tests/unit/`):**
   * Kiểm thử từng hàm độc lập: chuẩn hóa văn bản, tách token pháp lý (`tokenize_legal_spans`), trích xuất số tiền/ngày tháng/tỷ lệ, phân tích tiêu đề `Điều/Khoản/Điểm`, tính điểm tương đồng, và thuật toán Hungarian trên ma trận nhỏ.
2. **Property-Based Testing (`tests/property/` sử dụng thư viện `hypothesis`):**
   * Kiểm chứng các **tính chất bất biến toán học (Invariants)** với dữ liệu sinh ngẫu nhiên:
     * *Tính phản xạ (Identity):* Với mọi văn bản hợp đồng $D$, `compare(D, D)` phải trả về `is_identical = True`, mọi điều khoản đều `UNCHANGED` với `similarity_score == 1.0`, và `changes == []`.
     * *Tính đối xứng nghịch đảo (Symmetry):* Nếu `compare(A, B)` gán nhãn một nút là `ADDED` thì khi gọi `compare(B, A)`, nút tương ứng phải mang nhãn `DELETED`; số lượng điều khoản `MOVED` giữa `compare(A, B)` và `compare(B, A)` phải bằng nhau.
     * *Tính bảo toàn văn bản (Reconstruction):* Từ chuỗi `old_text` và danh sách opcodes/spans của `diff_words`, áp dụng các phép biến đổi phải tái tạo chính xác `new_text`.
3. **Regression Tests với Golden Dataset (`tests/regression/`):**
   * Lưu trữ 10 cặp hợp đồng tiêu biểu kèm file kết quả đầu ra chuẩn (`golden_output.json`). Mỗi khi sửa đổi biểu thức chính quy hoặc trọng số alignment, bộ test hồi quy đảm bảo không làm hỏng các ca đã chạy đúng trước đó.
4. **API & Integration Tests (`tests/integration/`):**
   * Sử dụng `fastapi.testclient.TestClient` kiểm thử toàn bộ các endpoint (`/api/v1/documents/extract`, `/api/v1/comparisons/text`, `/api/v1/comparisons/pdf`, và endpoint mới `/api/v1/comparisons/structured`), bao gồm cả các ca biên (file rỗng, file không phải PDF, văn bản chỉ chứa khoảng trắng).

### 7.2. Cấu trúc Repository Mục tiêu

```text
weakfish/
├── .github/
│   └── workflows/
│       └── ci.yml                  # Chạy ruff, mypy, pytest tự động mỗi khi push/PR
├── app/
│   ├── main.py                     # Khởi tạo FastAPI app
│   ├── core/
│   │   └── config.py               # Cấu hình ngưỡng (tau_high, tau_low, weights, OCR config)
│   ├── api/
│   │   ├── router.py
│   │   └── routes/
│   │       ├── health.py           # Endpoint kiểm tra trạng thái hệ thống (/health)
│   │       ├── documents.py        # Trích xuất & phân tích cấu trúc tài liệu
│   │       └── comparisons.py      # So sánh văn bản & PDF (Baseline + Structure-aware)
│   ├── extractors/
│   │   ├── pdf_extractor.py        # Trích xuất văn bản, bbox, font, bảng bằng pdfplumber
│   │   ├── ocr_extractor.py        # Nhánh OCR dự phòng cho trang quét
│   │   └── layout_cleaner.py       # Khử Header/Footer/Số trang & chuẩn hóa Unicode
│   ├── parsers/
│   │   ├── contract_parser.py      # HFSM + Regex tách Phần/Chương/Điều/Khoản/Điểm
│   │   └── entity_extractor.py     # Nhận diện Tiền, Ngày, Tỷ lệ, Bên, Từ khóa nghĩa vụ
│   ├── engines/
│   │   ├── text_diff.py            # Baseline diff_words & diff_tokens_legal nâng cấp
│   │   ├── clause_aligner.py       # Ghép cặp điều khoản (Hybrid Similarity + Hungarian)
│   │   ├── table_diff.py           # So sánh bảng biểu theo cấu trúc hàng/cột
│   │   └── change_classifier.py    # Phân loại thay đổi, gán Severity & cờ needs_review
│   ├── exporters/
│   │   └── report_exporter.py      # Xuất báo cáo HTML Redline & Markdown
│   ├── schemas/
│   │   ├── document.py
│   │   └── comparison.py
│   └── services/
│       ├── document_service.py
│       └── comparison_service.py
├── data/
│   ├── raw_templates/              # Hợp đồng mẫu công khai đã ẩn danh hóa
│   ├── synthetic_benchmark/        # Các cặp hợp đồng sinh tự động kèm ground_truth.json
│   └── curated_test_set/           # Các cặp hợp đồng biên tập bán thủ công
├── experiments/
│   ├── configs/                    # File YAML cấu hình tham số thí nghiệm
│   ├── generate_dataset.py         # Script sinh dữ liệu có kiểm soát (cố định random seed)
│   ├── run_evaluation.py           # Script chạy đối sánh Baseline vs Proposed & Ablation
│   └── results/                    # Bảng kết quả CSV, Markdown, biểu đồ phục vụ khóa luận
├── tests/
│   ├── conftest.py                 # Pytest fixtures dùng chung
│   ├── test_text_diff.py
│   ├── test_comparison_service.py
│   ├── test_comparison_api.py
│   ├── test_contract_parser.py
│   ├── test_clause_aligner.py
│   └── test_properties.py          # Property-based tests với Hypothesis
├── requirements.txt                # Danh sách thư viện ghim phiên bản cố định
└── README.md                       # Tài liệu hướng dẫn cài đặt, chạy API và tái lập thí nghiệm
```

### 7.3. Đảm bảo Khả năng Tái lập Thí nghiệm (Reproducibility)
* **Ghim phiên bản phụ thuộc (Pinned Dependencies):** Mọi gói trong `[requirements.txt](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/requirements.txt)` đều được ghim phiên bản chính xác (ví dụ `pdfplumber==0.11.4`, `scipy==1.14.1`, `fastapi==0.115.0`).
* **Cố định hạt giống ngẫu nhiên (Deterministic Seeding):** Mọi script sinh dữ liệu tổng hợp và chia tập dữ liệu đều nhận tham số `--seed 42`.
* **Tách biệt cấu hình:** Toàn bộ trọng số $(w_{\text{title}}, w_{\text{lex}}, w_{\text{sem}}, w_{\text{pos}})$ và ngưỡng $(\tau_{\text{low}}, \tau_{\text{high}})$ được lưu trong file cấu hình YAML để một lệnh `python experiments/run_evaluation.py --config experiments/configs/ablation.yaml` có thể tái tạo toàn bộ bảng biểu trong khóa luận.

---

## 8. Cấu trúc Báo cáo Đồ án và Kế hoạch Bảo vệ / Demo

### 8.1. Đề cương Chi tiết Báo cáo Đồ án Tốt nghiệp (5 Chương)

* **Chương 1: Tổng quan về Đề tài (Introduction)**
  * 1.1. Đặt vấn đề và nhu cầu thực tiễn trong rà soát phiên bản hợp đồng.
  * 1.2. Hạn chế của các phương pháp so sánh văn bản truyền thống (Word-level Diff).
  * 1.3. Phát biểu bài toán, câu hỏi nghiên cứu và giả thuyết nghiên cứu.
  * 1.4. Mục tiêu, phạm vi nghiên cứu và những đóng góp chính của đồ án.
  * 1.5. Bố cục của khóa luận.
* **Chương 2: Cơ sở Lý thuyết và Các Nghiên cứu Liên quan (Background & Related Work)**
  * 2.1. Đặc trưng cấu trúc văn bản pháp lý và hợp đồng tại Việt Nam.
  * 2.2. Các thuật toán so sánh văn bản và cấu trúc cây (LCS, Myers, Ratcliff/Obershelp, Tree Edit Distance, LaDiff).
  * 2.3. Kỹ thuật trích xuất bố cục tài liệu PDF và nhận dạng ký tự quang học (OCR).
  * 2.4. Biểu diễn tương đồng văn bản và bài toán ghép cặp tối ưu (TF-IDF, Sentence Embeddings, Thuật toán Hungarian).
  * 2.5. Tổng hợp các nghiên cứu, công cụ liên quan và xác định khoảng trống nghiên cứu.
* **Chương 3: Phương pháp Đề xuất và Thiết kế Hệ thống (Proposed Methodology & System Architecture)**
  * 3.1. Kiến trúc tổng thể của hệ thống `ContractDiff` mở rộng.
  * 3.2. Tiền xử lý tài liệu PDF, khử nhiễu bố cục và cơ chế cảnh báo lỗi trích xuất.
  * 3.3. Thuật toán phân đoạn cấu trúc hợp đồng phân cấp (Phần – Chương – Điều – Khoản – Điểm & Bảng biểu).
  * 3.4. Thuật toán ghép cặp điều khoản đa đặc trưng kết hợp tối ưu hóa Hungarian và phát hiện điều khoản di chuyển.
  * 3.5. So sánh chi tiết mức từ, trích xuất thực thể pháp lý và đánh giá mức độ rủi ro / cờ rà soát thủ công.
* **Chương 4: Thực nghiệm và Đánh giá (Experiments & Evaluation)**
  * 4.1. Xây dựng bộ dữ liệu thực nghiệm (Nguồn dữ liệu, quy trình tổng hợp thay đổi có kiểm soát, gán nhãn và hệ số đồng thuận $\kappa$).
  * 4.2. Thiết lập môi trường thực nghiệm và các độ đo đánh giá.
  * 4.3. Kết quả đánh giá phân đoạn cấu trúc (Trả lời RQ1).
  * 4.4. Kết quả đánh giá ghép cặp điều khoản và phát hiện di chuyển (Trả lời RQ2).
  * 4.5. Kết quả phân loại thay đổi ngữ nghĩa, so sánh với Baseline và Ablation Study (Trả lời RQ3 & RQ4).
  * 4.6. Phân tích lỗi (Error Analysis) và các mối đe dọa tới tính hợp lệ.
* **Chương 5: Kết luận và Hướng Phát triển (Conclusion & Future Work)**
  * 5.1. Tổng kết các kết quả đạt được so với mục tiêu ban đầu.
  * 5.2. Hạn chế hiện tại của hệ thống.
  * 5.3. Hướng phát triển tiếp theo (tích hợp LLM cục bộ để giải thích rủi ro pháp lý, xử lý bảng đa trang phức tạp, hỗ trợ song ngữ Việt - Anh).

### 8.2. Kế hoạch Bảo vệ và Kịch bản Live Demo (10–12 Phút)
Để thuyết phục Hội đồng chấm đồ án trong thời gian ngắn, phần Demo cần tập trung vào **sự tương phản rõ rệt giữa Baseline và Hệ thống Đề xuất**:
1. **Kịch bản Demo 1 (Tình huống Đàm phán Thực tế - 3 phút):**
   * Tải lên 2 bản PDF Hợp đồng Dịch vụ Phần mềm (Bản dự thảo v1 và Bản đối tác sửa v2). Trong bản v2:
     * *Điều 4 (Phương thức thanh toán)* và *Điều 7 (Trách nhiệm bảo mật)* bị đảo vị trí cho nhau.
     * Trong điều khoản thanh toán, thời hạn `"15 ngày làm việc"` bị sửa thành `"45 ngày"` và lãi phạt chậm trả giảm từ `"0.05%/ngày"` xuống `"0.01%/ngày"`.
     * Một từ `"Bên B phải bồi thường"` bị sửa nhẹ thành `"Bên B có thể bồi thường"`.
   * **Bật chế độ xem đối chiếu (Toggle Baseline vs. Structure-Aware):**
     * *Màn hình Baseline (`diff_words` cũ):* Đỏ rực toàn bộ từ Điều 4 đến Điều 7 do lệch vị trí, không phân biệt được đâu là sửa số tiền, đâu là đổi chỗ điều khoản.
     * *Màn hình Hệ thống mới:* Hiển thị rõ danh sách điều khoản bên trái, gắn nhãn `MOVED` cho Điều 7, highlight chính xác 3 thay đổi mức `CRITICAL` (Thời hạn, Tỷ lệ phạt, Nghĩa vụ bồi thường) ở bảng tóm tắt rủi ro đầu trang.
2. **Kịch bản Demo 2 (Kiểm soát Chất lượng & Cờ `needs_review` - 2 phút):**
   * Tải lên 1 bản PDF có 1 trang bị quét mờ hoặc lỗi font. Hệ thống tự động gắn cờ `needs_review = True` kèm lý do `EMPTY_OR_SCANNED_PAGE` / `AMBIGUOUS_CLAUSE_ALIGNMENT` và điều hướng người dùng tới đúng trang/điều khoản cần kiểm tra bằng mắt.

---

## 9. Danh sách Việc Cần Làm Đầu tiên (Immediate Action Items) & Các Quyết định Mở

### 9.1. Danh sách 8 Việc Cần Làm Ngay (Tuần 1)
Bạn có thể bắt đầu thực hiện ngay theo đúng thứ tự sau:

1. **Khởi tạo `[requirements.txt](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/requirements.txt)` và môi trường ảo:**
   * Thêm các thư viện cốt lõi: `fastapi`, `uvicorn[standard]`, `python-multipart`, `pydantic`, `pdfplumber`, `scipy`, `scikit-learn`, `pytest`, `httpx`, `hypothesis`.
2. **Hoàn thiện endpoint kiểm tra sức khỏe hệ thống:**
   * Viết code cho `[app/api/routes/health.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/api/routes/health.py)` (hiện đang trống) và gắn vào `[app/api/router.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/api/router.py#L1-L16)`.
3. **Sửa lỗi tiềm ẩn trong `[app/api/routes/comparisons.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/app/api/routes/comparisons.py#L13-L20)`:**
   * Bổ sung giá trị mặc định cho `old_file.filename or "old.pdf"` và `new_file.filename or "new.pdf"`, đồng thời kiểm tra định dạng tệp tải lên.
4. **Viết bộ Unit Test & API Test hoàn chỉnh cho Baseline hiện tại:**
   * Bổ sung các hàm `test_*` thực sự vào `[tests/test_text_diff.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/tests/test_text_diff.py)`, `[tests/test_comparison_service.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/tests/test_comparison_service.py)`, và `[tests/test_comparison_api.py](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/tests/test_comparison_api.py)` để khóa hành vi của baseline trước khi mở rộng.
5. **Tạo bộ dữ liệu mẫu nhỏ (Mini Seed Dataset - 5 cặp hợp đồng):**
   * Lưu 5 mẫu hợp đồng tiếng Việt dạng text và PDF vào `data/sample/` để dùng ngay cho việc phát triển bộ tách cấu trúc.
6. **Xây dựng nguyên mẫu `app/parsers/contract_parser.py`:**
   * Viết bộ Regex + FSM nhận diện `PHẦN`, `CHƯƠNG`, `ĐIỀU`, `KHOẢN`, `ĐIỂM` và viết unit test kiểm tra trên 5 hợp đồng mẫu.
7. **Xây dựng nguyên mẫu `app/engines/clause_aligner.py`:**
   * Cài đặt bước tính ma trận tương đồng TF-IDF + tiêu đề và gọi `scipy.optimize.linear_sum_assignment` để ghép cặp các nút cấp `ARTICLE` và `CLAUSE`.
8. **Viết tài liệu `[README.md](file:///C:/Users/Admin/orca/workspaces/contract-diff/weakfish/README.md)`:**
   * Ghi rõ mục tiêu dự án, kiến trúc thư mục, lệnh cài đặt và lệnh chạy server/test.

### 9.2. Các Quyết định Thiết kế Còn Mở Cần Bạn Xác nhận
Trước khi bắt tay vào viết code triển khai các module mới, bạn hãy xác nhận giúp tôi 5 quyết định thiết kế sau:

1. **Ngôn ngữ của hợp đồng mục tiêu:** Đồ án sẽ tập trung **100% vào hợp đồng tiếng Việt**, hay bạn muốn hỗ trợ **song ngữ Việt – Anh** (ví dụ: cả cấu trúc `Điều 1 / Khoản 1.1` lẫn `Article 1 / Section 1.1`)?
2. **Mức độ sử dụng Mô hình Học sâu (Embedding / OCR):**
   * *Phương án A (Nhẹ - CPU-friendly):* Dùng TF-IDF n-gram + thuật toán khoảng cách chuỗi cho Alignment, và `Tesseract OCR` cho PDF quét (cài đặt nhanh, không tốn RAM, chạy mượt trên mọi máy).
   * *Phương án B (Nặng hơn - AI/NLP sâu):* Tích hợp thêm `sentence-transformers` (như `vietnamese-bi-encoder`) cho Semantic Alignment và `VietOCR` cho PDF quét (điểm nhấn AI mạnh hơn cho hội đồng ngành CNTT/AI, nhưng cần tải trọng số mô hình $\sim 400\text{MB}$).
3. **Độ sâu của Cây Cấu trúc khi Ghép cặp (Granularity of Alignment):** Bạn muốn thuật toán Alignment ghép cặp ở cấp **Điều (`ARTICLE`) rồi tiếp tục ghép đệ quy xuống cấp Khoản (`CLAUSE`) / Điểm (`POINT`)**, hay làm phẳng (flatten) về cấp **Khoản (`CLAUSE`)** để ghép toàn cục một lần (giúp bắt được trường hợp một Khoản bị chuyển từ Điều 3 sang Điều 8)? *(Khuyến nghị: Ghép 2 tầng – neo theo Điều trước, sau đó các Khoản chưa ghép được sẽ được phép tìm cặp toàn cục xuyên qua các Điều khác).*
4. **Hình thức Giao diện Demo phục vụ Bảo vệ:** Bạn chỉ cần **Backend FastAPI + Xuất file báo cáo HTML Redline độc lập**, hay muốn làm thêm một **trang Web UI trực quan** (bằng Streamlit hoặc FastAPI + HTML/Tailwind/HTMX) để kéo-thả 2 file PDF khi đứng trước hội đồng?
5. **Thời gian thực tế còn lại của bạn:** Giả định **16 tuần (1 người làm)** ở Mục 6 có khớp với lịch nộp quyển của trường bạn hiện tại không, hay cần nén lại (ví dụ 8–12 tuần)?
