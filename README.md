# Spoti Skipper 🎤⏭

Голосовое управление Spotify через [Spicetify](https://spicetify.app). Говоришь «музыка, дальше» — трек скипается. Распознавание работает **офлайн** (Vosk), ничего никуда не отправляется.

## Как устроено

```
микрофон ─► listener.py (Vosk, офлайн) ─► ws://127.0.0.1:8974 ─► spoti-skipper.js (внутри Spotify) ─► Spicetify.Player
```

Почему не распознавание прямо в Spotify: встроенный в Chromium Web Speech API внутри клиента Spotify не работает (нет ключей Google), поэтому речь распознаёт маленький локальный слушатель.

## Установка (Windows)

Нужно: Spotify + [Spicetify](https://spicetify.app/docs/getting-started), Python 3.9+.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Скрипт копирует расширение в Spicetify, делает `spicetify apply` и ставит Python-зависимости в `listener\.venv`.

Потом запусти **`start.bat`**. При первом запуске скачается русская модель Vosk (~45 МБ). В Spotify появится уведомление «голосовое управление включено».

<details><summary>Вручную / macOS / Linux</summary>

```bash
cp extension/spoti-skipper.js "$(spicetify path userdata)/Extensions/"
spicetify config extensions spoti-skipper.js && spicetify apply
cd listener && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python listener.py
```
</details>

## Команды

Сначала wake word **«музыка»**, потом команда — в одной фразе.

| Скажи | Что делает |
|---|---|
| музыка **дальше** / следующий / скип / пропусти / next / skip | следующий трек |
| музыка **назад** / предыдущий / верни / back | предыдущий трек |
| музыка **пауза** / стоп | пауза |
| музыка **играй** / продолжи / play | продолжить |
| музыка **громче** / **тише** | громкость ±10% |
| музыка **лайк** / нравится | лайк трека |
| музыка **перемешай** / **повтор** | shuffle / repeat |

## Настройка — `listener/config.json`

| Поле | Что это |
|---|---|
| `wake_word` | слово-активатор. `""` — без него (но тогда команды может «сказать» сама песня из колонок) |
| `min_conf` | порог уверенности 0–1. Ложные срабатывания → подними до 0.75 |
| `lang` | `ru` или `en-us` |
| `device` | номер микрофона (`start.bat --list-devices`) |
| `extra_commands` | свои синонимы: `{"next": ["некст"]}` |
| `port` | порт WebSocket. Если меняешь — в консоли Spotify (Ctrl+Shift+I): `localStorage.setItem("spoti-skipper:port", "9000")` |

## Проверка без микрофона

```
start.bat --keyboard
```
и вводи `next`, `pause`, `громче` — команды уйдут в Spotify.

## Разработка

```bash
python -m pytest tests        # парсер команд
node --test tests/extension.test.mjs   # логика расширения
```
