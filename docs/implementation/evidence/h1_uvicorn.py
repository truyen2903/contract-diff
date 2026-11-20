"""H1: kịch bản thủ công trên Uvicorn thật (timeout thật 30 s, không chạy trong CI).

Chạy: .venv/Scripts/python docs/implementation/evidence/h1_uvicorn.py <repo> <module|exe>
Cảnh báo: bước cuối hard-kill API nên để lại một thư mục %TEMP%/contractdiff-* (rủi ro R-TEMP).
"""
import glob, json, os, subprocess, sys, tempfile, threading, time
import httpx

REPO, LAUNCHER = sys.argv[1], sys.argv[2]
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
URL = "http://127.0.0.1:8765/api/v1"
SELF_REF = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n3 0 R\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n136\n%%EOF\n"
)

def children(pid):
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
        f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | ForEach-Object ProcessId"],
        capture_output=True, text=True).stdout.split()
    return [int(x) for x in out]

def server_pid(launcher_pid):
    # .venv\Scripts\python.exe là launcher: server thật là process con của nó (nếu có).
    # uvicorn.exe thêm một tầng launcher nữa: đi theo chuỗi con duy nhất tới lá (chưa có worker).
    pid = launcher_pid
    while len(found := children(pid)) == 1:
        pid = found[0]
    return pid

def alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out

def temp_leftovers():
    return glob.glob(os.path.join(tempfile.gettempdir(), "contractdiff-*"))

def start_server():
    cmd = {"module": [PY, "-m", "uvicorn"], "exe": [os.path.join(REPO, ".venv", "Scripts", "uvicorn.exe")]}[LAUNCHER]
    server = subprocess.Popen(cmd + ["app.main:app", "--port", "8765"], cwd=REPO,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if httpx.get(URL + "/health").status_code == 200:
                return server
        except httpx.HTTPError:
            time.sleep(0.1)
    raise SystemExit("server did not start")

def extract(data, client):
    return client.post(URL + "/documents/extract", files={"file": ("a.pdf", data, "application/pdf")})

def main():
    before = set(temp_leftovers())
    server = start_server()
    real = server_pid(server.pid)
    report = {"launcher": LAUNCHER, "launcher_pid": server.pid, "server_pid": real}
    client = httpx.Client(timeout=60)
    try:
        old = open(os.path.join(REPO, "tests/fixtures/contract_old.pdf"), "rb").read()
        new = open(os.path.join(REPO, "tests/fixtures/contract_new.pdf"), "rb").read()
        t = time.monotonic()
        r = client.post(URL + "/comparisons/pdf", files={"old_file": ("o.pdf", old, "application/pdf"), "new_file": ("n.pdf", new, "application/pdf")})
        report["valid_pdf"] = [r.status_code, len(r.json()["changes"]), round(time.monotonic() - t, 2)]

        # Hai PDF treo chiếm cả 2 slot; trong lúc đó đo /health và request thứ ba.
        results = []
        def hang():
            t0 = time.monotonic()
            r = httpx.post(URL + "/documents/extract", files={"file": ("a.pdf", SELF_REF, "application/pdf")}, timeout=60)
            results.append([r.status_code, r.json().get("error_code"), round(time.monotonic() - t0, 2)])
        threads = [threading.Thread(target=hang) for _ in range(2)]
        for th in threads: th.start()
        deadline = time.monotonic() + 10
        while len(children(real)) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        report["workers_during_hang"] = len(children(real))
        t = time.monotonic(); h = client.get(URL + "/health"); report["health_during_hang"] = [h.status_code, round((time.monotonic() - t) * 1000, 1)]
        t = time.monotonic(); b = extract(SELF_REF, client)
        report["third_request"] = [b.status_code, b.json().get("error_code"), b.headers.get("retry-after"), round(time.monotonic() - t, 3)]
        for th in threads: th.join()
        report["hung_requests"] = results
        time.sleep(0.5)
        report["workers_after_timeout"] = children(real)
        report["temp_after_timeout"] = sorted(set(temp_leftovers()) - before)

        r = client.post(URL + "/comparisons/pdf", files={"old_file": ("o.pdf", old, "application/pdf"), "new_file": ("n.pdf", new, "application/pdf")})
        report["valid_after_timeout"] = [r.status_code, len(r.json()["changes"])]

        # Hard-kill API khi worker đang treo: worker mồ côi phải tự thoát (watchdog 30 + 5 s).
        hang_thread = threading.Thread(target=lambda: _ignore(lambda: httpx.post(URL + "/documents/extract", files={"file": ("a.pdf", SELF_REF, "application/pdf")}, timeout=70)), daemon=True)
        hang_thread.start()
        deadline = time.monotonic() + 10
        while not children(real) and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(1)
        worker = children(real)[0]
        subprocess.run(["taskkill", "/F", "/PID", str(real)], capture_output=True)
        subprocess.run(["taskkill", "/F", "/PID", str(server.pid)], capture_output=True)
        killed_at = time.monotonic()
        while alive(worker) and time.monotonic() - killed_at < 60:
            time.sleep(0.5)
        report["orphan_exit_after_api_kill_s"] = round(time.monotonic() - killed_at, 1) if not alive(worker) else "STILL ALIVE"
        report["temp_after_api_kill"] = sorted(set(temp_leftovers()) - before)
    finally:
        if server.poll() is None:
            server.kill()
    print(json.dumps(report, indent=1))

def _ignore(f):
    try: f()
    except Exception: pass

if __name__ == "__main__":
    main()
