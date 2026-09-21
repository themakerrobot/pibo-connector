"""로컬 웹서버. 브라우저 한 장으로 로봇을 찾고 점호하고 실행한다.

브라우저는 UDP 를 못 쏘고 TCP 스캔도 느리다. 그래서 스캔·트리거는
이 커넥터가 맡고, 브라우저는 화면만 담당한다.
"""

import asyncio
import contextlib
import json
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config, detect, net, scan
from .runner import Runner
from .store import Fleet


class Hub:
    """브라우저로 나가는 이벤트 방송. 탭을 여러 개 열어도 같은 화면을 본다."""

    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.log: List[dict] = []

    def emit(self, msg: dict) -> None:
        msg.setdefault("t", round(time.time(), 3))
        if msg.get("type") in ("log", "job"):
            self.log.append(msg)
            del self.log[:-200]
        loop = self.loop or asyncio.get_event_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(asyncio.ensure_future, self._send(msg))

    async def _send(self, msg: dict) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(json.dumps(msg, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


def create_app(token: str = "") -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        hub.loop = asyncio.get_running_loop()
        yield

    hub = Hub()
    app = FastAPI(title="pibo-connector", version=__version__, docs_url=None,
                  redoc_url=None, lifespan=lifespan)
    fleet = Fleet()
    runner = Runner(fleet, hub.emit)

    app.state.hub = hub
    app.state.fleet = fleet
    app.state.runner = runner
    app.state.token = token

    static = config.static_dir()
    if not static.is_dir():
        # 묶인 실행 파일이라면 빌드가 잘못된 것이다 (spec 의 datas 대상 확인).
        raise RuntimeError(
            f"정적 파일 디렉토리가 없다: {static}"
            + ("  (실행 파일 빌드 문제다 — build/pibo-connector.spec 의 datas 확인)"
               if config.frozen() else ""))
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    def check(request: Request) -> None:
        """--host 0.0.0.0 으로 열었을 때만 토큰을 요구한다."""
        if not token:
            return
        got = request.headers.get("x-token") or request.query_params.get("token")
        if got != token:
            raise HTTPException(status_code=401, detail="token")

    # ── 화면 ────────────────────────────────────────────────────────
    @app.get("/")
    async def index():
        return FileResponse(str(static / "index.html"))

    @app.get("/favicon.ico")
    async def favicon():
        path = static / "favicon.svg"
        if path.exists():
            return FileResponse(str(path))
        return JSONResponse({}, status_code=404)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        if token and websocket.query_params.get("token") != token:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        hub.clients.add(websocket)
        try:
            await websocket.send_text(json.dumps(
                {"type": "hello", "version": __version__,
                 "subnets": net.local_subnets(),
                 "fleet": fleet.list(),
                 "roster": fleet.roster_status(),
                 "busy": runner.busy()}, ensure_ascii=False))
            while True:
                await websocket.receive_text()   # 핑만 받는다
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            hub.clients.discard(websocket)

    # ── 상태 ────────────────────────────────────────────────────────
    @app.get("/api/info")
    async def info(request: Request):
        check(request)
        return {
            "version": __version__,
            "frozen": config.frozen(),
            "data_dir": str(config.data_dir()),
            "subnets": net.local_subnets(),
            "local_ip": net.local_ip(),
            "codepath": config.CODEPATH,
            "trigger_port": config.TRIG_PORT,
            "sync_mark": config.SYNC_MARK,
            "busy": runner.busy(),
        }

    @app.get("/api/fleet")
    async def get_fleet(request: Request):
        check(request)
        return {"robots": fleet.list(), "roster": fleet.roster_status(),
                "roster_list": fleet.roster}

    # ── 찾기 ────────────────────────────────────────────────────────
    @app.post("/api/scan")
    async def api_scan(request: Request, body: dict = Body(default={})):
        check(request)
        subnet = (body.get("subnet") or "").strip()
        if not subnet:
            subnet = net.guess_subnet()
        if not subnet:
            raise HTTPException(400, "서브넷을 알 수 없다. 직접 입력할 것 (예: 192.168.0)")
        try:
            rows = await scan.scan_subnet(
                fleet, subnet,
                progress=lambda d: hub.emit({"type": "scan", **d}),
                concurrency=int(body.get("concurrency") or 128),
                connect_timeout=float(body.get("timeout") or 0.5))
        except ValueError as ex:
            raise HTTPException(400, str(ex))
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return {"found": len(rows), "robots": rows}

    @app.post("/api/refresh")
    async def api_refresh(request: Request):
        check(request)
        res = await scan.refresh(fleet, progress=lambda d: hub.emit({"type": "scan", **d}))
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return res

    @app.post("/api/apscan")
    async def api_apscan(request: Request, body: dict = Body(default={})):
        check(request)
        res = await scan.ap_scan(fleet, use_robot=(body.get("ip") or None))
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return res

    # ── 목록 손질 ───────────────────────────────────────────────────
    @app.post("/api/rename")
    async def api_rename(request: Request, body: dict = Body(...)):
        check(request)
        ok = fleet.rename((body.get("sn") or "").lower(), (body.get("name") or "").strip())
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return {"ok": ok}

    @app.post("/api/note")
    async def api_note(request: Request, body: dict = Body(...)):
        check(request)
        ok = fleet.set_note((body.get("sn") or "").lower(), (body.get("note") or "").strip())
        hub.emit({"type": "fleet", "robots": fleet.list()})
        return {"ok": ok}

    @app.post("/api/remove")
    async def api_remove(request: Request, body: dict = Body(...)):
        check(request)
        ok = fleet.remove((body.get("sn") or "").lower())
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return {"ok": ok}

    @app.post("/api/roster")
    async def api_roster(request: Request, body: dict = Body(...)):
        """점호용 기대 SN 목록. 텍스트로 받아 8자리 조각만 골라낸다."""
        check(request)
        raw = body.get("sns")
        if isinstance(raw, str):
            import re
            raw = re.findall(r"[0-9a-fA-F]{8}", raw)
        fleet.set_roster(list(raw or []))
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return {"roster": fleet.roster, "status": fleet.roster_status()}

    @app.get("/api/export")
    async def api_export(request: Request):
        check(request)
        return fleet.export()

    @app.post("/api/import")
    async def api_import(request: Request, body: dict = Body(...)):
        check(request)
        payload = body.get("payload") if "payload" in body else body
        if isinstance(payload, str):
            payload = json.loads(payload)
        try:
            n = fleet.import_(payload, merge=bool(body.get("merge", True)))
        except Exception as ex:
            raise HTTPException(400, f"가져오기 실패: {ex}")
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return {"imported": n}

    # ── 기종 판별 규칙 ──────────────────────────────────────────────
    @app.get("/api/rules")
    async def get_rules(request: Request):
        check(request)
        return {"rules": detect.load_rules(), "default": detect.DEFAULT_RULES,
                "path": str(config.rules_path())}

    @app.post("/api/rules")
    async def set_rules(request: Request, body: dict = Body(...)):
        check(request)
        rules = body.get("rules")
        if not isinstance(rules, dict):
            raise HTTPException(400, "rules 가 객체가 아니다")
        detect.save_rules(rules)
        # 저장된 OS_VERSION 으로 기종을 다시 매긴다. 통신은 없다.
        loaded = detect.load_rules()
        for row in fleet.list():
            kind, conf, ev = detect.classify(row.get("os", ""), None, loaded)
            fleet.upsert({"sn": row["sn"], "kind": kind,
                          "kind_confidence": conf, "kind_evidence": ev})
        fleet.save()
        hub.emit({"type": "fleet", "robots": fleet.list(),
                  "roster": fleet.roster_status()})
        return {"ok": True, "rules": loaded}

    # ── 실행 ────────────────────────────────────────────────────────
    def _targets(body: dict) -> List[str]:
        sns = [str(s).lower() for s in (body.get("targets") or []) if str(s).strip()]
        if not sns:
            raise HTTPException(400, "대상 로봇이 없다")
        return sns

    @app.post("/api/run")
    async def api_run(request: Request, body: dict = Body(...)):
        check(request)
        if runner.busy():
            raise HTTPException(409, "이미 실행 중이다. 먼저 정지할 것")
        code = body.get("code") or ""
        if not code.strip():
            raise HTTPException(400, "코드가 비었다")
        return await runner.run(_targets(body), code,
                                codetype=body.get("codetype") or "python",
                                timeout=float(body.get("timeout") or 300))

    @app.post("/api/sync")
    async def api_sync(request: Request, body: dict = Body(...)):
        check(request)
        if runner.busy():
            raise HTTPException(409, "이미 실행 중이다. 먼저 정지할 것")
        code = body.get("code") or ""
        if not code.strip():
            raise HTTPException(400, "코드가 비었다")
        return await runner.sync(_targets(body), code,
                                 ready_timeout=float(body.get("ready_timeout") or 60),
                                 wait=float(body.get("wait") or 120),
                                 timeout=float(body.get("timeout") or 300))

    @app.post("/api/stop")
    async def api_stop(request: Request, body: dict = Body(default={})):
        check(request)
        sns = [str(s).lower() for s in (body.get("targets") or [])]
        if not sns:
            sns = [r["sn"] for r in fleet.list() if r.get("ip")]
        return await runner.stop(sns)

    @app.get("/api/output/{sn}")
    async def api_output(request: Request, sn: str):
        """로봇 한 대의 전체 로그. 화면에서 펼칠 때만 부른다."""
        check(request)
        key = sn.lower()
        job = runner.job
        rec = (job.records.get(key) if job else None)
        if rec is None:
            rec = runner.last_records.get(key, "")
        return {"sn": sn.lower(), "record": rec}

    return app
