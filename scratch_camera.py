"""CameraStream için hızlı elle test: kamerayı bir pencerede gösterir.

Çalıştırma:
    python scratch_camera.py            # dahili MacBook kamerası (otomatik)
    python scratch_camera.py -s 1       # belirli bir index'i zorla
    python scratch_camera.py --list     # kameraları isimleriyle listele
Çıkış: 'q' tuşu ya da ESC.
"""

import argparse

import cv2

from core.camera import CameraStream
from core.devices import find_builtin_index, list_devices

WINDOW = "face2emoji - camera test"


def print_devices() -> None:
    """Kameraları OpenCV index'leri ve isimleriyle yazdırır."""
    devices = list_devices()
    if not devices:
        print("Cihaz listesi alinamadi (pyobjc yok?). Varsayilan index 0 kullanilir.")
        return
    builtin = find_builtin_index()
    for d in devices:
        mark = " <- dahili (varsayilan)" if d.index == builtin else ""
        print(f"index {d.index}: {d.name}  [{d.device_type}]{mark}")


def main() -> None:
    """Kamera akışını pencerede gösterir, 'q' ile temiz çıkar."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s", "--source", type=int, default=None,
        help="kamera index'i (varsayilan: dahili MacBook kamerasi)",
    )
    parser.add_argument("--list", action="store_true", help="kameraları tara ve çık")
    parser.add_argument("--no-mirror", action="store_true", help="ayna görüntüsünü kapat")
    args = parser.parse_args()

    if args.list:
        print_devices()
        return

    with CameraStream(
        source=args.source, width=1280, height=720, mirror=not args.no_mirror
    ) as cam:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        for frame in cam.frames():
            cv2.imshow(WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # 'q' ya da ESC
                break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
