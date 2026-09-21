"""로컬 네트워크 관련 — 내 IP/서브넷 추정, ARP 표, 노트북 WiFi 스캔."""

import platform
import re
import socket
import subprocess
from typing import Dict, List, Tuple

IP_RX = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
MAC_RX = re.compile(r"\b([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})\b")


def local_ip() -> str:
    """기본 경로로 나가는 인터페이스의 IP. UDP 소켓은 실제로 패킷을 보내지 않는다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""
    finally:
        s.close()


def guess_subnet() -> str:
    """'192.168.0' 형태. 못 찾으면 빈 문자열."""
    ip = local_ip()
    if not ip or ip.startswith("127."):
        return ""
    return ".".join(ip.split(".")[:3])


def local_subnets() -> List[str]:
    """붙어 있는 사설망 후보들. 첫 번째가 기본 경로다.

    AP 모드 로봇에 직접 붙은 경우(192.168.34.x) 도 여기에 잡힌다.
    """
    out: List[str] = []
    g = guess_subnet()
    if g:
        out.append(g)

    try:
        for _, _, _, _, sa in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = sa[0]
            if ip.startswith("127."):
                continue
            sub = ".".join(ip.split(".")[:3])
            if sub not in out:
                out.append(sub)
    except Exception:
        pass
    return out


def arp_table() -> Dict[str, str]:
    """{ip: mac}. 직전에 그 IP 와 통신했으면 커널 ARP 캐시에 들어 있다.

    MAC 은 DHCP 로 IP 가 바뀌어도 그대로라 보조 식별자로 쓴다.
    다만 목록의 키는 SN 이다 (가슴 화면에 뜨는 값과 같아야 사람이 맞춰볼 수 있다).
    """
    sysname = platform.system()
    if sysname == "Linux":
        cmd = ["ip", "neigh"]
    else:
        cmd = ["arp", "-a"]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, **_no_window()
        ).stdout
    except Exception:
        return {}

    # 줄마다 따로 본다. 'dev wlan0 lladdr' 처럼 중간에 숫자가 섞여서
    # IP~MAC 을 한 정규식으로 이으면 리눅스에서 안 잡힌다.
    table: Dict[str, str] = {}
    for line in out.splitlines():
        i, m = IP_RX.search(line), MAC_RX.search(line)
        if i and m:
            table[i.group(1)] = m.group(1).lower().replace("-", ":")
    return table


def _no_window() -> dict:
    """윈도우에서 콘솔 창이 깜빡이지 않게 한다 (exe 를 windowed 로 빌드할 때)."""
    if platform.system() == "Windows":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def wifi_scan() -> Tuple[List[dict], str]:
    """노트북의 WiFi 스캔 결과와, 실패했으면 그 이유를 같이 준다.

    반환: ([{ssid, bssid, signal, channel}, ...], error_message)
    """
    sysname = platform.system()
    rows: List[dict] = []
    try:
        if sysname == "Linux":
            out = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,CHAN", "dev", "wifi",
                 "list", "--rescan", "yes"],
                capture_output=True, text=True, timeout=30,
            ).stdout
            for line in out.splitlines():
                # nmcli -t 는 BSSID 의 ':' 를 '\:' 로 이스케이프한다
                f = re.split(r"(?<!\\):", line)
                if len(f) >= 4:
                    rows.append({
                        "ssid": f[0],
                        "bssid": f[1].replace("\\:", ":").lower(),
                        "signal": f[2],
                        "channel": f[3],
                    })
        elif sysname == "Windows":
            out = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, text=True, timeout=30, **_no_window()
            ).stdout
            ssid = ""
            for line in out.splitlines():
                m = re.match(r"\s*SSID\s+\d+\s*:\s*(.*)", line)
                if m:
                    ssid = m.group(1).strip()
                    continue
                m = re.match(r"\s*BSSID\s+\d+\s*:\s*([0-9a-fA-F:]{17})", line)
                if m:
                    rows.append({"ssid": ssid, "bssid": m.group(1).lower(),
                                 "signal": "", "channel": ""})
                    continue
                m = re.match(r"\s*(?:Signal|신호)\s*:\s*(\d+)%", line)
                if m and rows:
                    rows[-1]["signal"] = m.group(1)
                    continue
                m = re.match(r"\s*(?:Channel|채널)\s*:\s*(\d+)", line)
                if m and rows:
                    rows[-1]["channel"] = m.group(1)
        else:
            # macOS 는 wdutil / system_profiler 출력이 OS 버전마다 달라
            # 형식을 확인하지 않고 파서를 넣지 않는다. 로봇에게 시키는 쪽을 쓴다.
            return [], f"{sysname} 는 노트북 WiFi 스캔을 지원하지 않는다"
    except FileNotFoundError as ex:
        return [], f"스캔 명령을 찾을 수 없다: {ex}"
    except Exception as ex:
        return [], f"WiFi 스캔 실패: {ex}"
    return rows, ""


def udp_broadcast(payload: bytes, port: int, times: int = 3,
                  targets: List[str] = None) -> List[str]:
    """동시 시작 트리거. UDP 는 유실될 수 있으니 여러 번 쏜다.

    255.255.255.255 는 공유기의 AP isolation / 멀티캐스트 필터에 막힐 수 있다.
    그래서 서브넷 브로드캐스트 주소와 개별 유니캐스트도 같이 쏜다.
    반환: 실제로 보낸 주소 목록.
    """
    sent: List[str] = []
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        addrs = ["255.255.255.255"]
        sub = guess_subnet()
        if sub:
            addrs.append(f"{sub}.255")
        addrs.extend(targets or [])
        for _ in range(times):
            for a in addrs:
                try:
                    u.sendto(payload, (a, port))
                    if a not in sent:
                        sent.append(a)
                except Exception:
                    pass
    finally:
        u.close()
    return sent
