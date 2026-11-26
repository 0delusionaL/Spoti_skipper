import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "listener"))

from healer import HEAL_STEPS, Healer, looks_ok  # noqa: E402


class World:
    def __init__(self, results=None):
        self.t = 0.0
        self.running = True
        self.connected = False
        self.calls = []
        self.notes = []
        self.results = results or {}

    def run(self, args):
        self.calls.append(" ".join(args))
        return self.results.get(" ".join(args), (0, "success"))

    def healer(self, **kw):
        return Healer(is_running=lambda: self.running, connected=lambda: self.connected, run=self.run,
                      notify=self.notes.append, prepare=lambda: None, now=lambda: self.t, **kw)


def advance(h, w, seconds, step=5):
    for _ in range(int(seconds / step)):
        w.t += step
        h.tick()


def test_no_heal_when_extension_connects():
    w = World(); h = w.healer()
    advance(h, w, 20)
    w.connected = True
    advance(h, w, 300)
    assert w.calls == []


def test_no_heal_when_spotify_closed():
    w = World(); w.running = False; h = w.healer()
    advance(h, w, 600)
    assert w.calls == []


def test_heals_with_backup_apply_after_grace():
    w = World(); h = w.healer(grace_sec=75)
    advance(h, w, 60)
    assert w.calls == []
    advance(h, w, 30)
    assert w.calls == ["backup apply"]
    assert any("восстановлен" in n for n in w.notes)


def test_falls_back_to_restore_then_upgrade():
    w = World(results={"backup apply": (1, "error: mismatch"),
                       "restore backup apply": (0, "✘ Spotify version not supported")})
    h = w.healer()
    assert h.heal() is False
    assert w.calls == [" ".join(s) for s in HEAL_STEPS]


def test_upgrade_then_restore_succeeds():
    calls = {"n": 0}
    w = World()

    def run(args):
        w.calls.append(" ".join(args))
        if args == ["restore", "backup", "apply"]:
            calls["n"] += 1
            return (0, "ok") if calls["n"] == 2 else (1, "error")
        if args == ["backup", "apply"]:
            return (1, "error")
        return (0, "upgraded")
    w.run = run
    h = w.healer()
    assert h.heal() is True
    assert w.calls[-2:] == ["upgrade", "restore backup apply"]


def test_does_not_loop_when_heal_fails():
    w = World(results={k: (1, "error") for k in ("backup apply", "restore backup apply")})
    h = w.healer(grace_sec=75, retry_after_sec=1800)
    advance(h, w, 600)
    assert w.calls.count("backup apply") == 1         # одна попытка за полчаса
    assert sum("вручную" in n for n in w.notes) == 1   # и одно предупреждение
    advance(h, w, 1800)
    assert w.calls.count("backup apply") == 2


def test_spicetify_missing():
    w = World(results={"backup apply": (127, "spicetify не найден")})
    h = w.healer()
    assert h.heal() is False and w.calls == ["backup apply"]
    assert any("не найден" in n for n in w.notes)


def test_looks_ok():
    assert looks_ok(0, "Applied successfully")
    assert not looks_ok(1, "")
    assert not looks_ok(0, "error: something")
