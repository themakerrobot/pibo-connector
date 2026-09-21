"""기기 없이 할 수 있는 검증. CI 와 손으로 같은 걸 돌린다.

    python -m tests.smoke

보는 것:
  1) system.sh CSV 파싱 — 특히 인덱스 9(WiFi 비밀번호)가 어디에도 안 남는지
  2) 기종 판별 (OS_VERSION 기준)
  3) 목록 저장소가 psk 계열 필드를 통째로 거르는지
  4) AP SSID 패턴
  5) 동시 실행 래퍼가 문법에 맞는 파이썬인지
  6) 서버가 실제로 떠서 /api/info 를 주는지
"""

import ast
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pibo_connector import config, detect, robot, runner, scan   # noqa: E402
from pibo_connector.store import Fleet                           # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def test_parse_system():
    print("system.sh CSV 파싱")
    # system/system.sh 의 echo 순서 그대로. 인덱스 9 가 PSK 다.
    row = ["100000001cd488e95", "piBo_260915v1-ph", "12345.6", "48.3'C",
           "3900000", "2100000", "192.168.0.51", "", "classroom-5g",
           "SuperSecret!234", "", "wpa-psk"]
    d = robot.parse_system(row)
    check("SN 은 시리얼 뒤 8자리", d["sn"] == "cd488e95", d["sn"])
    check("OS_VERSION", d["os"] == "piBo_260915v1-ph")
    check("IP 는 wlan0 우선", d["ip"] == "192.168.0.51")
    check("SSID", d["ssid"] == "classroom-5g")
    blob = json.dumps(d, ensure_ascii=False)
    check("PSK 가 파싱 결과에 없다", "SuperSecret" not in blob, blob)

    d2 = robot.parse_system(["100000001cd488e95", "piBo_x"])
    check("짧은 배열도 안 터진다", d2["sn"] == "cd488e95" and d2["ip"] == "")


def test_detect():
    print("기종 판별 (OS_VERSION)")
    k, c, _ = detect.classify("piBo_260915v1-ph")
    check("piBo_… → pibo", (k, c) == (detect.PIBO, "high"), f"{k}/{c}")
    k, c, _ = detect.classify("piBrain_260915v1")
    check("piBrain_… → pibrain", (k, c) == (detect.PIBRAIN, "high"), f"{k}/{c}")
    k, _, _ = detect.classify("pibrain-pibo-mix")
    check("pibrain 이 pibo 보다 먼저 걸린다", k == detect.PIBRAIN, k)
    k, c, _ = detect.classify("something-else-v1")
    check("모르는 이름은 unknown", k == detect.UNKNOWN, k)
    k, _, _ = detect.classify("", device_reply="#40:12-0-1-0-99:!")
    check("OS 없으면 device 패킷으로 pibo 추정", k == detect.PIBO, k)
    k, _, _ = detect.classify("", device_reply="Error: no device")
    check("device 에러면 pibrain 쪽", k == detect.PIBRAIN, k)


def test_store():
    print("목록 저장소")
    with tempfile.TemporaryDirectory() as td:
        f = Fleet(path=Path(td) / "fleet.json")
        f.upsert({"sn": "CD488E95", "os": "piBo_1", "ip": "192.168.0.51",
                  "psk": "SuperSecret!234", "wifi_password": "nope",
                  "kind": "pibo"})
        f.rename("cd488e95", "1번")
        f.save()
        raw = (Path(td) / "fleet.json").read_text(encoding="utf-8")
        check("SN 은 소문자 키", "cd488e95" in raw)
        check("PSK 가 파일에 없다", "SuperSecret" not in raw and "nope" not in raw, raw)
        check("이름이 남는다", '"1번"' in raw)

        # 다시 스캔해도 사람이 붙인 이름은 보존된다
        f.upsert({"sn": "cd488e95", "ip": "192.168.0.77", "os": "piBo_2"})
        check("재스캔 후에도 이름 유지", f.get("cd488e95")["name"] == "1번")
        check("IP 는 갱신", f.get("cd488e95")["ip"] == "192.168.0.77")

        f.set_roster(["cd488e95", "DEADBEEF", "cd488e95"])
        st = f.roster_status()
        check("점호: 중복 제거", st["expected"] == 2, st)
        check("점호: 접속 1대", st["present"] == ["cd488e95"], st)
        check("점호: 미확인 1대", st["missing"] == ["deadbeef"], st)


def test_ap_rx():
    print("AP SSID 패턴")
    check("pibo-<SN> 만 잡는다", bool(scan.AP_RX.match("pibo-cd488e95")))
    check("교실 공유기 SSID 는 안 잡힌다", not scan.AP_RX.match("pibo-classroom"))
    check("길이가 다르면 안 잡힌다", not scan.AP_RX.match("pibo-cd488e9"))


def test_wrap():
    print("동시 실행 래퍼")
    code = "import openpibo\n" + config.SYNC_MARK + "\nprint('go')\n"
    body, main = code.split(config.SYNC_MARK, 1)
    wrapped = runner.WRAP.format(port=config.TRIG_PORT, wait=120.0,
                                 body=body, main=main)
    try:
        ast.parse(wrapped)
        ok = True
    except SyntaxError as ex:
        ok = False
        print(wrapped)
        print(ex)
    check("래퍼가 파이썬 문법에 맞는다", ok)
    check("트리거 포트가 박혀 있다", f"bind(('', {config.TRIG_PORT}))" in wrapped)
    check("[ready] 를 찍는다", "print('[ready]'" in wrapped)

    # 사용자 코드에 중괄호가 있어도 format 이 깨지면 안 된다
    w2 = runner.WRAP.format(port=1, wait=1, body="d = {'a': 1}", main="print(d['a'])")
    try:
        ast.parse(w2)
        ok2 = True
    except SyntaxError:
        ok2 = False
    check("중괄호가 든 코드도 통과", ok2)


def test_server():
    print("서버 기동")
    port = 8911
    p = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py"), "--no-browser", "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))
    try:
        info = None
        for _ in range(40):
            time.sleep(0.5)
            if p.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/info", timeout=2) as r:
                    info = json.loads(r.read().decode())
                    break
            except Exception:
                continue
        check("/api/info 가 200", info is not None,
              (p.stdout.read() if p.poll() is not None else "기동 안 됨"))
        if info:
            check("codepath 고정", info["codepath"] == config.CODEPATH, info["codepath"])
            check("트리거 포트", info["trigger_port"] == config.TRIG_PORT)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
                html = r.read().decode()
            check("화면이 나온다", "pibo-connector" in html)
            # codepath 를 UI 에 노출하지 않는다 (executeb 에 is_protect 가 없다)
            check("화면에 codepath 입력칸이 없다", "/home/pi/code" not in html)
        except Exception as ex:
            check("화면이 나온다", False, str(ex))
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()


def main() -> int:
    for fn in (test_parse_system, test_detect, test_store, test_ap_rx,
               test_wrap, test_server):
        fn()
    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: " + ", ".join(FAIL))
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
