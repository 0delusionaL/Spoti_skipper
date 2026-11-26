"""Окно настроек Spoti Skipper: своё слово-активатор и свои фразы для скипа.

Открывается из меню трея. Сохраняет в config.json; код выхода 0 = сохранили
(трей после этого перезапускается и применяет изменения).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from commands import DEFAULT_WAKE_WORDS

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"
DEFAULT_LABEL = "Джарвис"


def split_list(text: str) -> list[str]:
    """«пятница, Friday ,, » -> ["пятница", "friday"] (без дублей, порядок сохраняется)."""
    out: list[str] = []
    for part in text.replace(";", ",").replace("\n", ",").split(","):
        w = " ".join(part.strip().lower().split())
        if w and w not in out:
            out.append(w)
    return out


def wake_words_to_save(text: str) -> list[str]:
    """Пусто или только стандартные варианты Джарвиса -> [] (= «Джарвис» со всеми вариантами)."""
    words = split_list(text)
    default = {w.lower() for w in DEFAULT_WAKE_WORDS}
    if not words or set(words) <= default:
        return []
    return words


def apply_settings(cfg: dict, wake_text: str, skip_text: str, use_wake: bool) -> dict:
    cfg = dict(cfg)
    cfg["wake_words"] = wake_words_to_save(wake_text)
    cfg["require_wake_word"] = bool(use_wake)
    extra = dict(cfg.get("extra_commands") or {})
    extra["next"] = split_list(skip_text)
    cfg["extra_commands"] = extra
    return cfg


def load_raw() -> dict:
    if CONFIG.exists():
        with CONFIG.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_raw(cfg: dict) -> None:
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG)


NO_TK_EXIT = 3


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError:
        return NO_TK_EXIT  # Python без tkinter (при установке с python.org он ставится по умолчанию)

    cfg = load_raw()
    saved = {"ok": False}

    root = tk.Tk()
    root.title("Spoti Skipper — настройки")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.grid()

    ttk.Label(frm, text="Слово-активатор", font=("Segoe UI", 10, "bold")).grid(sticky="w")
    ttk.Label(frm, text="Его говоришь перед командой. Можно несколько через запятую или фразу: «эй спотик».\n"
                        "Оставь пустым — будет «Джарвис».", foreground="#555").grid(sticky="w", pady=(0, 4))
    wake_var = tk.StringVar(value=", ".join(cfg.get("wake_words") or []) or DEFAULT_LABEL)
    ttk.Entry(frm, textvariable=wake_var, width=56).grid(sticky="we")

    use_wake = tk.BooleanVar(value=cfg.get("require_wake_word", True))
    ttk.Checkbutton(frm, text="Требовать активатор (без него команды может «сказать» песня из колонок)",
                    variable=use_wake).grid(sticky="w", pady=(6, 14))

    ttk.Label(frm, text="Свои фразы для скипа", font=("Segoe UI", 10, "bold")).grid(sticky="w")
    ttk.Label(frm, text="Через запятую. Добавляются к стандартным («некст», «дальше», «skip»…).\n"
                        "Пример: врубай следующий, мотай, гоу", foreground="#555").grid(sticky="w", pady=(0, 4))
    skip_var = tk.StringVar(value=", ".join((cfg.get("extra_commands") or {}).get("next", [])))
    ttk.Entry(frm, textvariable=skip_var, width=56).grid(sticky="we")

    ttk.Label(frm, text="Остальные команды и все фразы — в commands.json (меню трея → «Изменить фразы»).",
              foreground="#555").grid(sticky="w", pady=(14, 10))

    def on_save() -> None:
        new = apply_settings(cfg, wake_var.get(), skip_var.get(), use_wake.get())
        try:
            save_raw(new)
        except OSError as e:
            messagebox.showerror("Spoti Skipper", f"Не получилось сохранить: {e}")
            return
        saved["ok"] = True
        root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(sticky="e")
    ttk.Button(btns, text="Отмена", command=root.destroy).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(btns, text="Сохранить и применить", command=on_save).grid(row=0, column=1)
    root.bind("<Return>", lambda _e: on_save())
    root.bind("<Escape>", lambda _e: root.destroy())
    root.attributes("-topmost", True)
    root.mainloop()
    return 0 if saved["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
