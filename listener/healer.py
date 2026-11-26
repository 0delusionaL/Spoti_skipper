"""Автопочинка Spicetify после обновления Spotify.

Spotify при каждом обновлении стирает изменения Spicetify, и расширение пропадает.
Признак: Spotify запущен, а расширение так и не подключилось к слушателю.
Тогда по очереди пробуем:
    spicetify backup apply            — обычный случай после обновления
    spicetify restore backup apply    — если старая резервная копия мешает
    spicetify upgrade + restore backup apply — если сам Spicetify устарел для новой версии Spotify
Обновления Spotify не блокируются.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

EXTENSION_NAME = "spoti-skipper.js"
EXTENSION_SRC = Path(__file__).resolve().parent.parent / "extension" / EXTENSION_NAME

HEAL_STEPS = [
    ["backup", "apply"],
    ["restore", "backup", "apply"],
    ["upgrade"],
    ["restore", "backup", "apply"],
]

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # чтобы не мигала консоль под pythonw


# ---------- взаимодействие с системой ----------
def spicetify_exe() -> Optional[str]:
    found = shutil.which("spicetify")
    if found:
        return found
    candidates = [Path.home() / ".spicetify" / "spicetify"]
    if os.environ.get("LOCALAPPDATA"):
        candidates.insert(0, Path(os.environ["LOCALAPPDATA"]) / "spicetify" / "spicetify.exe")
    return next((str(c) for c in candidates if c.exists()), None)


def run_spicetify(args: list[str], timeout: int = 300) -> tuple[int, str]:
    exe = spicetify_exe()
    if not exe:
        return 127, "spicetify не найден"
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=timeout, creationflags=_NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "spicetify не ответил вовремя"
    except OSError as e:
        return 126, str(e)


def spotify_running() -> bool:
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Spotify.exe", "/NH"], capture_output=True,
                                 text=True, errors="replace", creationflags=_NO_WINDOW, timeout=10).stdout
            return "spotify.exe" in out.lower()
        return subprocess.run(["pgrep", "-ix", "spotify"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_extension_installed(run: Callable[[list[str]], tuple[int, str]] = run_spicetify) -> None:
    """Файл расширения на месте и прописан в конфиге Spicetify (на случай переустановки Spicetify)."""
    code, out = run(["path", "userdata"])
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    userdata = Path(lines[-1]) if code == 0 and lines else None
    if not userdata or not userdata.exists():
        appdata = os.environ.get("APPDATA")
        userdata = Path(appdata) / "spicetify" if appdata else Path.home() / ".config" / "spicetify"
    ext_dir = userdata / "Extensions"
    target = ext_dir / EXTENSION_NAME
    if EXTENSION_SRC.exists() and (not target.exists() or target.read_bytes() != EXTENSION_SRC.read_bytes()):
        ext_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EXTENSION_SRC, target)
    run(["config", "extensions", EXTENSION_NAME])


def looks_ok(code: int, out: str) -> bool:
    low = out.lower()
    return code == 0 and "error" not in low and "✘" not in out


# ---------- логика ----------
class Healer:
    """Вызывай tick() раз в несколько секунд."""

    def __init__(
        self,
        is_running: Callable[[], bool] = spotify_running,
        connected: Callable[[], bool] = lambda: False,
        run: Callable[[list[str]], tuple[int, str]] = run_spicetify,
        notify: Callable[[str], None] = lambda _m: None,
        log: Callable[[str], None] = lambda _m: None,
        prepare: Optional[Callable[[], None]] = None,
        grace_sec: float = 75.0,       # столько ждём подключения расширения после запуска Spotify
        retry_after_sec: float = 1800.0,  # не чиним чаще раза в 30 минут, если не помогло
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.is_running, self.connected, self.run = is_running, connected, run
        self.notify, self.log, self.now = notify, log, now
        self.prepare = prepare if prepare is not None else (lambda: ensure_extension_installed(run))
        self.grace, self.retry_after = grace_sec, retry_after_sec
        self.missing_since: Optional[float] = None
        self.last_heal: Optional[float] = None
        self.warned = False
        self.busy = False

    def tick(self) -> None:
        if self.busy:
            return
        if self.connected():
            self.missing_since = None
            self.warned = False
            return
        if not self.is_running():
            self.missing_since = None
            return
        t = self.now()
        if self.missing_since is None:
            self.missing_since = t
            return
        if t - self.missing_since < self.grace:
            return
        if self.last_heal is None or t - self.last_heal >= self.retry_after:
            self.heal()
            self.missing_since = self.now()
        elif not self.warned:
            self.warned = True
            self.notify("Не получилось вернуть расширение после обновления Spotify. "
                        "Попробуй вручную: spicetify restore backup apply")

    def heal(self, manual: bool = False) -> bool:
        self.busy = True
        self.last_heal = self.now()
        try:
            self.log("Расширение не подключилось — похоже, Spotify обновился. Восстанавливаю Spicetify…")
            if not manual:
                self.notify("Spotify обновился — восстанавливаю Spicetify, Spotify перезапустится.")
            try:
                self.prepare()
            except Exception as e:  # noqa: BLE001
                self.log(f"  не удалось проверить файл расширения: {e!r}")
            for step in HEAL_STEPS:
                code, out = self.run(step)
                self.log(f"  spicetify {' '.join(step)} -> {code}: {out.strip()[-300:]}")
                if code == 127:
                    self.notify("Spicetify не найден. Установи его: spicetify.app")
                    return False
                if step[0] != "upgrade" and looks_ok(code, out):
                    self.log("  готово")
                    self.notify("Spicetify восстановлен после обновления Spotify ✔")
                    return True
            self.notify("Не получилось восстановить Spicetify автоматически. Подробности — «Открыть лог».")
            return False
        finally:
            self.busy = False
