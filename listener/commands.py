"""Разбор распознанной речи в команды плеера.

Модуль без внешних зависимостей, чтобы его можно было тестировать отдельно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# Команда -> слова, которые её вызывают (RU + EN).
DEFAULT_COMMANDS: dict[str, list[str]] = {
    "next": ["дальше", "следующий", "следующая", "следующую", "скип", "скипни",
             "пропусти", "пропустить", "next", "skip"],
    "previous": ["назад", "предыдущий", "предыдущая", "предыдущую", "верни",
                 "back", "previous"],
    "pause": ["пауза", "стоп", "останови", "pause", "stop"],
    "play": ["играй", "продолжи", "продолжай", "плей", "play", "resume"],
    "volume_up": ["громче", "louder"],
    "volume_down": ["тише", "quieter"],
    "like": ["лайк", "нравится", "like"],
    "shuffle": ["перемешай", "шафл", "shuffle"],
    "repeat": ["повтор", "repeat"],
}


@dataclass
class Word:
    text: str
    conf: float = 1.0


@dataclass
class CommandParser:
    commands: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_COMMANDS))
    # Пустая строка = wake word не нужен (риск ложных срабатываний от самой музыки).
    wake_word: str = "музыка"
    min_conf: float = 0.6

    def __post_init__(self) -> None:
        self.wake_word = (self.wake_word or "").strip().lower()
        self._lookup: dict[str, str] = {}
        for cmd, words in self.commands.items():
            for w in words:
                self._lookup[w.strip().lower()] = cmd

    def vocabulary(self) -> list[str]:
        """Слова для грамматики Vosk (ограничивает распознавание только ими)."""
        vocab = set(self._lookup)
        if self.wake_word:
            vocab.add(self.wake_word)
        return sorted(vocab)

    def parse(self, words: Sequence[Word] | str) -> Optional[str]:
        """Вернёт имя команды или None.

        С wake word команда должна идти ПОСЛЕ него в той же фразе:
        «музыка дальше» -> next, «дальше» -> None.
        """
        if isinstance(words, str):
            words = [Word(t) for t in words.split()]
        tokens = [w.text.strip().lower() for w in words if w.conf >= self.min_conf and w.text.strip()]
        tokens = [t for t in tokens if t != "[unk]"]

        if self.wake_word:
            if self.wake_word not in tokens:
                return None
            tokens = tokens[tokens.index(self.wake_word) + 1:]

        for t in tokens:
            cmd = self._lookup.get(t)
            if cmd:
                return cmd
        return None


def words_from_vosk(result: dict) -> list[Word]:
    """Достаёт слова с уверенностью из JSON-результата Vosk (SetWords(True))."""
    if result.get("result"):
        return [Word(r.get("word", ""), float(r.get("conf", 1.0))) for r in result["result"]]
    return [Word(t) for t in (result.get("text") or "").split()]


def merge_commands(base: dict[str, list[str]], extra: dict[str, Iterable[str]] | None) -> dict[str, list[str]]:
    """Добавляет пользовательские синонимы из config.json к стандартным."""
    merged = {k: list(v) for k, v in base.items()}
    for cmd, words in (extra or {}).items():
        merged.setdefault(cmd, [])
        for w in words:
            if w not in merged[cmd]:
                merged[cmd].append(w)
    return merged
