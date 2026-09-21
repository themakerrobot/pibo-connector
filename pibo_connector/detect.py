"""기종 판별 — Pibo 인가 PiBrain 인가.

기준은 **OS_VERSION** 이다. system.sh 가 /home/pi/.OS_VERSION 을 읽어
system 배열 인덱스 1 로 넘겨준다 (예: 'piBo_260915v1-ph').
socket.io 로 init 한 번이면 받으므로 추가 통신이 없다.

매칭은 소문자 부분문자열이다. 'pibrain' 을 'pibo' 보다 먼저 본다 —
반대로 하면 PiBrain 이미지 이름에 'pibo' 가 들어 있을 때 오판한다.

규칙은 rules.json 으로 덮어쓸 수 있다. 새 이미지 이름이 생기면
코드를 고치지 않고 화면의 [판별 규칙] 에서 조각 하나만 더하면 된다.

    { "os_contains": { "pibrain": "pibrain", "pibo": "pibo" } }

어느 조각에도 안 걸리면 unknown 으로 두고 OS_VERSION 원문을 화면에
그대로 띄운다. 추측으로 기종을 칠하지 않는다.
"""

import json
from typing import Optional, Tuple

from . import config

PIBO = "pibo"
PIBRAIN = "pibrain"
UNKNOWN = "unknown"

DEFAULT_RULES = {
    # OS_VERSION(소문자) 에 이 조각이 들어 있으면 그 기종.
    # 긴 조각부터 비교하므로 'pibrain' 이 'pibo' 를 이긴다.
    "os_contains": {
        "pibrain": PIBRAIN,
        "pi_brain": PIBRAIN,
        "pibo": PIBO,
    },
    # OS_VERSION 이 비어 있을 때만 쓰는 보조 판별.
    # Pibo 는 UART device 보드를 거치고(DeviceByPibo.send_raw),
    # PiBrain 은 GPIO 직결이라(DeviceByPiBrain) /device/#40:! 가 비거나 에러다.
    # 어디까지나 보조다 — 결과는 confidence='low' 로 표시한다.
    "use_device_probe": True,
    "device_min_dashes": 3,   # get_button 이 split('-')[3] 을 쓴다
}


def load_rules() -> dict:
    """rules.json 이 있으면 기본 규칙에 덮어쓴다. 깨진 파일은 무시한다."""
    rules = json.loads(json.dumps(DEFAULT_RULES))   # deep copy
    try:
        path = config.rules_path()
        if path.exists():
            user = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                rules.update(user)
    except Exception:
        pass
    return rules


def save_rules(rules: dict) -> None:
    config.rules_path().write_text(
        json.dumps(rules, indent=1, ensure_ascii=False), encoding="utf-8")


def device_reply_looks_like_packet(reply, rules: dict) -> bool:
    """GET /device/#40:! 응답이 device 보드 패킷 모양인가.

    booting.py 는 실패해도 200 으로 'Error: ...' 를 돌려준다.
    device 보드가 없으면 system_data 가 비어 '' 가 온다.
    """
    if not isinstance(reply, str):
        return False
    s = reply.strip()
    if not s or s.lower().startswith("error"):
        return False
    return s.count("-") >= int(rules.get("device_min_dashes", 3))


def classify(os_version: str = "", device_reply=None,
             rules: Optional[dict] = None) -> Tuple[str, str, str]:
    """(kind, confidence, evidence).

    confidence 'high' 는 OS_VERSION 으로 확정한 경우다.
    'low' 는 보조 판별이라 화면에 '확인 필요' 로 표시한다.
    """
    rules = rules or load_rules()
    os_v = (os_version or "").strip()
    os_l = os_v.lower()

    table = rules.get("os_contains", {}) or {}
    for frag in sorted(table, key=len, reverse=True):
        if frag and frag.lower() in os_l:
            return table[frag], "high", f"OS_VERSION '{os_v}' ⊃ '{frag}'"

    if os_v:
        # OS_VERSION 은 받았는데 아는 조각이 없다. 새 이미지 이름일 것이다.
        return UNKNOWN, "low", f"OS_VERSION '{os_v}' — 규칙에 없는 이름"

    if rules.get("use_device_probe", True) and device_reply is not None:
        if device_reply_looks_like_packet(device_reply, rules):
            return PIBO, "low", f"OS_VERSION 없음 · /device/#40:! = '{_clip(device_reply)}'"
        return PIBRAIN, "low", f"OS_VERSION 없음 · /device/#40:! 응답 없음"

    return UNKNOWN, "low", "OS_VERSION 없음"


def _clip(v, n: int = 60) -> str:
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"
