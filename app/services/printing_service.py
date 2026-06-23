"""Thermal-ticket printing service (POS-58).

Ported from the sibling Love_fitness project
(``proyectos_python/Love_fitness/.../printing_service.py``): the ticket is
rendered as plain text (40 cols), written to a temp ``.txt`` and sent to the OS
print spooler — ``win32print``/``win32api`` on Windows, ``lp`` elsewhere.

FitPilot adaptations over the original:
  * brand header + footer + width come from ``Config``;
  * the configured ``PRINTER_NAME`` (default POS-58) is targeted via the
    ``printto`` verb, falling back to the default printer;
  * adds ``imprimir_ticket_venta`` (multi-line sale) and ``imprimir_corte_caja``.

Designed to degrade gracefully: when pywin32 is missing it logs and returns
False instead of crashing the app.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from ..core import Config
    _BRAND = Config.RECEIPT_BRAND
    _FOOTER = Config.RECEIPT_FOOTER
    _WIDTH = Config.RECEIPT_WIDTH
    _PRINTER_NAME = Config.PRINTER_NAME
except Exception:  # pragma: no cover - config import is best-effort
    _BRAND, _FOOTER, _WIDTH, _PRINTER_NAME = "FITPILOT", "¡Gracias por su preferencia!", 40, "POS-58"

logger = logging.getLogger(__name__)


class PrintingService:
    """Render and print tickets/receipts on the configured thermal printer."""

    def __init__(self, printer_name: Optional[str] = None) -> None:
        self.platform = sys.platform
        self.printer_name = printer_name if printer_name is not None else _PRINTER_NAME
        self.width = _WIDTH
        self.brand = _BRAND
        self.footer = _FOOTER
        logger.info("PrintingService init (platform=%s, printer=%s)", self.platform, self.printer_name)

    # ------------------------------------------------------------------ public
    def imprimir_ticket(self, data: Dict[str, Any]) -> bool:
        """Print a generic ticket.

        data keys: titulo, fecha, socio, usuario, total, items[{concepto,detalle,precio}],
        pagos[{metodo,monto}], cambio, horario, footer_lines[str].
        """
        try:
            content = self._generar_contenido_ticket(data)
            with tempfile.NamedTemporaryFile(
                suffix=".txt", delete=False, mode="w", encoding="utf-8"
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            logger.debug("Ticket temp file: %s", tmp_path)

            if self.platform == "win32":
                ok = self._imprimir_windows(tmp_path)
            elif self.platform in ("linux", "linux2", "darwin"):
                ok = self._imprimir_unix(tmp_path)
            else:
                logger.warning("Plataforma no soportada para impresión: %s", self.platform)
                ok = False
            return ok
        except Exception as exc:  # noqa: BLE001
            logger.error("Error al imprimir ticket: %s", exc, exc_info=True)
            return False
        finally:
            if "tmp_path" in locals():
                try:
                    os.unlink(tmp_path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("No se pudo eliminar el temporal: %s", exc)

    def imprimir_ticket_venta(self, sale: Dict[str, Any], usuario: Optional[str] = None) -> bool:
        """Print a POS sale ticket from a ``sale`` dict (GraphQL SaleType shape)."""
        items: List[Dict[str, Any]] = []
        for li in sale.get("lineItems") or sale.get("line_items") or []:
            qty = li.get("quantity") or 1
            desc = li.get("description") or ""
            concepto = f"{qty} x {desc}" if qty and qty != 1 else desc
            items.append({"concepto": concepto, "precio": li.get("lineTotal", li.get("line_total", 0))})

        pagos = [
            {"metodo": p.get("method", ""), "monto": p.get("amount", 0)}
            for p in (sale.get("payments") or [])
        ]
        total = float(sale.get("total") or 0)
        paid = float(sale.get("amountPaid", sale.get("amount_paid", total)) or 0)
        change = float(sale.get("changeDue", sale.get("change_due", max(paid - total, 0))) or 0)

        data: Dict[str, Any] = {
            "titulo": f"TICKET DE VENTA #{sale.get('id', '')}".strip(),
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "total": f"${total:,.2f}",
            "items": items,
            "pagos": pagos,
            "cambio": change,
        }
        socio = sale.get("personName") or sale.get("person_name")
        if socio:
            data["socio"] = socio
        if usuario:
            data["usuario"] = usuario
        return self.imprimir_ticket(data)

    def imprimir_corte_caja(self, report: Dict[str, Any]) -> bool:
        """Print the corte de caja (cash session report dict, GraphQL shape)."""
        by_method = report.get("byMethod") or report.get("by_method") or []
        expected = report.get("expectedCash", report.get("expected_cash"))
        if expected is None:
            expected = report.get("computedExpectedCash", report.get("computed_expected_cash", 0))
        counted = report.get("countedCash", report.get("counted_cash"))
        difference = report.get("difference")

        footer_lines = [
            f"Fondo inicial: ${float(report.get('openingFloat', report.get('opening_float', 0)) or 0):,.2f}",
            f"Ventas: {report.get('salesCount', report.get('sales_count', 0))}"
            f"  (${float(report.get('salesTotal', report.get('sales_total', 0)) or 0):,.2f})",
            f"Ingresos efectivo: ${float(report.get('cashIn', report.get('cash_in', 0)) or 0):,.2f}",
            f"Retiros efectivo: ${float(report.get('cashOut', report.get('cash_out', 0)) or 0):,.2f}",
            "",
            f"Efectivo esperado: ${float(expected or 0):,.2f}",
        ]
        if counted is not None:
            footer_lines.append(f"Efectivo contado: ${float(counted):,.2f}")
        if difference is not None:
            footer_lines.append(f"Diferencia: ${float(difference):,.2f}")

        items = [
            {"concepto": (b.get("method") or "").capitalize(), "precio": b.get("total", 0)}
            for b in by_method
        ]
        data: Dict[str, Any] = {
            "titulo": f"CORTE DE CAJA #{report.get('sessionId', report.get('session_id', ''))}".strip(),
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "items": items,
            "total": f"${float(report.get('salesTotal', report.get('sales_total', 0)) or 0):,.2f}",
            "footer_lines": footer_lines,
        }
        return self.imprimir_ticket(data)

    # ------------------------------------------------------------------ render
    def _generar_contenido_ticket(self, data: Dict[str, Any]) -> str:
        ancho = self.width
        sep = "-" * ancho
        titulo = data.get("titulo", "COMPROBANTE").center(ancho)
        fecha = data.get("fecha", datetime.now().strftime("%d/%m/%Y %H:%M"))

        lines: List[str] = ["", self.brand.center(ancho), "", titulo, sep, f"Fecha: {fecha}".ljust(ancho)]

        if "socio" in data:
            lines.append(f"Socio: {data['socio']}".ljust(ancho))
        if "usuario" in data:
            lines.append(f"Atendió: {data['usuario']}".ljust(ancho))
        lines.append(sep)

        for item in data.get("items") or []:
            concepto = item.get("concepto", "")
            detalle = item.get("detalle", "")
            precio = float(item.get("precio", 0) or 0)
            lines.append(str(concepto))
            if detalle:
                lines.append(f"  {detalle}")
            lines.append(f"${precio:,.2f}".rjust(ancho))
        if data.get("items"):
            lines.append(sep)

        lines.append(f"TOTAL: {data.get('total', '$0.00')}".rjust(ancho))

        for pago in data.get("pagos") or []:
            metodo = str(pago.get("metodo", "")).capitalize()
            monto = float(pago.get("monto", 0) or 0)
            lines.append(f"{metodo}: ${monto:,.2f}".rjust(ancho))
        if data.get("cambio"):
            lines.append(f"Cambio: ${float(data['cambio']):,.2f}".rjust(ancho))

        for fl in data.get("footer_lines") or []:
            lines.append(str(fl).ljust(ancho))

        if "horario" in data:
            lines.append(sep)
            lines.append(f"Horario: {data['horario']}".center(ancho))

        lines.extend([sep, self.footer.center(ancho), "", "", ""])  # trailing space for the cut
        return "\n".join(lines)

    # ----------------------------------------------------------------- backends
    def _imprimir_windows(self, archivo: str) -> bool:
        try:
            import win32api
            import win32print
        except ImportError:
            logger.error("No se pudo importar win32print/win32api. Instale pywin32.")
            return False

        try:
            printer = (self.printer_name or "").strip()
            if printer:
                # Target the configured printer explicitly.
                win32api.ShellExecute(0, "printto", archivo, f'"{printer}"', ".", 0)
                logger.info("Ticket enviado a impresora: %s", printer)
            else:
                default_printer = win32print.GetDefaultPrinter()
                if not default_printer:
                    logger.warning("No hay impresora predeterminada en Windows")
                    return False
                win32api.ShellExecute(0, "print", archivo, None, ".", 0)
                logger.info("Ticket enviado a impresora predeterminada: %s", default_printer)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Error al imprimir en Windows: %s", exc)
            return False

    def _imprimir_unix(self, archivo: str) -> bool:
        try:
            import subprocess

            cmd = ["lp"]
            if (self.printer_name or "").strip():
                cmd += ["-d", self.printer_name]
            cmd.append(archivo)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                logger.info("Ticket enviado a impresora (lp)")
                return True
            logger.error("Error al imprimir con lp: %s", proc.stderr)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Error al imprimir en Unix: %s", exc)
            return False
