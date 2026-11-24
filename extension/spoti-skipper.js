// NAME: Spoti Skipper
// AUTHOR: 0delusionaL
// DESCRIPTION: Голосовое управление Spotify: получает команды от локального слушателя (listener.py) по WebSocket.
// VERSION: 1.0.0

(function SpotiSkipper() {
  const VERSION = "1.0.0";
  const PORT_KEY = "spoti-skipper:port";
  const DEFAULT_PORT = 8974;
  const VOLUME_STEP = 0.1;

  const LABELS = {
    next: "⏭ Следующий трек",
    previous: "⏮ Предыдущий трек",
    pause: "⏸ Пауза",
    play: "▶ Играю",
    volume_up: "🔊 Громче",
    volume_down: "🔉 Тише",
    like: "❤ Лайк",
    shuffle: "🔀 Перемешивание",
    repeat: "🔁 Повтор",
  };

  function clamp01(v) {
    return Math.min(1, Math.max(0, v));
  }

  // Выполняет команду над плеером. Возвращает true, если команда известна.
  function runCommand(Spicetify, command) {
    const P = Spicetify.Player;
    switch (command) {
      case "next": P.next(); break;
      case "previous": P.back(); break;
      case "pause": P.pause(); break;
      case "play": P.play(); break;
      case "volume_up": P.setVolume(clamp01(P.getVolume() + VOLUME_STEP)); break;
      case "volume_down": P.setVolume(clamp01(P.getVolume() - VOLUME_STEP)); break;
      case "like": P.toggleHeart(); break;
      case "shuffle": P.toggleShuffle(); break;
      case "repeat": P.toggleRepeat(); break;
      default: return false;
    }
    return true;
  }

  function currentTrack(Spicetify) {
    const meta = Spicetify.Player?.data?.item?.metadata;
    if (!meta) return "";
    return [meta.artist_name, meta.title].filter(Boolean).join(" — ");
  }

  function handleMessage(Spicetify, raw, send) {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return null;
    }
    if (!msg || msg.type !== "command") return null;
    const ok = runCommand(Spicetify, msg.command);
    if (!ok) return null;
    Spicetify.showNotification(LABELS[msg.command] || msg.command);
    // Трек меняется не мгновенно — шлём подтверждение чуть позже.
    setTimeout(() => {
      send({ type: "ack", command: msg.command, track: currentTrack(Spicetify) });
    }, 700);
    return msg.command;
  }

  function getPort() {
    try {
      const v = parseInt(localStorage.getItem(PORT_KEY), 10);
      return Number.isFinite(v) && v > 0 ? v : DEFAULT_PORT;
    } catch {
      return DEFAULT_PORT;
    }
  }

  function connect(Spicetify) {
    let delay = 1000;
    let wasConnected = false;

    const open = () => {
      const ws = new WebSocket(`ws://127.0.0.1:${getPort()}`);
      const send = (obj) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
      };

      ws.onopen = () => {
        delay = 1000;
        wasConnected = true;
        send({ type: "hello", version: VERSION });
        Spicetify.showNotification("🎤 Spoti Skipper: голосовое управление включено");
      };
      ws.onmessage = (e) => handleMessage(Spicetify, e.data, send);
      ws.onclose = () => {
        if (wasConnected) {
          wasConnected = false;
          Spicetify.showNotification("🎤 Spoti Skipper: слушатель отключился");
        }
        setTimeout(open, delay);
        delay = Math.min(delay * 2, 15000); // тихо переподключаемся, пока не запустишь listener
      };
      ws.onerror = () => ws.close();
    };

    open();
  }

  // Экспорт для тестов в Node; в Spotify этого объекта нет.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { runCommand, handleMessage, currentTrack, clamp01 };
    return;
  }

  (function waitForSpicetify() {
    const S = window.Spicetify;
    if (!S || !S.Player || !S.Player.next || !S.showNotification) {
      setTimeout(waitForSpicetify, 300);
      return;
    }
    connect(S);
  })();
})();
