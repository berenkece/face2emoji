/* Face2Emoji - /state'i yoklar ve emoji baloncugunu yuz uzerinde konumlandirir. */

(function () {
  "use strict";

  var POLL_MS = 100;
  /* Baloncuk font-size'i yuz genisliginin bu kadari olur. */
  var FONT_RATIO = 0.6;
  /* Yuvarlak zeminin em cinsinden capi (style.css ile ayni olmali). */
  var BUBBLE_EM = 1.45;
  /* Yuz ile baloncuk arasindaki bosluk (font-size'in kati). */
  var GAP_RATIO = 0.15;
  /* Pop animasyonu suresi (style.css ile ayni olmali). */
  var POP_MS = 260;
  /* Bu kadar ust uste basarisiz istekten sonra baloncuk gizlenir. */
  var MAX_FAILURES = 3;

  var video = document.getElementById("video");
  var bubble = document.getElementById("bubble");
  var bubbleFace = document.getElementById("bubble-face");
  var cameraStatus = document.getElementById("camera-status");

  var lastEmoji = null;
  var popTimer = null;
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

  /** Baloncugu gizler (opacity ile yumusakca). */
  function hideBubble() {
    bubble.classList.remove("visible");
  }

  /** Emoji degistiyse kisa bir pop animasyonu tetikler. */
  function setEmoji(emoji) {
    if (emoji === lastEmoji) {
      return;
    }
    lastEmoji = emoji;
    bubbleFace.textContent = emoji;

    bubble.classList.remove("pop");
    /* Sinifi yeniden eklemeden once reflow: animasyon bastan oynasin. */
    void bubble.offsetWidth;
    bubble.classList.add("pop");

    window.clearTimeout(popTimer);
    popTimer = window.setTimeout(function () {
      bubble.classList.remove("pop");
    }, POP_MS);
  }

  /** Baloncugu normalize yuz kutusuna gore konumlandirir. */
  function placeBubble(face) {
    var rect = displayedRect();
    if (!rect) {
      hideBubble();
      return;
    }

    var faceX = rect.x + face.x * rect.width;
    var faceY = rect.y + face.y * rect.height;
    var faceW = face.w * rect.width;

    var fontSize = Math.max(12, faceW * FONT_RATIO);
    var size = fontSize * BUBBLE_EM;
    var gap = fontSize * GAP_RATIO;

    /* Yuzun sag ust yani; goruntunun disina tasmasin diye kirpilir. */
    var left = clamp(faceX + faceW + gap, rect.x, rect.x + rect.width - size);
    var top = clamp(faceY - size * 0.35, rect.y, rect.y + rect.height - size);

    bubble.style.fontSize = fontSize + "px";
    bubble.style.transform =
      "translate3d(" + Math.round(left) + "px," + Math.round(top) + "px,0)";
    bubble.classList.add("visible");
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
      hideBubble();
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

        setEmoji(state.emoji);
        if (state.face) {
          placeBubble(state.face);
        } else {
          hideBubble();
        }
      })
      .catch(handleFailure);
  }

  /* Sekme arka plandayken tarayici setInterval'i kisiyor; geri gelince
     bekleme olmadan tazele. */
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      poll();
    }
  });

  window.setInterval(poll, POLL_MS);
  poll();
})();
