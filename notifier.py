import os
import threading
import time
from datetime import datetime
import requests

try:
    import winsound
except ImportError:
    winsound = None


class Notifier:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enable_sound = os.getenv("ENABLE_SOUND_ALARM", "true").lower() == "true"
        self._last_phantom_alert = 0.0  # Control de enfriamiento para no saturar con stock fantasma

    def _telegram_configured(self) -> bool:
        return (
            bool(self.bot_token)
            and bool(self.chat_id)
            and self.bot_token != "tu_token_aqui"
            and self.chat_id != "tu_chat_id_aqui"
        )

    def play_alarm(self, pattern: str = "stock"):
        """Reproduce una alarma sonora en la PC en segundo plano para no bloquear la compra."""
        if not self.enable_sound or winsound is None:
            return

        def _beep_worker():
            try:
                if pattern == "stock":
                    for _ in range(4):
                        winsound.Beep(1200, 220)
                        winsound.Beep(1600, 220)
                        time.sleep(0.05)
                elif pattern == "success":
                    # Fanfarria triunfal de compra exitosa
                    for freq, dur in [(659, 180), (659, 180), (659, 250), (523, 180), (659, 250), (784, 400), (392, 450)]:
                        winsound.Beep(freq, dur)
                        time.sleep(0.03)
                elif pattern == "warning":
                    for _ in range(3):
                        winsound.Beep(500, 400)
                        time.sleep(0.1)
            except Exception as e:
                print(f"[WARN] No se pudo reproducir el sonido: {e}")

        threading.Thread(target=_beep_worker, daemon=True).start()

    def _resolve_chat_id(self) -> str | None:
        """Verifica el chat_id y, si es el ID del propio bot o no es válido, intenta autodetectarlo con getUpdates."""
        bot_id_prefix = self.bot_token.split(":")[0] if ":" in self.bot_token else ""
        if self.chat_id and self.chat_id != "tu_chat_id_aqui" and self.chat_id != bot_id_prefix:
            return self.chat_id

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            resp = requests.get(url, timeout=8).json()
            if resp.get("ok") and resp.get("result"):
                for update in reversed(resp["result"]):
                    msg = update.get("message") or update.get("edited_message") or {}
                    chat = msg.get("chat", {})
                    if chat.get("id"):
                        detected_id = str(chat["id"])
                        self.chat_id = detected_id
                        print(f"[INFO] ✅ Chat ID de Telegram autodetectado: {detected_id}")
                        return detected_id
        except Exception as e:
            print(f"[WARN] No se pudo consultar getUpdates de Telegram: {e}")
        return None

    def send_telegram(self, message: str, photo_path: str | None = None, parse_mode: str = "HTML"):
        """Envía mensaje (y foto opcional) a Telegram en segundo plano con formato HTML."""
        if not self._telegram_configured():
            return

        def _send_worker():
            target_chat_id = self._resolve_chat_id()
            if not target_chat_id:
                return

            # Intentar enviar con foto si existe
            if photo_path and os.path.exists(photo_path):
                try:
                    url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
                    with open(photo_path, "rb") as img:
                        r = requests.post(
                            url,
                            data={
                                "chat_id": target_chat_id,
                                "caption": message,
                                "parse_mode": parse_mode,
                            },
                            files={"photo": img},
                            timeout=15,
                        )
                    if r.json().get("ok"):
                        print(f"[INFO] 📨 Notificación con captura enviada a Telegram.")
                        return
                except Exception as e:
                    print(f"[WARN] No se pudo enviar foto por Telegram, enviando texto: {e}")

            # Enviar mensaje de texto como método principal o respaldo
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                r = requests.post(
                    url,
                    json={
                        "chat_id": target_chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": False,
                    },
                    timeout=10,
                )
                data = r.json()
                if not data.get("ok"):
                    print(f"[WARN] ❌ Telegram rechazó el envío: {data.get('description')}")
                else:
                    print(f"[INFO] 📨 Mensaje enviado a Telegram.")
            except Exception as e:
                print(f"[WARN] Error enviando texto a Telegram: {e}")

        threading.Thread(target=_send_worker, daemon=True).start()

    def alert_stock_found(self, price: float | None, url: str, photo_path: str | None = None):
        """Notificación personalizada cuando se detecta stock / botón de compra."""
        now = datetime.now().strftime("%H:%M:%S")
        price_str = f"US${price:,.2f}" if price else "Consultar en página"
        msg = (
            "🟢 <b>¡STOCK / PREVENTA DETECTADA!</b> 🎮\n\n"
            "📦 <b>Producto:</b> Nintendo Switch™ 2 – The Legend of Zelda™ – 40th Anniversary\n"
            f"💵 <b>Precio:</b> <code>{price_str}</code>\n"
            "🏪 <b>Vendedor:</b> Amazon.com Oficial\n"
            f"⏰ <b>Hora de detección:</b> <code>{now}</code>\n"
            "⚡ <b>Acción:</b> <i>Ejecutando proceso de compra automática ahora mismo...</i>\n\n"
            f"🔗 <a href='{url}'>Abrir ficha en Amazon</a>"
        )
        print(f"\n🔔 [STOCK ENCONTRADO] Precio: {price_str}")
        self.play_alarm(pattern="stock")
        self.send_telegram(message=msg, photo_path=photo_path)

    def alert_order_success(self, price: float | None, dry_run: bool = False, photo_path: str | None = None):
        """Notificación triunfal cuando la orden ha sido realizada con éxito."""
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        price_str = f"US${price:,.2f}" if price else "Consultar en Amazon"

        if dry_run:
            msg = (
                "🧪 <b>[MODO PRUEBA - DRY RUN] BOTÓN FINAL DETECTADO</b> 🧪\n\n"
                "🎯 <b>Resultado:</b> ¡El bot llegó con éxito a la pantalla final de pago!\n"
                "📦 <b>Producto:</b> Nintendo Switch™ 2 Zelda 40th Edition\n"
                f"💵 <b>Total estimado:</b> <code>{price_str}</code>\n"
                f"⏰ <b>Hora:</b> <code>{now}</code>\n\n"
                "ℹ️ <i>No se realizó el cargo porque DRY_RUN=true está activado.</i>"
            )
        else:
            msg = (
                "🎉🎉🎉 <b>¡¡COMPRA REALIZADA CON ÉXITO!!</b> 🎉🎉🎉\n\n"
                "✅ <b>¡Tu orden ha sido tramitada en Amazon!</b>\n"
                "📦 <b>Producto:</b> Nintendo Switch™ 2 – The Legend of Zelda™ – 40th Anniversary\n"
                f"💵 <b>Monto:</b> <code>{price_str}</code>\n"
                f"⏰ <b>Fecha y Hora:</b> <code>{now}</code>\n\n"
                "👉 <i>Revisa tu correo asociado a Amazon y la sección 'Mis Pedidos' para ver la confirmación y fecha de entrega.</i>"
            )

        print(f"\n🏆 [ORDEN EXITOSA] {now}")
        self.play_alarm(pattern="success")
        self.send_telegram(message=msg, photo_path=photo_path)

    def alert_phantom_stock(self, price: float | None, photo_path: str | None = None):
        """Notificación cuando Amazon muestra el botón pero reporta Cantidad: 0 en backend (con enfriamiento de 5 min)."""
        now = time.time()
        # Enviar como máximo una alerta de stock fantasma cada 5 minutos para evitar spam si Amazon lo congela
        if now - self._last_phantom_alert < 300:
            return
        self._last_phantom_alert = now

        price_str = f"US${price:,.2f}" if price else "N/A"
        time_str = datetime.now().strftime("%H:%M:%S")
        msg = (
            "⚠️ <b>Aviso de Stock Fantasma en Amazon</b>\n\n"
            f"El botón de preventa estuvo activo a <code>{price_str}</code> ({time_str}), pero Amazon reportó:\n"
            "<i>'Cantidad: 0 - La cantidad solicitada ya no está disponible'</i>.\n\n"
            "🔄 <b>El bot continúa monitoreando automáticamente para atrapar las unidades en cuanto liberen inventario real.</b>"
        )
        print("\n⚠️ [AVISO TELEGRAM] Stock fantasma detectado.")
        self.send_telegram(message=msg, photo_path=photo_path)

    def alert_attention_required(self, reason: str, photo_path: str | None = None):
        """Notificación cuando se requiere intervención manual (CVV, 2FA, Captcha)."""
        time_str = datetime.now().strftime("%H:%M:%S")
        msg = (
            "🚨 <b>¡INTERVENCIÓN MANUAL REQUERIDA!</b> 🚨\n\n"
            f"⚠️ <b>Motivo:</b> {reason}\n"
            f"⏰ <b>Hora:</b> <code>{time_str}</code>\n\n"
            "👉 <b>Por favor abre la ventana de Google Chrome en tu PC y completa la verificación de inmediato.</b>"
        )
        print(f"\n🚨 [ACCION REQUERIDA] {reason}")
        self.play_alarm(pattern="warning")
        self.send_telegram(message=msg, photo_path=photo_path)

    def alert_all(self, message: str, alarm_pattern: str = "stock", photo_path: str | None = None):
        """Método genérico para mensajes de prueba y logs generales."""
        print(f"\n🔔 [ALERTA] {message}")
        self.play_alarm(pattern=alarm_pattern)
        self.send_telegram(message=message, photo_path=photo_path)
