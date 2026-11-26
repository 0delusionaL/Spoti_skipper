import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "listener"))

from commands import CommandParser, DEFAULT_COMMANDS, merge_commands  # noqa: E402
from settings import apply_settings, split_list, wake_words_to_save  # noqa: E402
import listener  # noqa: E402


def test_split_list():
    assert split_list(" Пятница, friday ,,  эй   спотик; пятница") == ["пятница", "friday", "эй спотик"]
    assert split_list("") == []


def test_default_jarvis_stored_as_empty():
    assert wake_words_to_save("Джарвис") == []
    assert wake_words_to_save("джарвис, Jarvis") == []
    assert wake_words_to_save("") == []
    assert wake_words_to_save("Пятница") == ["пятница"]


def test_apply_keeps_other_settings_and_works_end_to_end():
    cfg = {"port": 1, "extra_commands": {"like": ["сердце"]}, "require_wake_word": True}
    new = apply_settings(cfg, "Пятница", "мотай, врубай следующий", True)
    assert new["port"] == 1 and new["extra_commands"]["like"] == ["сердце"]
    assert new["extra_commands"]["next"] == ["мотай", "врубай следующий"]
    full = dict(listener.DEFAULT_CONFIG, **new)
    p = listener.build_parser(full)
    assert p.parse("пятница мотай") == "next"
    assert p.parse("пятница врубай следующий") == "next"
    assert p.parse("пятница сердце") == "like"
    assert p.parse("джарвис мотай") is None


def test_reset_to_jarvis():
    new = apply_settings({"wake_words": ["пятница"]}, "Джарвис", "", True)
    p = listener.build_parser(dict(listener.DEFAULT_CONFIG, **new))
    assert p.parse("джарвис некст") == "next"
    assert p.parse("джервис некст") == "next"   # варианты Джарвиса вернулись
