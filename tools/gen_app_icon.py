"""Genera el icono de app/barra de tareas de Windows (app/assets/icons/fitpilot.ico).

Ejecutar desde la carpeta ``frontend/``:

    python tools/gen_app_icon.py

================================  AJUSTES  ================================
FILL        -> *Perilla de TAMAÑO*. Fracción del ANCHO del recuadro que ocupa
               la marca. Útil 0.6 .. 1.0. La marca es apaisada (~1.35:1), así que
               el ANCHO es el límite y el máximo real es 1.0 (borde a borde);
               valores mayores se limitan a 1.0 (no puede salirse del lienzo).
               Para algo más grande usa USE_TILE=True.

Efecto de VOLUMEN (3D suave): cada forma se rellena con un degradado vertical
(luz arriba, sombra abajo). Ajusta las parejas de color:
  WINGS_TOP/WINGS_BOT -> alas (claro arriba / oscuro abajo)
  P_TOP/P_BOT         -> la "P" y el punto
Pon EFFECT="flat" para volver a colores planos (usa WINGS_TOP/P_TOP).

USE_TILE    -> True para un azulejo (squircle relleno) detrás de la marca, con la
               marca en blanco. Tamaño dentro del tile: TILE_MARK_FILL.
==========================================================================
"""
import struct
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QLinearGradient, QBrush
from PySide6.QtCore import Qt, QRectF, QBuffer, QByteArray, QIODevice

# ----------------------------- AJUSTES ------------------------------------
FILL = 2                          # <-- TAMAÑO sin azulejo (útil 0.6..1.0)
SIZES = [16, 20, 24, 32, 48, 64, 128, 256]

EFFECT = "gradient"               # "gradient" (volumen 3D) | "flat"
WINGS_TOP = "#6CC8F3"             # alas: luz (arriba)
WINGS_BOT = "#1576B8"             # alas: sombra (abajo)
P_TOP = "#B0E8FB"                 # P/punto: luz
P_BOT = "#3CAEDC"                 # P/punto: sombra

USE_TILE = False                  # True -> azulejo relleno detrás de la marca
TILE_RADIUS = 0.22                # redondeo de esquina (fracción del tamaño)
TILE_MARK_FILL = 0.80             # ancho de la marca dentro del azulejo
TILE_GRAD = ("#2E9BE0", "#1E6FB8")  # degradado del azulejo
# --------------------------------------------------------------------------

_ASSETS = Path(__file__).resolve().parent.parent / "app" / "assets"
_MARK = _ASSETS / "fitpilot-mark.png"
_OUT = _ASSETS / "icons" / "fitpilot.ico"

_NAVY = (24, 47, 80)
_LBLUE = (103, 182, 223)


def _dist2(c, t):
    return (c[0] - t[0]) ** 2 + (c[1] - t[1]) ** 2 + (c[2] - t[2]) ** 2


def _split_masks(img: QImage):
    """Devuelve (wings_img, p_img): la marca con solo una región opaca cada una
    (conservando el alpha original para bordes suaves)."""
    wings = QImage(img)
    p = QImage(img)
    clear = QColor(0, 0, 0, 0)
    for y in range(img.height()):
        for x in range(img.width()):
            px = img.pixelColor(x, y)
            if px.alpha() == 0:
                continue
            c = (px.red(), px.green(), px.blue())
            if _dist2(c, _NAVY) < _dist2(c, _LBLUE):
                p.setPixelColor(x, y, clear)        # es ala -> fuera de la P
            else:
                wings.setPixelColor(x, y, clear)    # es P  -> fuera de las alas
    return wings, p


def _fill_mask(mask: QImage, top: str, bot: str, target_w: int) -> QPixmap:
    """Rellena la silueta ``mask`` con un degradado vertical (top->bot) o color
    plano si EFFECT='flat'. Escalada a ``target_w`` de ancho."""
    base = QPixmap.fromImage(mask).scaledToWidth(
        target_w, Qt.TransformationMode.SmoothTransformation
    )
    res = QPixmap(base.size())
    res.fill(Qt.GlobalColor.transparent)
    p = QPainter(res)
    p.drawPixmap(0, 0, base)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    if EFFECT == "flat":
        p.fillRect(base.rect(), QColor(top))
    else:
        g = QLinearGradient(0, 0, 0, base.height())
        g.setColorAt(0, QColor(top))
        g.setColorAt(1, QColor(bot))
        p.fillRect(base.rect(), QBrush(g))
    p.end()
    return res


def _white_mark(mark: QPixmap, target_w: int) -> QPixmap:
    base = mark.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
    res = QPixmap(base.size())
    res.fill(Qt.GlobalColor.transparent)
    p = QPainter(res)
    p.drawPixmap(0, 0, base)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(base.rect(), QColor("#ffffff"))
    p.end()
    return res


def _render(size, wings_img, p_img, mark):
    if USE_TILE:
        ss = size * 4
        pm = QPixmap(ss, ss)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        g = QLinearGradient(0, 0, ss, ss)
        g.setColorAt(0, QColor(TILE_GRAD[0]))
        g.setColorAt(1, QColor(TILE_GRAD[1]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(0, 0, ss, ss), ss * TILE_RADIUS, ss * TILE_RADIUS)
        mk = _white_mark(mark, int(ss * TILE_MARK_FILL))
        p.drawPixmap(int((ss - mk.width()) / 2), int((ss - mk.height()) / 2), mk)
        p.end()
        return pm.scaled(
            size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # Sin azulejo: alas y P con degradado de volumen, ajustadas dentro del
    # recuadro (ancho = FILL*size, máx 1.0) sin deformar ni recortar.
    box = int(size * min(FILL, 1.0))
    wings = _fill_mask(wings_img, WINGS_TOP, WINGS_BOT, box)
    pmark = _fill_mask(p_img, P_TOP, P_BOT, box)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    ox = (size - wings.width()) // 2
    oy = (size - wings.height()) // 2
    p.drawPixmap(ox, oy, wings)
    p.drawPixmap(ox, oy, pmark)
    p.end()
    return pm


def _png_bytes(pm: QPixmap) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def main() -> None:
    app = QApplication([])  # noqa: F841 (necesario para QImage/QPainter)
    if not USE_TILE and FILL > 1.0:
        print(
            f"AVISO: FILL={FILL} se limita a 1.0. Sin azulejo la marca ya llena "
            f"el lienzo en 1.0; valores mayores NO la agrandan (no puede salirse "
            f"del recuadro). Para un icono más grande usa USE_TILE=True."
        )
    img = QImage(str(_MARK)).convertToFormat(QImage.Format.Format_ARGB32)
    if img.isNull():
        raise SystemExit(f"No se encontró la marca: {_MARK}")
    wings_img, p_img = _split_masks(img)
    mark = QPixmap(str(_MARK))

    items = [(s, _png_bytes(_render(s, wings_img, p_img, mark))) for s in SIZES]
    offset = 6 + 16 * len(items)
    dir_b = b""
    img_b = b""
    for s, png in items:
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        dir_b += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        img_b += png
    _OUT.write_bytes(struct.pack("<HHH", 0, 1, len(items)) + dir_b + img_b)
    print(f"OK -> {_OUT}  (EFFECT={EFFECT}, FILL={FILL}, tile={USE_TILE})")


if __name__ == "__main__":
    main()
