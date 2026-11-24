import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "listener"))

from commands import CommandParser, Word, merge_commands, words_from_vosk, DEFAULT_COMMANDS  # noqa: E402


def test_wake_word_required():
    p = CommandParser()
    assert p.parse("дальше") is None
    assert p.parse("музыка дальше") == "next"
    assert p.parse("эй музыка назад") == "previous"


def test_command_before_wake_word_ignored():
    assert CommandParser().parse("дальше музыка") is None


def test_no_wake_word_mode():
    p = CommandParser(wake_word="")
    assert p.parse("скип") == "next"
    assert p.parse("next") == "next"
    assert p.parse("пауза") == "pause"
    assert p.parse("привет") is None


def test_low_confidence_filtered():
    p = CommandParser(min_conf=0.7)
    assert p.parse([Word("музыка", 0.9), Word("дальше", 0.4)]) is None
    assert p.parse([Word("музыка", 0.9), Word("дальше", 0.95)]) == "next"
    assert p.parse([Word("музыка", 0.3), Word("дальше", 0.95)]) is None


def test_unk_and_case():
    p = CommandParser()
    assert p.parse("[unk] МУЗЫКА [unk] Громче") == "volume_up"


def test_vocabulary_contains_wake_word():
    v = CommandParser().vocabulary()
    assert "музыка" in v and "дальше" in v and "skip" in v


def test_words_from_vosk():
    res = {"result": [{"word": "музыка", "conf": 1.0}, {"word": "тише", "conf": 0.8}], "text": "музыка тише"}
    assert CommandParser().parse(words_from_vosk(res)) == "volume_down"
    assert words_from_vosk({"text": "a b"})[1].text == "b"
    assert words_from_vosk({}) == []


def test_merge_custom_synonyms():
    merged = merge_commands(DEFAULT_COMMANDS, {"next": ["некст"], "like": ["сердечко"]})
    p = CommandParser(commands=merged, wake_word="")
    assert p.parse("некст") == "next"
    assert p.parse("сердечко") == "like"
    assert p.parse("дальше") == "next"
    assert "некст" not in DEFAULT_COMMANDS["next"]
