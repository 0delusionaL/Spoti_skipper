"""Разбор распознанной речи в команды плеера.

Слова и фразы живут в commands.json рядом с этим файлом.
Модуль без внешних зависимостей, чтобы его можно было тестировать отдельно.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Optional, Sequence

COMMANDS_FILE = Path(__file__).resolve().with_name("commands.json")


def load_phrases(path: Path = COMMANDS_FILE) -> tuple[list[str], dict[str, list[str]]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("wake_words", [])), {k: list(v) for k, v in data["commands"].items()}


DEFAULT_WAKE_WORDS, DEFAULT_COMMANDS = load_phrases()


def _norm(text: str) -> str:
    return text.strip().lower().replace("ё", "е")


@dataclass
class Word:
    text: str
    conf: float = 1.0


@dataclass
class CommandParser:
    commands: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_COMMANDS.items()})
    # Пустой список = активатор не нужен (риск ложных срабатываний от самой музыки).
    wake_words: list[str] = field(default_factory=lambda: list(DEFAULT_WAKE_WORDS))
    min_conf: float = 0.5
    fuzzy: float = 0.5        # насколько похожим должно быть слово команды (0..1), 1 = только точное совпадение
    wake_fuzzy: float = 0.7   # то же для «Джарвис»; ниже не надо — иначе будит любое слово из песни
    max_gap: int = 6          # команда должна прозвучать не дальше N слов после активатора

    def __post_init__(self) -> None:
        self.wake_words = [" ".join(_norm(w).split()) for w in self.wake_words if w.strip()]
        # Активатор может быть из нескольких слов: «эй спотик».
        self._wake_phrases = [w.split() for w in self.wake_words]
        # (команда, фраза-токены), длинные фразы первыми: «убери лайк» важнее «лайк».
        self._phrases: list[tuple[str, list[str]]] = []
        for cmd, phrases in self.commands.items():
            for p in phrases:
                toks = _norm(p).split()
                if toks:
                    self._phrases.append((cmd, toks))
        self._phrases.sort(key=lambda x: -len(x[1]))
        # Все «настоящие» слова из фраз: их нечётко не подменяем
        # (иначе «выключи» превратилось бы во «включи»).
        self._known = {t for _, toks in self._phrases for t in toks} | {t for w in self._wake_phrases for t in w}

    # ---- сравнение слов ----
    def _similar(self, token: str, target: str) -> bool:
        if token == target:
            return True
        if token in self._known or len(target) < 4 or self.fuzzy >= 1:
            return False
        return SequenceMatcher(None, token, target).ratio() >= self.fuzzy

    def _wake_token(self, token: str, target: str) -> bool:
        if token == target:
            return True
        if token in self._known or self.wake_fuzzy >= 1 or len(target) < 4:
            return False
        return SequenceMatcher(None, token, target).ratio() >= self.wake_fuzzy

    def _find_wake(self, tokens: list[str]) -> Optional[int]:
        """Индекс слова сразу после активатора или None."""
        for i in range(len(tokens)):
            for phrase in self._wake_phrases:
                seg = tokens[i:i + len(phrase)]
                if len(seg) == len(phrase) and all(self._wake_token(a, b) for a, b in zip(seg, phrase)):
                    return i + len(phrase)
        return None

    # ---- разбор ----
    def parse(self, words: Sequence[Word] | str) -> Optional[str]:
        """Вернёт имя команды или None.

        «джарвис некст» -> next, «джарвис лайкни эту песню» -> like, «некст» -> None.
        """
        if isinstance(words, str):
            words = [Word(t) for t in words.split()]
        tokens = [_norm(w.text) for w in words if w.conf >= self.min_conf and w.text.strip()]
        tokens = [t for t in tokens if t and t != "[unk]"]

        if self.wake_words:
            idx = self._find_wake(tokens)
            if idx is None:
                return None
            tokens = tokens[idx: idx + self.max_gap + 3]
            limit = self.max_gap
        else:
            limit = len(tokens)

        for start in range(min(limit, len(tokens))):
            for cmd, toks in self._phrases:
                seg = tokens[start:start + len(toks)]
                if len(seg) == len(toks) and all(self._similar(a, b) for a, b in zip(seg, toks)):
                    return cmd
        return None


def words_from_vosk(result: dict) -> list[Word]:
    """Достаёт слова с уверенностью из JSON-результата Vosk (SetWords(True))."""
    if result.get("result"):
        return [Word(r.get("word", ""), float(r.get("conf", 1.0))) for r in result["result"]]
    return [Word(t) for t in (result.get("text") or "").split()]


def merge_commands(base: dict[str, list[str]], extra: dict[str, Iterable[str]] | None) -> dict[str, list[str]]:
    """Добавляет пользовательские фразы из config.json к стандартным."""
    merged = {k: list(v) for k, v in base.items()}
    for cmd, words in (extra or {}).items():
        merged.setdefault(cmd, [])
        for w in words:
            if w not in merged[cmd]:
                merged[cmd].append(w)
    return merged
