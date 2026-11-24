import math
import random
import sys
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "listener"))

from gate import SilenceGate, rms_int16  # noqa: E402

N = 4000  # 0.25 с при 16 кГц


def noise(level: float, seed: int = 0) -> bytes:
    rnd = random.Random(seed)
    return array("h", (max(-32768, min(32767, int(rnd.gauss(0, level)))) for _ in range(N))).tobytes()


def tone(amp: float) -> bytes:
    return array("h", (int(amp * math.sin(2 * math.pi * 300 * i / 16000)) for i in range(N))).tobytes()


def run(gate, chunks):
    passed, closes = [], 0
    for c in chunks:
        out, closed = gate.feed(c)
        passed += out
        closes += closed
    return passed, closes


def test_rms():
    assert rms_int16(b"") == 0
    assert abs(rms_int16(tone(1000)) - 1000 / math.sqrt(2)) < 5


def test_silence_is_dropped():
    g = SilenceGate()
    passed, _ = run(g, [noise(30, i) for i in range(40)])
    assert passed == []


def test_quiet_bad_mic_speech_passes():
    # Плохой микрофон: фон ~40, голос всего ~250
    g = SilenceGate()
    quiet = [noise(40, i) for i in range(20)]
    speech = [tone(350) for _ in range(6)]
    passed, closes = run(g, quiet + speech + [noise(40, 99 + i) for i in range(12)])
    for s in speech:
        assert s in passed
    assert closes == 1


def test_preroll_keeps_start_of_word():
    g = SilenceGate(preroll_chunks=3)
    quiet = [noise(30, i) for i in range(20)]
    _, _ = run(g, quiet)
    out, _ = g.feed(tone(3000))
    assert len(out) == 4 and out[:3] == quiet[-3:]


def test_hangover_lets_phrase_finish():
    g = SilenceGate(hangover_chunks=6)
    run(g, [noise(30, i) for i in range(20)])
    g.feed(tone(3000))
    tail = [noise(30, 50 + i) for i in range(6)]
    passed, closes = run(g, tail[:5])
    assert len(passed) == 5 and closes == 0    # хвост фразы пропускаем
    out, closed = g.feed(tail[5])
    assert out == [tail[5]] and closed is True  # последний кусок тоже, и просим FinalResult
    out, closed = g.feed(noise(30, 77))
    assert out == [] and closed is False        # дальше тишина отбрасывается


def test_constant_music_switches_to_bypass():
    # Музыка из колонок, громкость «плавает» -> фильтр сдаётся и пропускает всё
    g = SilenceGate()
    run(g, [noise(30, i) for i in range(8)])
    music = [tone(2000 + 1500 * (i % 2)) for i in range(120)]
    passed, _ = run(g, music)
    assert g.bypass
    assert passed[-40:] == music[-40:]


def test_bypass_turns_off_when_quiet_again():
    g = SilenceGate()
    run(g, [tone(2000 + 1500 * (i % 2)) for i in range(120)])
    assert g.bypass
    run(g, [noise(30, i) for i in range(120)])
    assert not g.bypass
