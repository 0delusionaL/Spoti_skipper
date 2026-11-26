"""Spoti Skipper в системном трее — без окна консоли.

Запускается через «Spoti Skipper.vbs» (pythonw, без консоли).
Всё, что раньше писалось в консоль, теперь пишется в listener.log.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOG_FILE = HERE / "listener.log"
LAUNCHER = ROOT / "Spoti Skipper.vbs"
APP = "Spoti Skipper"


def _redirect_output() -> None:
    """У pythonw нет консоли: sys.stdout = None, и любой print падал бы."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.unlink()  # не даём логу разрастись
    except OSError:
        pass
    f = open(LOG_FILE, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = f
    sys.stderr = f


_redirect_output()

import asyncio  # noqa: E402

import pystray  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from healer import Healer  # noqa: E402
from listener import Hub, load_config, log, run_service, wake_words  # noqa: E402

LABELS = {
    "next": "Следующий трек", "previous": "Предыдущий трек", "restart": "Сначала",
    "pause": "Пауза", "play": "Играю", "volume_up": "Громче", "volume_down": "Тише",
    "like": "В любимые", "unlike": "Убрано из любимых", "shuffle": "Перемешивание", "repeat": "Повтор",
}


# ---------- иконка ----------
def make_icon(color: str) -> Image.Image:
    """Микрофон на круглом фоне. Цвет = состояние."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, size - 2, size - 2), fill=color)
    white = (255, 255, 255, 255)
    d.rounded_rectangle((24, 12, 40, 38), radius=8, fill=white)          # капсула микрофона
    d.arc((17, 22, 47, 46), start=0, end=180, fill=white, width=4)        # дуга-держатель
    d.line((32, 46, 32, 52), fill=white, width=4)                          # ножка
    d.line((24, 53, 40, 53), fill=white, width=4)                          # подставка
    return img


ICONS = {
    "loading": make_icon("#6b7280"),   # серый: загружается
    "ready": make_icon("#1db954"),     # зелёный: слушаю, Spotify подключён
    "waiting": make_icon("#d4a017"),   # жёлтый: слушаю, Spotify не подключён
    "paused": make_icon("#4b5563"),    # тёмно-серый: пауза
    "error": make_icon("#dc2626"),     # красный: ошибка
}


# ---------- автозапуск ----------
def startup_file() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup" / f"{APP}.vbs"


def autostart_enabled() -> bool:
    return startup_file().exists()


def set_autostart(on: bool) -> None:
    f = startup_file()
    if on:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            'CreateObject("WScript.Shell").Run """wscript.exe"" ""' + str(LAUNCHER) + '""", 0, False\r\n',
            encoding="utf-16",
        )
    elif f.exists():
        f.unlink()


def open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", str(path)])


# ---------- приложение ----------
class TrayApp:
    def __init__(self) -> None:
        self.cfg = load_config(HERE / "config.json")
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.ready = False
        self.spotify = 0
        self.error: str | None = None
        self.last = "—"
        self.restart_requested = False
        self.thread: threading.Thread | None = None
        self.hub = Hub(on_change=self._on_spotify, on_command=self._on_command)
        self.healer = Healer(connected=lambda: self.spotify > 0, notify=self.notify, log=log)
        self.icon = pystray.Icon(APP, ICONS["loading"], f"{APP}: загружаю модели…", menu=self._menu())

    # --- состояние ---
    def status_text(self) -> str:
        if self.error:
            return f"Ошибка: {self.error}"
        if not self.ready:
            return "Загружаю модели…"
        if self.paused.is_set():
            return "На паузе"
        return "Слушаю, Spotify подключён" if self.spotify else "Слушаю, жду Spotify"

    def refresh(self) -> None:
        if self.error:
            key = "error"
        elif not self.ready:
            key = "loading"
        elif self.paused.is_set():
            key = "paused"
        else:
            key = "ready" if self.spotify else "waiting"
        self.icon.icon = ICONS[key]
        self.icon.title = f"{APP}: {self.status_text()}"[:127]
        self.icon.update_menu()

    def notify(self, text: str) -> None:
        try:
            self.icon.notify(text, APP)
        except Exception:  # noqa: BLE001  уведомления есть не везде
            pass

    def _on_spotify(self, n: int) -> None:
        self.spotify = n
        self.refresh()

    def _on_command(self, cmd: str, text: str) -> None:
        self.last = f"{LABELS.get(cmd, cmd)} («{text}»)"
        self.refresh()

    def _on_ready(self) -> None:
        self.ready = True
        self.refresh()
        wake = wake_words(self.cfg)[0].capitalize() if self.cfg.get("require_wake_word", True) else ""
        self.notify(f"Слушаю. Скажи «{wake + ', ' if wake else ''}некст».")

    # --- меню ---
    def _menu(self) -> pystray.Menu:
        item = pystray.MenuItem
        return pystray.Menu(
            item(lambda _: self.status_text(), None, enabled=False),
            item(lambda _: f"Последняя команда: {self.last}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("Пауза", self.toggle_pause, checked=lambda _: self.paused.is_set(), default=True),
            pystray.Menu.SEPARATOR,
            item("Настройки: активатор и фразы для скипа…", self.open_settings),
            item("Изменить все фразы (commands.json)", lambda: open_path(HERE / "commands.json")),
            item("Все настройки (config.json)", lambda: open_path(HERE / "config.json")),
            item("Починить Spicetify сейчас", self.heal_now),
            item("Открыть лог", lambda: open_path(LOG_FILE)),
            item("Перезапустить (применить изменения)", self.restart),
            pystray.Menu.SEPARATOR,
            item("Запускать вместе с Windows", self.toggle_autostart,
                 checked=lambda _: autostart_enabled(), visible=sys.platform == "win32"),
            item("Выход", self.quit),
        )

    def toggle_pause(self) -> None:
        if self.paused.is_set():
            self.paused.clear()
        else:
            self.paused.set()
        log("пауза" if self.paused.is_set() else "снова слушаю")
        self.refresh()

    def toggle_autostart(self) -> None:
        try:
            set_autostart(not autostart_enabled())
        except OSError as e:
            self.notify(f"Не получилось изменить автозапуск: {e}")
        self.refresh()

    def open_settings(self) -> None:
        def worker() -> None:
            try:
                rc = subprocess.run([sys.executable, str(HERE / "settings.py")], cwd=str(HERE)).returncode
            except OSError as e:
                self.notify(f"Не открылись настройки: {e}")
                return
            if rc == 0:
                self.notify("Настройки сохранены, перезапускаюсь…")
                self.restart()
            elif rc == 3:
                self.notify("Окно настроек не открылось: в Python нет tkinter. "
                            "Открываю config.json — активатор в поле \"wake_words\".")
                open_path(HERE / "config.json")
        threading.Thread(target=worker, daemon=True).start()

    def heal_now(self) -> None:
        threading.Thread(target=lambda: self.healer.heal(manual=True), daemon=True).start()

    def _heal_loop(self) -> None:
        while not self.stop.wait(5):
            if self.cfg.get("auto_heal", True):
                try:
                    self.healer.tick()
                except Exception as e:  # noqa: BLE001
                    log(f"автопочинка: {e!r}")

    def restart(self) -> None:
        self.restart_requested = True
        self.quit()

    def quit(self) -> None:
        self.stop.set()
        self.icon.stop()

    # --- фон ---
    def _service(self) -> None:
        try:
            asyncio.run(run_service(self.cfg, self.stop, paused=self.paused, hub=self.hub, on_ready=self._on_ready))
        except OSError as e:
            if getattr(e, "errno", None) in (98, 10048) or "address" in str(e).lower():
                self.error = "уже запущен (порт занят)"
                self.notify("Spoti Skipper уже работает — ищи иконку в трее.")
            else:
                self.error = str(e)[:80]
                self.notify(f"Ошибка: {e}")
            log(f"ОШИБКА: {e!r}")
        except Exception as e:  # noqa: BLE001  нет микрофона, не скачалась модель и т.п.
            self.error = str(e)[:80] or e.__class__.__name__
            log(f"ОШИБКА: {e!r}")
            self.notify(f"Ошибка: {self.error}. Подробности — «Открыть лог».")
        if not self.stop.is_set():
            self.refresh()

    def _setup(self, icon: pystray.Icon) -> None:
        icon.visible = True
        self.thread = threading.Thread(target=self._service, daemon=True)
        self.thread.start()
        threading.Thread(target=self._heal_loop, daemon=True).start()

    def run(self) -> None:
        log("=== старт в трее ===")
        self.icon.run(setup=self._setup)
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)  # дождаться, пока освободится порт
        log("=== выход ===")
        if self.restart_requested:
            launch_detached()


def launch_detached() -> None:
    if sys.platform == "win32" and LAUNCHER.exists():
        subprocess.Popen(["wscript.exe", str(LAUNCHER)], close_fds=True)
    else:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve())], close_fds=True)


if __name__ == "__main__":
    TrayApp().run()
