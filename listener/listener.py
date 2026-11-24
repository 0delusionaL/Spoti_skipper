"""Spoti Skipper — голосовой слушатель.

Слушает микрофон офлайн через Vosk, распознаёт команды и рассылает их
расширению Spicetify по WebSocket (ws://127.0.0.1:<port>).

Запуск:
    python listener.py                 # голосом
    python listener.py --keyboard      # вводить команды с клавиатуры (для проверки)
    python listener.py --debug         # печатать всё, что услышано (подбирать слова)
    python listener.py --list-devices  # показать микрофоны
"""

from __future__ import annotations

import argparse
import asyncio
import json
import queue
import sys
import threading
import time
from pathlib import Path

from gate import SilenceGate
from commands import DEFAULT_COMMANDS, DEFAULT_WAKE_WORDS, CommandParser, merge_commands, words_from_vosk

HERE = Path(__file__).resolve().parent
SAMPLE_RATE = 16000

DEFAULT_CONFIG = {
    "port": 8974,
    "langs": ["ru", "en-us"],  # модели Vosk, слушают одновременно; ["ru"] — только русский (меньше нагрузка)
    "model_paths": [],         # пути к своим моделям; пусто = скачать маленькие автоматически
    "require_wake_word": True,  # False = без «Джарвис» (музыка из колонок может триггерить команды)
    "min_conf": 0.5,
    "fuzzy": 0.8,               # 1.0 = только точные совпадения слов
    "cooldown_sec": 1.2,
    "skip_silence": True,       # не нагружать процессор в тишине; False — слушать всё подряд
    "silence_ratio": 2.0,       # голос = звук в N раз громче фона; плохо слышит — поставь 1.5
    "device": None,          # номер микрофона из --list-devices; null = по умолчанию
    "extra_commands": {},    # {"next": ["врубай следующий"]} — сверх commands.json
}


def load_config(path: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        with path.open(encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


class Hub:
    """Хранит подключённые расширения и рассылает им команды."""

    def __init__(self) -> None:
        self.clients: set = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def handler(self, ws) -> None:
        self.clients.add(ws)
        log(f"Spotify подключился ({len(self.clients)})")
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if msg.get("type") == "ack":
                    log(f"  ✓ {msg.get('command')}  {msg.get('track') or ''}")
                elif msg.get("type") == "hello":
                    log(f"  расширение v{msg.get('version')}")
        except Exception:
            pass
        finally:
            self.clients.discard(ws)
            log("Spotify отключился")

    async def _broadcast(self, payload: str) -> None:
        if not self.clients:
            log("  (Spotify не подключён — команда никуда не ушла)")
            return
        await asyncio.gather(*(c.send(payload) for c in list(self.clients)), return_exceptions=True)

    def send_command(self, command: str, text: str = "") -> None:
        """Потокобезопасно: можно звать из потока распознавания."""
        payload = json.dumps({"type": "command", "command": command, "text": text}, ensure_ascii=False)
        assert self.loop is not None
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def voice_loop(hub: Hub, cfg: dict, parser: CommandParser, stop: threading.Event, debug: bool = False) -> None:
    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)
    # Старый формат конфига: "lang": "ru", "model_path": "..."
    langs = cfg.get("langs") or [cfg.get("lang", "ru")]
    if isinstance(langs, str):
        langs = [langs]
    paths = cfg.get("model_paths") or ([cfg["model_path"]] if cfg.get("model_path") else [])

    recognizers = []  # (название, распознаватель)
    for src in (paths or langs):
        log(f"Загружаю модель Vosk «{src}» (первый запуск скачает ~40–50 МБ)...")
        model = Model(src) if paths else Model(lang=src)
        # Без ограничения словаря: «Джарвиса» нет в словаре модели, ловим похожие слова нечётко.
        rec = KaldiRecognizer(model, SAMPLE_RATE)
        rec.SetWords(True)
        recognizers.append((Path(src).name if paths else src, rec))

    audio: queue.Queue[bytes] = queue.Queue()

    def on_audio(indata, frames, t, status):  # noqa: ARG001
        audio.put(bytes(indata))

    last = 0.0

    def handle(name: str, raw_result: str) -> None:
        nonlocal last
        result = json.loads(raw_result)
        text = result.get("text", "")
        if not text or text == "[unk]":
            return
        cmd = parser.parse(words_from_vosk(result))
        if debug:
            log(f"   [{name}] слышу: «{text}»" + ("" if cmd else "  (не команда)"))
        if not cmd:
            return
        now = time.monotonic()
        if now - last < cfg["cooldown_sec"]:
            return  # одну и ту же фразу могли поймать обе модели
        last = now
        log(f"🎤 [{name}] «{text}» → {cmd}")
        hub.send_command(cmd, text)

    gate = SilenceGate(ratio=float(cfg["silence_ratio"])) if cfg["skip_silence"] else None
    gate_state = None

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000, dtype="int16",
                           channels=1, callback=on_audio, device=cfg["device"]):
        hint = f"«{parser.wake_words[0].capitalize()}, некст»" if parser.wake_words else "«некст»"
        log(f"Слушаю. Скажи, например, {hint}. Ctrl+C — выход.")
        while not stop.is_set():
            try:
                data = audio.get(timeout=0.5)
            except queue.Empty:
                continue

            chunks, phrase_ended = gate.feed(data) if gate else ([data], False)
            if gate and debug:
                state = "шумно, слушаю всё" if gate.bypass else ("голос" if gate.open else "тишина")
                if state != gate_state:
                    log(f"   фильтр: {state}")
                    gate_state = state

            for chunk in chunks:
                for name, rec in recognizers:
                    if rec.AcceptWaveform(chunk):
                        handle(name, rec.Result())
            if phrase_ended:
                # Дальше звук не пойдёт — забираем то, что модели успели услышать.
                for name, rec in recognizers:
                    handle(name, rec.FinalResult())


def keyboard_loop(hub: Hub, parser: CommandParser, stop: threading.Event) -> None:
    names = ", ".join(parser.commands)
    log(f"Режим клавиатуры. Вводи команду ({names}) или фразу. Пустая строка — выход.")
    p = CommandParser(commands=parser.commands, wake_words=[], min_conf=0)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            break
        cmd = line if line in parser.commands else p.parse(line)
        if cmd:
            hub.send_command(cmd, line)
        else:
            log("  не понял")
    stop.set()


async def main_async(args: argparse.Namespace) -> None:
    import websockets

    cfg = load_config(Path(args.config))
    if args.device is not None:
        cfg["device"] = args.device
    parser = CommandParser(
        commands=merge_commands(DEFAULT_COMMANDS, cfg.get("extra_commands")),
        wake_words=DEFAULT_WAKE_WORDS if cfg["require_wake_word"] else [],
        min_conf=float(cfg["min_conf"]),
        fuzzy=float(cfg["fuzzy"]),
    )

    hub = Hub()
    hub.loop = asyncio.get_running_loop()
    stop = threading.Event()

    async with websockets.serve(hub.handler, "127.0.0.1", int(cfg["port"])):
        log(f"WebSocket: ws://127.0.0.1:{cfg['port']}")
        target = keyboard_loop if args.keyboard else voice_loop
        targs = (hub, parser, stop) if args.keyboard else (hub, cfg, parser, stop, args.debug)
        worker = threading.Thread(target=target, args=targs, daemon=True)
        worker.start()
        try:
            while worker.is_alive():
                await asyncio.sleep(0.3)
        finally:
            stop.set()


def main() -> None:
    ap = argparse.ArgumentParser(description="Голосовое управление Spotify через Spicetify")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--keyboard", action="store_true", help="команды с клавиатуры вместо микрофона")
    ap.add_argument("--device", type=int, help="номер микрофона")
    ap.add_argument("--debug", action="store_true", help="печатать всё распознанное")
    ap.add_argument("--list-devices", action="store_true")
    args = ap.parse_args()

    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        return
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        log("Пока!")


if __name__ == "__main__":
    main()
