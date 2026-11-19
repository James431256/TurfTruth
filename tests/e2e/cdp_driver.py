"""Playwright-compatible headless Chrome driver over --remote-debugging-pipe."""

import base64
import json
import mimetypes
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Any

_CLIP_JS = (
    "(() => { window.__clipText = ''; const c = { writeText: async (t) => "
    "{ window.__clipText = String(t); }, readText: async () => window.__clipText || '' }; "
    "try { Object.defineProperty(navigator, 'clipboard', { value: c, configurable: true }); } "
    "catch (_) { navigator.clipboard.writeText = c.writeText; "
    "navigator.clipboard.readText = c.readText; } })();"
)
_RESOLVE_JS = (
    "(steps) => { let nodes = [document]; for (const [sel, idx] of steps) { "
    "const found = []; for (const n of nodes) found.push(...n.querySelectorAll(sel)); "
    "nodes = idx !== null ? (found[idx] ? [found[idx]] : []) : found; } return nodes; }"
)


class CDPLocator:
    """Playwright-compatible Locator backed by Chrome DevTools Protocol."""

    def __init__(self, page: "CDPPage", steps: list[tuple[str, int | None]]) -> None:
        self._page, self._steps = page, steps

    @property
    def first(self) -> "CDPLocator":
        return self.nth(0)

    def nth(self, index: int) -> "CDPLocator":
        return CDPLocator(self._page, [*self._steps[:-1], (self._steps[-1][0], index)])

    def locator(self, selector: str) -> "CDPLocator":
        return CDPLocator(self._page, [*self._steps, (selector, None)])

    def _eval(self, body: str, arg: Any = None) -> Any:
        s_json, a_json = json.dumps(self._steps), json.dumps(arg)
        expr = f"const nodes = ({_RESOLVE_JS})({s_json}); const el = nodes[0]; const arg = {a_json}; {body}"
        return self._page.evaluate(f"(() => {{ {expr} }})()")

    def count(self) -> int:
        return int(self._eval("return nodes.length;") or 0)

    def wait_for(self, timeout: float = 5.0) -> "CDPLocator":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.count() > 0:
                return self
            time.sleep(0.04)
        raise AssertionError(f"Timeout waiting for {self._steps}")

    def click(self) -> None:
        self.wait_for()._eval("el.click();")
        self._page.wait_for_idle()

    def dblclick(self) -> None:
        self.wait_for()._eval("el.click(); el.click();")
        self._page.wait_for_idle()

    def fill(self, value: str) -> None:
        self.wait_for()._eval(
            "el.value = String(arg); el.dispatchEvent(new Event('input', {bubbles: true}));"
            "el.dispatchEvent(new Event('change', {bubbles: true}));",
            str(value),
        )
        self._page.wait_for_idle()

    def uncheck(self) -> None:
        self.wait_for()._eval("if (el.checked) el.click();")
        self._page.wait_for_idle()

    def set_input_files(self, file_path: str | Path) -> None:
        p = Path(file_path)
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        self.wait_for()._eval(
            "const b = Uint8Array.from(atob(arg.b64), c => c.charCodeAt(0));"
            "const dt = new DataTransfer();"
            "dt.items.add(new File([b], arg.name, {type: arg.mime}));"
            "el.files = dt.files; el.dispatchEvent(new Event('change', {bubbles: true}));",
            {"b64": b64, "name": p.name, "mime": mime},
        )
        self._page.wait_for_idle()

    def inner_text(self) -> str:
        return str(self.wait_for()._eval("return el ? (el.innerText ?? el.textContent ?? '') : '';") or "")

    def input_value(self) -> str:
        return str(self.wait_for()._eval("return el ? String(el.value ?? '') : '';") or "")

    def is_visible(self) -> bool:
        return bool(
            self._eval(
                "if (!el || el.hidden) return false; const st = getComputedStyle(el);"
                "if (st.display === 'none' || st.visibility === 'hidden') return false;"
                "const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0;"
            )
        )


class CDPPage:
    """Headless Google Chrome page controlled over --remote-debugging-pipe."""

    def __init__(self) -> None:
        c2b_r, self._w = os.pipe()
        self._r, b2c_w = os.pipe()
        cmd = ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--remote-debugging-pipe", "about:blank"]
        self._proc = subprocess.Popen(
            cmd,
            preexec_fn=lambda: (os.dup2(c2b_r, 3), os.dup2(b2c_w, 4)),
            pass_fds=(3, 4),
            stderr=subprocess.DEVNULL,
        )
        os.close(c2b_r)
        os.close(b2c_w)
        self._buf, self._msg_id, self.console_errors, self._sid = b"", 0, [], ""
        targets = self._call("Target.getTargets")["targetInfos"]
        t_id = next(t["targetId"] for t in targets if t["type"] == "page")
        self._sid = self._call("Target.attachToTarget", {"targetId": t_id, "flatten": True})["sessionId"]
        for dom in ("Page", "DOM", "Runtime", "Log"):
            self._call(f"{dom}.enable")
        self._call("Page.addScriptToEvaluateOnNewDocument", {"source": _CLIP_JS})
        self.set_viewport_size({"width": 1280, "height": 900})

    def _call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._msg_id += 1
        req_id = self._msg_id
        payload: dict[str, Any] = {"id": req_id, "method": method, "params": params or {}}
        if self._sid:
            payload["sessionId"] = self._sid
        os.write(self._w, json.dumps(payload).encode("utf-8") + b"\x00")
        while True:
            while b"\x00" in self._buf:
                raw, self._buf = self._buf.split(b"\x00", 1)
                if not raw:
                    continue
                msg = json.loads(raw.decode("utf-8"))
                m, p = msg.get("method", ""), msg.get("params", {})
                if m == "Runtime.consoleAPICalled" and p.get("type") == "error":
                    self.console_errors.append(" ".join(str(a.get("value", "")) for a in p.get("args", [])))
                elif m == "Runtime.exceptionThrown":
                    self.console_errors.append(str(p.get("exceptionDetails", {}).get("text", "error")))
                if msg.get("id") == req_id:
                    return msg.get("result", {})
            if not select.select([self._r], [], [], 10.0)[0]:
                raise TimeoutError(f"CDP timeout: {method}")
            self._buf += os.read(self._r, 65536)

    @property
    def context(self) -> "CDPPage":
        return self

    def grant_permissions(self, _perms: list[str], **_kw: Any) -> None:
        return None

    def goto(self, url: str) -> None:
        self._call("Page.navigate", {"url": url})
        for _ in range(80):
            if self.evaluate("document.readyState") == "complete":
                break
            time.sleep(0.05)
        self.wait_for_idle(0.18)

    def wait_for_idle(self, delay: float = 0.14) -> None:
        time.sleep(delay)

    def set_viewport_size(self, size: dict[str, int]) -> None:
        w, h = int(size["width"]), int(size["height"])
        self._call("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": w < 600})

    def locator(self, selector: str) -> CDPLocator:
        return CDPLocator(self, [(selector, None)])

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        expr = expression.strip()
        if expr.startswith("() =>") or expr.startswith("(arg) =>") or expr.startswith("async () =>"):
            expr = f"({expr})({json.dumps(arg)})"
        res = self._call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        return res.get("result", {}).get("value")

    def screenshot(self, path: str | Path, full_page: bool = False) -> bytes:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        res = self._call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": full_page})
        raw = base64.b64decode(res["data"])
        out.write_bytes(raw)
        return raw

    def close(self) -> None:
        self._proc.terminate()
        self._proc.wait(timeout=3)
        os.close(self._r)
        os.close(self._w)
