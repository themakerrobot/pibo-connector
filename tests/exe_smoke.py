"""빌드된 실행 파일이 실제로 뜨는지 본다. 세 OS 에서 같은 스크립트를 쓴다.

    python tests/exe_smoke.py dist/pibo-connector.exe [--port 8912] [--timeout 90]

실패하면 실행 파일이 찍은 stdout/stderr 를 통째로 보여준다.
PyInstaller 로 묶인 뒤에야 드러나는 문제(모듈 누락, static 경로)는
이 출력이 없으면 원인을 알 수 없다.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exe")
    ap.add_argument("--port", type=int, default=8912)
    ap.add_argument("--timeout", type=float, default=90.0,
                    help="onefile 은 첫 실행에 압축을 푼다. 넉넉히 준다")
    args = ap.parse_args()

    exe = Path(args.exe).resolve()
    if not exe.exists():
        print(f"!! 실행 파일이 없다: {exe}")
        return 1
    print(f"exe: {exe}  ({exe.stat().st_size / 1e6:.1f} MB)")

    base = f"http://127.0.0.1:{args.port}"
    log = Path(tempfile.gettempdir()) / "exe_smoke.log"
    fails = []

    with open(log, "wb") as f:
        p = subprocess.Popen([str(exe), "--no-browser", "--port", str(args.port)],
                             stdout=f, stderr=subprocess.STDOUT)
    try:
        info = None
        died = False
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            if p.poll() is not None:
                died = True
                print(f"!! 실행 파일이 그냥 끝났다 (exit {p.returncode})")
                break
            try:
                _, body = get(base + "/api/info", 3)
                info = json.loads(body)
                break
            except Exception:
                time.sleep(1.0)

        if info is None:
            if not died:
                print(f"!! {args.timeout:.0f}초 안에 {base}/api/info 가 안 열렸다")
            fails.append("기동")
        else:
            took = args.timeout - (deadline - time.time())
            print(f"ok  /api/info  ({took:.1f}초 만에 응답)")
            print("    " + json.dumps(info, ensure_ascii=False))
            if not info.get("frozen"):
                print("!! frozen 이 False 다 — 묶인 실행 파일이 아니다")
                fails.append("frozen")

            # static 이 번들에 안 들어갔으면 여기서 걸린다
            try:
                st, html = get(base + "/", 5)
                if st != 200 or "pibo-connector" not in html:
                    print(f"!! 화면이 이상하다 (status {st})")
                    fails.append("화면")
                else:
                    print("ok  /  (화면 서빙)")
            except Exception as ex:
                print(f"!! 화면을 못 받았다: {ex}")
                fails.append("화면")

            try:
                st, _ = get(base + "/static/app.js", 5)
                print("ok  /static/app.js" if st == 200 else f"!! app.js status {st}")
                if st != 200:
                    fails.append("정적 파일")
            except Exception as ex:
                print(f"!! app.js 를 못 받았다: {ex}")
                fails.append("정적 파일")
    finally:
        try:
            p.terminate()
            p.wait(timeout=15)
        except Exception:
            p.kill()

    out = ""
    try:
        out = log.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        pass
    if out or fails:
        print("─── 실행 파일 출력 " + "─" * 40)
        print(out or "(출력 없음)")
        print("─" * 58)

    if fails:
        print("실패: " + ", ".join(fails))
        return 1
    print("exe 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
