/* Face2Emoji - /state'i yoklar ve her kisinin yuzu yaninda kendi emojisini
   gosterir. Her face id icin bir baloncuk DOM elemani tutulur (havuz); her
   karede silinip yeniden yaratilmaz, yoksa animasyonlar sifirlanir. */

(function () {
  "use strict";

  var POLL_MS = 100;
  /* Baloncuk font-size'i o kisinin yuz genisliginin bu kadari olur. */
  var FONT_RATIO = 0.6;
  /* Yuvarlak zeminin em cinsinden capi (style.css ile ayni olmali). */
  var BUBBLE_EM = 1.45;
  /* Yuz ile baloncuk arasindaki bosluk (font-size'in kati). */
  var GAP_RATIO = 0.15;
  /* Pop animasyonu suresi (style.css ile ayni olmali). */
  var POP_MS = 260;
  /* En kucuk okunabilir baloncuk font-size'i. */
  var MIN_FONT_PX = 12;
  /* Bu kadar ust uste basarisiz istekten sonra baloncuklar gizlenir. */
  var MAX_FAILURES = 3;
  /* Fare bu kadar hareketsiz kalinca imlec gizlenir. */
  var CURSOR_IDLE_MS = 3000;

  var video = document.getElementById("video");
  var bubbleLayer = document.getElementById("bubbles");
  var cameraStatus = document.getElementById("camera-status");

  /* face id -> {el, faceEl, lastEmoji, popTimer} */
  var bubbles = {};
  var consecutiveFailures = 0;

  /**
   * <img> object-fit:contain ile olceklendiginde goruntunun stage koordinat
   * sisteminde gercekte kapladigi dikdortgeni hesaplar.
   * Letterbox bosluklari (ustte/altta ya da yanlarda) disarida birakilir.
   */
  function displayedRect() {
    var naturalW = video.naturalWidth;
    var naturalH = video.naturalHeight;
    var boxW = video.clientWidth;
    var boxH = video.clientHeight;

    if (!naturalW || !naturalH || !boxW || !boxH) {
      return null;
    }

    var scale = Math.min(boxW / naturalW, boxH / naturalH);
    var width = naturalW * scale;
    var height = naturalH * scale;

    return {
      x: video.offsetLeft + (boxW - width) / 2,
      y: video.offsetTop + (boxH - height) / 2,
      width: width,
      height: height
    };
  }

  /** Degeri [min, max] araligina sikistirir. */
  function clamp(value, min, max) {
    if (max < min) {
      return min;
    }
    return Math.min(Math.max(value, min), max);
  }

  /** Verilen id icin baloncugu dondurur, yoksa olusturur. */
  function getBubble(id) {
    var existing = bubbles[id];
    if (existing) {
      return existing;
    }

    var el = document.createElement("div");
    el.className = "bubble";
    var faceEl = document.createElement("div");
    faceEl.className = "face";
    el.appendChild(faceEl);
    bubbleLayer.appendChild(el);

    var entry = { el: el, faceEl: faceEl, lastEmoji: null, popTimer: null };
    bubbles[id] = entry;
    return entry;
  }

  /** Bir baloncugu DOM'dan kaldirir. */
  function removeBubble(id) {
    var entry = bubbles[id];
    if (!entry) {
      return;
    }
    window.clearTimeout(entry.popTimer);
    if (entry.el.parentNode) {
      entry.el.parentNode.removeChild(entry.el);
    }
    delete bubbles[id];
  }

  /** Tum baloncuklari gizler (DOM'dan silmeden). */
  function hideAllBubbles() {
    Object.keys(bubbles).forEach(function (id) {
      bubbles[id].el.classList.remove("visible");
    });
  }

  /** Emoji degistiyse o KISIYE ozel pop animasyonu tetikler. */
  function setEmoji(entry, emoji) {
    if (emoji === entry.lastEmoji) {
      return;
    }
    entry.lastEmoji = emoji;
    entry.faceEl.textContent = emoji;

    entry.el.classList.remove("pop");
    /* Sinifi yeniden eklemeden once reflow: animasyon bastan oynasin. */
    void entry.el.offsetWidth;
    entry.el.classList.add("pop");

    window.clearTimeout(entry.popTimer);
    entry.popTimer = window.setTimeout(function () {
      entry.el.classList.remove("pop");
    }, POP_MS);
  }

  /** Bir baloncugu kendi yuzunun sag ust yanina konumlandirir. */
  function placeBubble(entry, box, rect) {
    var faceX = rect.x + box.x * rect.width;
    var faceY = rect.y + box.y * rect.height;
    var faceW = box.w * rect.width;

    /* Uzaktaki kisinin yuzu kucuk -> baloncugu da kucuk. */
    var fontSize = Math.max(MIN_FONT_PX, faceW * FONT_RATIO);
    var size = fontSize * BUBBLE_EM;
    var gap = fontSize * GAP_RATIO;

    var left = clamp(faceX + faceW + gap, rect.x, rect.x + rect.width - size);
    var top = clamp(faceY - size * 0.35, rect.y, rect.y + rect.height - size);

    entry.el.style.fontSize = fontSize + "px";
    entry.el.style.transform =
      "translate3d(" + Math.round(left) + "px," + Math.round(top) + "px,0)";
    entry.el.classList.add("visible");
  }

  /** Gelen yuz listesine gore havuzu gunceller. */
  function renderFaces(faces) {
    var rect = displayedRect();
    if (!rect) {
      hideAllBubbles();
      return;
    }

    var seen = {};
    faces.forEach(function (face) {
      seen[face.id] = true;
      var entry = getBubble(face.id);
      setEmoji(entry, face.emoji);
      placeBubble(entry, face.box, rect);
    });

    /* Kadrajdan cikan kisilerin baloncugunu kaldir. */
    Object.keys(bubbles).forEach(function (id) {
      if (!seen[id]) {
        removeBubble(id);
      }
    });
  }

  /** Kamera uyarisini gosterir ya da gizler. */
  function setCameraStatus(visible) {
    if (!cameraStatus) {
      return;
    }
    cameraStatus.hidden = !visible;
    /* hidden kalkmadan once sinif eklenirse gecis oynamaz. */
    if (visible) {
      void cameraStatus.offsetWidth;
    }
    cameraStatus.classList.toggle("visible", visible);
  }

  /** Sunucuya ulasilamadiginda arayuzu durdurur. */
  function handleFailure() {
    consecutiveFailures += 1;
    if (consecutiveFailures >= MAX_FAILURES) {
      /* Sunucu olmusse ekranda donmus emoji kalmasin. */
      hideAllBubbles();
      setCameraStatus(false);
    }
  }

  /** /state'i okur ve arayuzu gunceller. */
  function poll() {
    fetch("/state", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (state) {
        consecutiveFailures = 0;
        setCameraStatus(state.camera_ok === false);
        renderFaces(state.faces || []);
      })
      .catch(handleFailure);
  }

  /* --- Kiosk davranislari --- */

  /* Fare 3 sn hareketsiz kalinca imleci gizle, hareket edince geri getir. */
  function setupCursorHiding() {
    var timer = null;
    function schedule() {
      document.body.classList.remove("idle");
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        document.body.classList.add("idle");
      }, CURSOR_IDLE_MS);
    }
    ["mousemove", "mousedown", "keydown", "touchstart"].forEach(function (evt) {
      document.addEventListener(evt, schedule, { passive: true });
    });
    schedule();
  }

  /* Ekranin uykuya gecmesini engelle. Desteklenmiyorsa sessizce gec. */
  function setupWakeLock() {
    if (!navigator.wakeLock || !navigator.wakeLock.request) {
      return;
    }
    var lock = null;

    function acquire() {
      navigator.wakeLock
        .request("screen")
        .then(function (sentinel) {
          lock = sentinel;
          /* Sekme arka plana alininca kilit dusuyor; donunce yeniden al. */
          sentinel.addEventListener("release", function () {
            lock = null;
          });
        })
        .catch(function () {
          /* Izin yok ya da desteklenmiyor -- sessizce vazgec. */
        });
    }

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && lock === null) {
        acquire();
      }
    });
    acquire();
  }

  /* Sekme arka plandayken tarayici setInterval'i kisiyor; geri gelince
     bekleme olmadan tazele. */
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      poll();
    }
  });

  setupCursorHiding();
  setupWakeLock();
  window.setInterval(poll, POLL_MS);
  poll();
})();
