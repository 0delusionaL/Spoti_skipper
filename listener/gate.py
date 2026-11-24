"""Детектор тишины: не отдаёт моделям звук, когда никто не говорит.

Задача — экономить процессор, НЕ ухудшая распознавание:
* порог относительный (во сколько раз громче фона), поэтому тихие и плохие
  микрофоны работают так же, как хорошие;
* перед срабатыванием отдаём «предзапись», чтобы не обрезать начало слова;
* после тишины ещё какое-то время пропускаем звук, чтобы модель дослушала фразу;
* если вокруг постоянно шумно (музыка из колонок), фильтр сам отключается
  и пропускает всё — тогда поведение как без него.
"""

from __future__ import annotations

import math
from array import array
from collections import deque


def rms_int16(chunk: bytes) -> float:
    samples = array("h")
    samples.frombytes(chunk[: len(chunk) - len(chunk) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class SilenceGate:
    def __init__(
        self,
        ratio: float = 2.0,          # во сколько раз громче фона считается «звуком»
        min_level: float = 120.0,    # ниже этого уровня (из 32768) — всегда тишина
        preroll_chunks: int = 3,     # ~0.75 с при кусках по 0.25 с
        hangover_chunks: int = 6,    # ~1.5 с
        busy_window: int = 80,       # ~20 с истории для автоотключения
        busy_on: float = 0.5,        # открыт больше 50% времени -> пропускаем всё
        busy_off: float = 0.3,       # меньше 30% -> снова фильтруем
    ) -> None:
        self.ratio = ratio
        self.min_level = min_level
        self.hangover_chunks = hangover_chunks
        self.busy_on, self.busy_off = busy_on, busy_off
        self.floor: float | None = None
        self.open = False
        self.bypass = False
        self._hang = 0
        self._pre: deque[bytes] = deque(maxlen=preroll_chunks)
        self._history: deque[int] = deque(maxlen=busy_window)

    def is_loud(self, level: float) -> bool:
        if self.floor is None:
            return level >= self.min_level
        return level >= max(self.min_level, self.floor * self.ratio)

    def _update_floor(self, level: float) -> None:
        if self.floor is None:
            self.floor = level
        elif level < self.floor:
            self.floor += (level - self.floor) * 0.3    # в тишину подстраиваемся быстро
        else:
            self.floor += (level - self.floor) * 0.02   # к шуму — медленно, чтобы голос не «съедал» порог

    def feed(self, chunk: bytes) -> tuple[list[bytes], bool]:
        """Возвращает (куски для моделей, фраза_закончилась).

        фраза_закончилась=True — пора забрать у моделей FinalResult().
        """
        level = rms_int16(chunk)
        loud = self.is_loud(level)
        if not loud:
            self._update_floor(level)

        was_open = self.open
        if loud:
            self.open = True
            self._hang = self.hangover_chunks
        elif self.open:
            self._hang -= 1
            if self._hang <= 0:
                self.open = False

        self._history.append(1 if self.open else 0)
        if len(self._history) == self._history.maxlen:
            busy = sum(self._history) / len(self._history)
            if not self.bypass and busy > self.busy_on:
                self.bypass = True
            elif self.bypass and busy < self.busy_off:
                self.bypass = False

        if self.bypass:
            self._pre.clear()
            return [chunk], False

        if self.open:
            out = list(self._pre) + [chunk] if not was_open else [chunk]
            self._pre.clear()
            return out, False

        if was_open:
            # Последний кусок «хвоста» тоже отдаём и просим модели закончить фразу.
            return [chunk], True

        self._pre.append(chunk)
        return [], False
