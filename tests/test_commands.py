import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "listener"))

from commands import (  # noqa: E402
    DEFAULT_COMMANDS, CommandParser, Word, merge_commands, words_from_vosk,
)

P = CommandParser()


@pytest.mark.parametrize("phrase,cmd", [
    ("джарвис некст", "next"),
    ("джарвис next", "next"),
    ("jarvis skip", "next"),
    ("джарвис скипни", "next"),
    ("джарвис пропусти эту песню", "next"),
    ("джарвис давай другую", "next"),
    ("джарвис переключи трек", "next"),
    ("джарвис мне не нравится", "next"),
    ("джарвис следующую песню", "next"),
    ("джарвис верни назад", "previous"),
    ("джарвис прошлую песню", "previous"),
    ("джарвис включи сначала", "restart"),
    ("джарвис повтори песню", "restart"),
    ("джарвис поставь на паузу", "pause"),
    ("джарвис выключи музыку", "pause"),
    ("джарвис включи музыку", "play"),
    ("джарвис сними с паузы", "play"),
    ("джарвис сделай погромче", "volume_up"),
    ("джарвис потише", "volume_down"),
    ("джарвис лайкни эту песню", "like"),
    ("джарвис добавь в фавориты", "like"),
    ("джарвис добавь эту песню в избранное", "like"),
    ("джарвис мне нравится", "like"),
    ("джарвис убери лайк", "unlike"),
    ("джарвис убери из избранного", "unlike"),
    ("джарвис поставь на повтор", "repeat"),
    ("джарвис перемешай", "shuffle"),
    ("ну джарвис пожалуйста пропусти", "next"),
])
def test_phrases(phrase, cmd):
    assert P.parse(phrase) == cmd


@pytest.mark.parametrize("heard", ["джервис", "жарвис", "джарвиз", "джарвисс", "джарвес"])
def test_wake_word_misheard_variants(heard):
    assert P.parse(f"{heard} дальше") == "next"


def test_no_wake_word_no_command():
    assert P.parse("некст") is None
    assert P.parse("пропусти эту песню") is None
    assert P.parse("дальше джарвис") is None


def test_command_too_far_from_wake_word():
    p = CommandParser(fuzzy=0.8)
    assert p.parse("джарвис я сегодня гулял по парку и было очень хорошо дальше") is None


def test_known_words_not_fuzzed_into_each_other():
    # «выключи» похоже на «включи», но это разные команды
    assert P.parse("джарвис выключи") == "pause"
    assert P.parse("джарвис включи") == "play"
    # «не нравится» — пропуск, а не лайк
    assert P.parse("джарвис не нравится") == "next"


def test_fuzzy_command_word():
    assert P.parse("джарвис пропустиь") == "next"
    assert CommandParser(fuzzy=1.0).parse("джарвис пропустиь") is None


def test_yo_normalized():
    assert P.parse("джарвис вперёд") == "next"
    assert P.parse("джарвис еще громче") == "volume_up"


def test_low_confidence_filtered():
    p = CommandParser(min_conf=0.7)
    assert p.parse([Word("джарвис", 0.9), Word("дальше", 0.4)]) is None
    assert p.parse([Word("джарвис", 0.9), Word("дальше", 0.95)]) == "next"
    assert p.parse([Word("джарвис", 0.3), Word("дальше", 0.95)]) is None


def test_no_wake_word_mode():
    p = CommandParser(wake_words=[], fuzzy=0.8)
    assert p.parse("скип") == "next"
    assert p.parse("привет") is None


def test_words_from_vosk():
    res = {"result": [{"word": "джарвис", "conf": 1.0}, {"word": "тише", "conf": 0.8}], "text": "джарвис тише"}
    assert P.parse(words_from_vosk(res)) == "volume_down"
    assert words_from_vosk({}) == []


def test_merge_custom_phrases():
    merged = merge_commands(DEFAULT_COMMANDS, {"next": ["врубай следующий"]})
    p = CommandParser(commands=merged)
    assert p.parse("джарвис врубай следующий") == "next"
    assert "врубай следующий" not in DEFAULT_COMMANDS["next"]


def test_every_phrase_resolves_to_its_command():
    # Ни одна фраза из commands.json не должна перехватываться чужой командой.
    p = CommandParser(fuzzy=1.0)
    for cmd, phrases in DEFAULT_COMMANDS.items():
        for ph in phrases:
            assert p.parse(f"джарвис {ph}") == cmd, ph


@pytest.mark.parametrize("phrase,cmd", [
    ("jarvis next song", "next"),
    ("jarvis skip this song", "next"),
    ("jarvis play the next one", "next"),
    ("jarvis i don't like this", "next"),
    ("jarvis play something else", "next"),
    ("jarvis go back", "previous"),
    ("jarvis play the last song", "previous"),
    ("jarvis play it again", "restart"),
    ("jarvis start over", "restart"),
    ("jarvis pause the music", "pause"),
    ("jarvis turn it off", "pause"),
    ("jarvis turn it on", "play"),
    ("jarvis keep playing", "play"),
    ("jarvis turn it up", "volume_up"),
    ("jarvis turn it down", "volume_down"),
    ("jarvis i like this song", "like"),
    ("jarvis add to liked songs", "like"),
    ("jarvis remove from favorites", "unlike"),
    ("jarvis shuffle", "shuffle"),
    ("jarvis put on repeat", "repeat"),
    ("jarvis please skip it", "next"),
    ("джарвис листни", "next"),
    ("джарвис крути по кругу", "repeat"),
    ("джарвис больше не нравится", "unlike"),
    ("джарвис добавь в понравившиеся", "like"),
])
def test_english_and_more_phrases(phrase, cmd):
    assert P.parse(phrase) == cmd


def test_no_duplicate_phrases_across_commands():
    seen = {}
    for cmd, phrases in DEFAULT_COMMANDS.items():
        for ph in phrases:
            assert ph not in seen, f"«{ph}» есть и в {seen[ph]}, и в {cmd}"
            seen[ph] = cmd


@pytest.mark.parametrize("phrase,cmd", [
    ("джарвис далее", "next"),
    ("джарвис на репит", "repeat"),
    ("джарвис поставь на репит", "repeat"),
    ("джарвис ски", "next"),
    ("jarvis ski", "next"),
])
def test_new_phrases(phrase, cmd):
    assert P.parse(phrase) == cmd
