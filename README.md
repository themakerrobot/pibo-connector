# pibo-connector

교실에 켜져 있는 **파이보 / 파이브레인을 브라우저 한 장으로** 찾고, 점호하고,
같은 코드를 한 번에 실행한다.

- **로봇에는 아무것도 설치하지 않는다.** OS 가 이미 띄워둔 두 서버만 쓴다
- **노트북에 파이썬이 없어도 된다.** 릴리스의 실행 파일을 받아 더블클릭하면 브라우저가 열린다
- **소스로도 그대로 돈다.** 같은 코드다 (`python run.py`)
- **오프라인에서 동작한다.** CDN·npm·빌드 없음. 교실 `pibo` 망에 인터넷이 없어도 된다

```
[노트북] pibo-connector ──┬── :80   socket.io  init / executeb / update / stop
   └ 브라우저 (화면)      └── :8080 HTTP       /wifi · /wifi_scan · /device
```

브라우저는 UDP 를 못 쏘고 254개 TCP 스캔도 느리다. 그래서 스캔과 동시 시작
트리거는 커넥터가 맡고, 브라우저는 화면만 담당한다.

## 받기

**파이썬 없는 노트북** — [Releases](https://github.com/themakerrobot/pibo-connector/releases)

| 노트북 | 파일 |
|---|---|
| Windows | `pibo-connector-windows.exe` |
| Linux | `pibo-connector-linux` (`chmod +x` 후 실행) |
| macOS | `pibo-connector-macos` (`chmod +x`, 첫 실행은 우클릭 → 열기) |

`nightly` 는 `main` 이 바뀔 때마다 자동으로 덮어써진다. 수업에 쓸 거면
버전 태그가 붙은 정식 릴리스를 받는 쪽이 낫다.

**소스로 실행**

```bash
pip install -r requirements.txt
python run.py
```

둘 다 `http://127.0.0.1:8900/` 이 열린다. 포트가 막혀 있으면 다음 빈 포트를 잡는다.

```
python run.py --port 9000        # 포트 지정
python run.py --no-browser       # 브라우저 안 염
python run.py --host 0.0.0.0     # 다른 기기에서도 열기 (이때는 토큰이 붙는다)
```

## 쓰는 순서

화면 문구는 초등 수업 기준으로 쉽게 썼다. 밝은 테마/어두운 테마를 따라가고
(프로젝터엔 밝은 쪽), 오른쪽 위에서 바꿀 수 있다. 영어는 `?lang=en`.

1. **[로봇 찾기]** — 교실 네트워크의 `.1~.254` 를 훑는다. 15대면 보통 3~8초
2. **출석 확인** — 우리 반 로봇 번호(가슴의 8자리)를 출석부에 적으면
   왔어요 / 와이파이 못 붙음 / 안 보여요 로 갈린다
3. **이름 붙이기** — 표의 이름칸을 눌러 `1번`, `창가` 처럼. 다음날에도 남는다
4. 표에서 로봇을 고르고(행을 누르면 된다) **코드** → **[실행!]** 또는 **[다 같이 시작]**

### 코드를 어디서 가져오나

| 모드 | 하는 일 |
|---|---|
| **새 코드** | 코드 창의 내용을 고른 로봇 전부에 보내 실행한다. [예제 골라보기…] 로 `examples/` 를 불러오고, [내 컴퓨터 파일 열기] 도 된다. `Ctrl+Enter` 가 실행 |
| **로봇 안의 파일** | 로봇에 **이미 있는 파일**을 경로로 그 자리에서 실행한다. 코드 창은 쓰지 않는다. [찾아보기] 로 로봇 한 대의 `/home/pi/code` 를 열어 고르고, [코드 창으로 가져오기] 로 읽어와 고친 뒤 전부에 밀어넣을 수도 있다 |

로봇 안의 파일은 `executeb` 로 짧은 런처만 보내서 돌린다 — `.py` 는
`runpy.run_path(..., run_name='__main__')`, `.sh` 는 `sh`. 대상 파일은 손대지
않고, 없는 로봇은 출력에 `[missing] 경로` 가 찍힌다. 폴더 목록과 파일 읽기는
IDE 의 `load_directory` · `load` 이벤트를 그대로 쓴다.

> `load_directory` 는 IDE 의 작업 폴더를 바꾼다. 실행 cwd 가 거기 따라가므로
> 커넥터가 목록을 다 본 뒤 `/home/pi/code` 로 되돌려 둔다.

### 찾기

```
1) TCP connect :8080        — 가장 싸다. 없는 IP 를 여기서 전부 떨군다
2) GET /wifi                — {"result":"ok"} 면 파이보 계열
3) socket.io emit('init')   — SN · OS_VERSION · 온도 · SSID 를 한 번에
```

- **[다시 확인]** — 저장된 IP 로만 확인한다. 안 바뀌었으면 1~2초.
  응답 없는 놈이 있으면 그때만 전체 스캔을 돌리면 된다
- **[와이파이 못 붙은 로봇 찾기]** — 공유기에 못 붙은 로봇은 IP 가 없어 스캔에 안 걸린다.
  대신 자기 WiFi 를 켜고 있고 SSID 가 `pibo-<SN>` 이다 (`system/hotspot.sh`).
  노트북 WiFi 스캔을 먼저 쓰고, 안 되면 붙어 있는 로봇에게 시킨다

> 로봇에게 시킨 스캔은 **캐시된 결과**다. `openpibo` 의 `wifi.py` 가 쓰는 nmcli 에
> `--rescan` 이 없어서 오래된 값이 나올 수 있다. 화면에도 '참고용' 으로 표시된다.

### 목록

키는 **SN** 이다 — Pi 시리얼 뒤 8자리. 가슴 화면의 SN, hostname, AP SSID 의
`pibo-<SN>` 이 전부 같은 값이라 사람이 눈으로 맞춰볼 수 있다. IP 는 DHCP 라
다음날 바뀐다.

[내보내기] / [가져오기] 로 노트북을 바꿔도 목록과 이름을 그대로 옮긴다.

### 기종 판별 (Pibo / PiBrain)

**OS_VERSION** 으로 가른다. `system.sh` 가 `/home/pi/.OS_VERSION` 을 읽어
`init` 응답에 실어 보내므로 추가 통신이 없다.

기본 규칙은 소문자 부분문자열이고, 긴 조각을 먼저 본다:

```json
{ "pibrain": "pibrain", "pi_brain": "pibrain", "pibo": "pibo" }
```

새 이미지 이름이 생기면 화면의 **[종류 구분 설정]** 에서 조각 하나만 더하면 된다
(`rules.json` 에 저장된다. 코드를 안 고친다). 어느 조각에도 안 걸리면 `?` 로
두고 OS_VERSION 원문을 배지에 그대로 띄운다 — 추측으로 기종을 칠하지 않는다.

### 실행

체크한 로봇에 `executeb` 로 동시에 던지고, `update` 이벤트의 `record` 를
로봇별로 받아 마지막 줄을 띄운다. 줄을 누르면 전체 로그가 펼쳐진다.

**[다 같이 시작]** 은 시작 시각을 맞춘다. 그냥 [실행!] 하면 `import openpibo` 시간이
로봇마다 달라 수백 ms 씩 어긋난다. 코드를 한 줄로 나눈다:

```python
from openpibo.motion import Motion   # 준비 — 무거운 import 를 여기서 끝낸다
m = Motion()

# --- GO ---

m.set_motion('dance1', 2)            # 본편 — 트리거를 받은 순간 같이 돈다
```

전부 `[ready]` 를 찍으면 커넥터가 UDP `:50055` 로 트리거를 쏜다. 고정 초를
기다리지 않고 실제 준비 개수를 센다.

> 공유기가 무선 브로드캐스트를 막으면(AP isolation, 멀티캐스트 필터) 트리거가
> 안 간다. 커넥터는 브로드캐스트와 유니캐스트를 둘 다 쏘지만, 그래도 막히면
> `[timeout]` 으로 끝나 바로 알 수 있다. 그때는 그냥 [실행!] 으로 내려오면 된다.
>
> 로봇 안의 파일을 다 같이 시작하려면 내용을 알아야 GO 래퍼로 감쌀 수 있다.
> 그래서 고른 첫 로봇에서 파일을 읽어와 전부에 밀어넣는다 (파이썬만).

### 알아둘 것

- **실행하면 로봇의 `tools` · `classify` · `llama-server` 가 멈춘다.**
  LLM 쓰는 코드는 `Dialog.start_llm` 부터 해야 한다
- **IDE 의 출력창은 전역이다.** 교사 브라우저가 IDE 에 붙어 있으면 그쪽 터미널에도
  출력이 찍히고, 누가 IDE 에서 Run 을 누르면 이쪽 코드가 죽는다
- 15대 동시 카메라는 대당 0.3~0.8 Mbps × airtime 2배 ≈ 24 Mbps.
  5GHz 80MHz 한 채널이면 여유다

## 안전장치

- **WiFi 비밀번호는 어디에도 남지 않는다.** `system` 배열 인덱스 9 와 `/wifi`
  응답의 `psk` 는 평문이다. 커넥터는 받는 즉시 버리고, 저장소는 `psk`·`password`·
  `key` 가 이름에 든 필드를 통째로 거른다. `tests/smoke.py` 가 매 CI 마다 확인한다
- **`codepath` 는 하드코딩이고 화면에 나오지 않는다.** `executeb` 에는 `is_protect`
  검사가 없다 (`execute` 에만 있다). 사용자가 고치게 두면 보호 디렉토리를 덮어쓴다
- 기본 바인딩은 `127.0.0.1` 이다. `--host 0.0.0.0` 으로 열 때만 토큰이 붙는다

## 검증

```bash
python -m tests.smoke            # 파싱 · 판별 · PSK 유출 · 래퍼 · 런처 · 번들 경로 · 서버 기동
python -m tests.exe_smoke dist/pibo-connector   # 묶은 실행 파일이 실제로 뜨는지 (CI 가 세 OS 에서 돌린다)
```

기기 없이 전 경로를 돌려보려면 가짜 로봇을 띄운다:

```bash
python -m tests.mock_pibo --sn cd488e95 --os piBo_260915v1-ph &
python run.py
# 화면에서 서브넷을 127.0.0 으로 두고 [찾기]
```

PiBrain 쪽 판별까지 보려면 OS 이름만 바꿔 한 대 더 띄우면 된다:

```bash
python -m tests.mock_pibo --sn 1a2b3c4d --os piBrain_260915v1 \
  --ide-port 8081 --sys-port 8082
```

기기가 있으면:

1. 로봇 2대를 켜고 커넥터를 띄운 뒤 [찾기] — SN · OS_VERSION 과 함께 뜨는지
2. `print('hello')` 를 [실행] — 양쪽 출력에 `hello` 와 `[exit]` 이 뜨는지
3. 1대를 AP 모드로 만들고 [AP 모드 찾기] — `pibo-<SN>` 이 잡히는지
4. 커넥터를 껐다 켜서 목록이 남아 있는지
5. 15대까지 올려 스캔 시간과 동시 실행이 견디는지

## exe 빌드 (손으로)

```bash
pip install -r requirements.txt pyinstaller
pyinstaller build/pibo-connector.spec --noconfirm
# dist/pibo-connector(.exe)
```

`static/` 과 `examples/` 는 spec 의 `datas` 로 같이 묶인다 — `config.py` 가
보는 자리(`_MEIPASS/static`, `_MEIPASS/examples`)와 정확히 맞아야 하고,
`tests/smoke.py` 가 그걸 확인한다. 윈도우 아이콘은 `build/make_icon.py` 가
의존성 없이 만든 `build/pibo-connector.ico` 다.

CI 가 같은 스펙으로 빌드한다. `main` push 는 `nightly` 를, `v*` 태그는 정식
릴리스를 만든다 (`.github/workflows/release.yml`).

## 근거

전부 `themakerrobot/openpibo-os.pibo` 코드에서 확인한 것이다.

| 사실 | 근거 |
|---|---|
| IDE(80) 가 socket.io 서버다 | `ide/run_ide.py` `SocketManager` |
| CORS 전면 허용 | `ide/run_ide.py` `allow_origins=["*"]` |
| `init` → `system` 이벤트로 기기 정보 | `ide/run_ide.py` `handle_init` |
| 그 배열이 `system.sh` 의 CSV 그대로 | `system/system.sh` 마지막 `echo` |
| `executeb` 로 코드 실행, `update.record` 로 출력 | `ide/run_ide.py` `handle_executeb`, `execute` |
| `executeb` 에는 `is_protect` 가 없다 | `handle_execute` 와 비교 |
| `stop` 이 실행을 죽인다 | `ide/run_ide.py` `handle_stop` |
| 8080 은 `/wifi`, `/wifi_scan`, `/device/{pkt}` | `system/booting.py` |
| `/wifi` 응답에 psk 평문이 있다 | `system/booting.py` |
| 폴더 목록 · 파일 읽기 이벤트가 있다 | `ide/run_ide.py` `handle_load_directory`, `handle_load` |
| `load_directory` 가 IDE 작업 폴더(PATH)를 바꾼다 | `ide/run_ide.py` `global PATH` |
| AP SSID 가 `pibo-<시리얼 뒤 8자리>` | `system/hotspot.sh` `AP_SSID` |
| hostname 도 같은 8자리 | `system/init` |
| PiBrain 은 GPIO 직결, Pibo 는 UART device 보드 | `openpibo/device.py` `DeviceByPiBrain` / `DeviceByPibo` |

`system` 배열 인덱스 (`system/system.sh`):

| i | 값 | i | 값 |
|---|---|---|---|
| 0 | Pi 시리얼 (뒤 8자리 = SN) | 6 | wlan0 IP |
| 1 | `.OS_VERSION` | 7 | eth1 IP |
| 2 | uptime | 8 | 접속 SSID |
| 3 | 온도 | **9** | **WiFi 비밀번호 (평문 — 버린다)** |
| 4, 5 | 메모리 | 10, 11 | identity, key-mgmt |
