import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

from notifier import Notifier

load_dotenv()

PRODUCT_URL = os.getenv(
    "PRODUCT_URL",
    "https://www.amazon.com/-/es/gp/product/B0HJ6F8L6V/ref=ox_sc_saved_image_1?smid=ATVPDKIKX0DER&psc=1",
)
REFRESH_SECONDS = float(os.getenv("REFRESH_SECONDS", "8"))
MAX_PRICE = float(os.getenv("MAX_PRICE", "0"))
STRICT_AMAZON_SELLER = os.getenv("STRICT_AMAZON_SELLER", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

BASE_DIR = Path(__file__).parent
CHROME_PROFILE_DIR = BASE_DIR / "chrome_profile"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


def log(msg: str):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")


def parse_price(price_text: str) -> float | None:
    """Extrae el valor numérico de un texto de precio como 'US$449.99' o '$449,99'."""
    if not price_text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", price_text.strip())
    if not cleaned:
        return None
    # Si tiene tanto coma como punto, identificar cuál es el separador decimal
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Si termina en 2 dígitos tras la coma, es decimal (ej. 499,99)
        parts = cleaned.split(",")
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_current_price(page: Page) -> float | None:
    """Busca el precio actual dentro de la caja de compra (BuyBox)."""
    price_selectors = [
        "#corePrice_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        "#price_inside_buybox",
        "#newBuyBoxPrice",
        "#tp_price_block_total_price_ww .a-offscreen",
    ]
    for selector in price_selectors:
        loc = page.locator(selector).first
        if loc.count() > 0:
            try:
                text = loc.inner_text(timeout=800)
                val = parse_price(text)
                if val is not None:
                    return val
            except Exception:
                continue
    return None


def is_official_amazon_seller(page: Page) -> bool:
    """Verifica si el producto es vendido por Amazon.com."""
    seller_selectors = [
        "#merchant-info",
        "#tabular-buybox",
        "#fulfillerInfoFeature_feature_div",
        "#sellerProfileTriggerId",
    ]
    combined_text = ""
    for selector in seller_selectors:
        loc = page.locator(selector).first
        if loc.count() > 0:
            try:
                combined_text += " " + loc.inner_text(timeout=800).lower()
            except Exception:
                continue

    # Si no se muestra bloque de vendedor pero el parámetro smid=ATVPDKIKX0DER tiene BuyBox activo, permitir
    if not combined_text.strip():
        return True

    return "amazon.com" in combined_text or "amazon" in combined_text


def check_captcha(page: Page, notifier: Notifier) -> bool:
    """Detecta si Amazon muestra un CAPTCHA y avisa al usuario para que lo resuelva en la ventana."""
    captcha_loc = page.locator("form[action*='validateCaptcha'], #captchacharacters")
    if captcha_loc.count() > 0 and captcha_loc.first.is_visible():
        snap = str(SCREENSHOTS_DIR / f"captcha_{int(time.time())}.png")
        page.screenshot(path=snap)
        notifier.alert_attention_required(
            reason="Amazon solicitó resolver un CAPTCHA en la ventana de Chrome",
            photo_path=snap,
        )
        log("Esperando a que resuelvas el CAPTCHA en la ventana de Chrome...")
        while captcha_loc.count() > 0 and captcha_loc.first.is_visible():
            time.sleep(2)
        log("CAPTCHA resuelto. Reanudando monitoreo...")
        return True
    return False


def complete_checkout(page: Page, notifier: Notifier, price: float | None = None) -> bool:
    """Intenta finalizar la orden en el modal Turbo Checkout o en la página de Checkout estándar."""
    log("⚡ Entrando al flujo de Checkout rápido...")

    # 1. Revisar si se abrió el iframe de Turbo Checkout (1-Click modal dentro de la página)
    turbo_iframe = page.frame_locator("#turbo-checkout-iframe")
    turbo_btn = turbo_iframe.locator("#turbo-checkout-pyo-button, input[type='submit']")

    # 2. Botones de "Realizar tu pedido" en la página estándar de checkout de Amazon
    place_order_selectors = [
        "input[name='placeYourOrder1']",
        "#submitOrderButtonId input",
        "#bottomSubmitOrderButtonId input",
        "input[aria-labelledby*='submitOrderButtonId']",
        "#placeYourOrder input",
    ]

    # Esperar hasta 10 segundos a que aparezca cualquiera de los botones finales de orden
    deadline = time.time() + 10.0
    while time.time() < deadline:
        # Detectar de inmediato si Amazon arrojó "Cantidad: 0 / no disponible" en el checkout
        try:
            body_text = page.locator("body").inner_text(timeout=400).lower()
            if (
                "la cantidad solicitada ya no está disponible" in body_text
                or "actualiza tus productos" in body_text
                or "este producto no está disponible" in body_text
            ):
                snap = str(SCREENSHOTS_DIR / f"phantom_stock_{int(time.time())}.png")
                page.screenshot(path=snap)
                log("⚠️ Stock fantasma detectado por Amazon en el checkout (Cantidad asignada: 0). Regresando de inmediato...")
                notifier.alert_phantom_stock(price=price, photo_path=snap)
                return False
        except Exception:
            pass

        # Revisar Turbo Checkout Iframe
        try:
            if turbo_btn.first.is_visible(timeout=300):
                snap = str(SCREENSHOTS_DIR / f"checkout_ready_{int(time.time())}.png")
                page.screenshot(path=snap)
                if DRY_RUN:
                    notifier.alert_order_success(price=price, dry_run=True, photo_path=snap)
                    return True
                else:
                    turbo_btn.first.click()
                    time.sleep(3)
                    final_snap = str(SCREENSHOTS_DIR / f"order_placed_{int(time.time())}.png")
                    page.screenshot(path=final_snap)
                    notifier.alert_order_success(price=price, dry_run=False, photo_path=final_snap)
                    return True
        except Exception:
            pass

        # Revisar página estándar de Checkout
        for sel in place_order_selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() > 0 and loc.is_visible(timeout=200):
                    snap = str(SCREENSHOTS_DIR / f"checkout_ready_{int(time.time())}.png")
                    page.screenshot(path=snap)
                    if DRY_RUN:
                        notifier.alert_order_success(price=price, dry_run=True, photo_path=snap)
                        return True
                    else:
                        loc.click()
                        time.sleep(4)
                        final_snap = str(SCREENSHOTS_DIR / f"order_placed_{int(time.time())}.png")
                        page.screenshot(path=final_snap)
                        notifier.alert_order_success(price=price, dry_run=False, photo_path=final_snap)
                        return True
            except Exception:
                continue

        time.sleep(0.3)

    # Si pidió iniciar sesión o confirmar tarjeta/CVV
    snap = str(SCREENSHOTS_DIR / f"checkout_attention_{int(time.time())}.png")
    page.screenshot(path=snap)
    notifier.alert_attention_required(
        reason="Amazon requiere confirmación de método de pago (CVV) o dirección de entrega",
        photo_path=snap,
    )
    return False


def main():
    notifier = Notifier()
    if "--test-alert" in sys.argv:
        log("🔊 Probando alarma sonora y notificaciones personalizadas de Telegram...")
        notifier.alert_stock_found(
            price=519.99,
            url=PRODUCT_URL,
        )
        time.sleep(1.5)
        notifier.alert_order_success(
            price=519.99,
            dry_run=False,
        )
        time.sleep(4)
        return

    setup_mode = "--setup" in sys.argv
    max_cycles = 0
    for arg in sys.argv[1:]:
        if arg.startswith("--max-cycles="):
            try:
                max_cycles = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    print("=" * 68)
    print(" 🎮 BOT DE COMPRA AMAZON - NINTENDO SWITCH 2 ZELDA 40TH EDITION")
    print("=" * 68)
    print(f" • URL Objetivo : {PRODUCT_URL}")
    print(f" • Refresco     : Cada {REFRESH_SECONDS} segundos")
    print(f" • Precio Máx.  : {'$' + str(MAX_PRICE) if MAX_PRICE > 0 else 'Sin límite'}")
    print(f" • Solo Amazon  : {'Sí' if STRICT_AMAZON_SELLER else 'No'}")
    print(f" • Modo Prueba  : {'ACTIVADO (No gasta dinero)' if DRY_RUN else 'DESACTIVADO (COMPRA REAL)'}")
    print(f" • Perfil Chrome: {CHROME_PROFILE_DIR}")
    print("=" * 68)

    with sync_playwright() as p:
        # Abre un navegador Google Chrome independiente con su propio perfil persistente
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Ocultar propiedad navigator.webdriver
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        if setup_mode:
            log("🔧 MODO CONFIGURACIÓN: Abriendo Amazon.com para que inicies sesión...")
            page.goto("https://www.amazon.com", wait_until="domcontentloaded")
            print("\n👉 Por favor inicia sesión en tu cuenta de Amazon en la ventana de Chrome que se abrió.")
            print("👉 Asegúrate de marcar 'Recuérdame' y tener activo 1-Click / dirección y tarjeta predeterminadas.")
            input("\n✅ Cuando hayas terminado de iniciar sesión, presiona ENTER aquí para guardar y cerrar...")
            context.close()
            return

        log("Abriendo página del producto en navegador Chrome independiente...")
        try:
            page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError:
            log("Tiempo de carga inicial agotado, continuando con el ciclo de monitoreo...")

        attempt = 0
        while True:
            attempt += 1
            cycle_start = time.time()

            try:
                # Si el navegador fue redirigido fuera de la página del producto (ej. pantalla del perro o error), volver a PRODUCT_URL
                current_url = page.url.lower()
                is_dog_or_error = (
                    "dogs of amazon" in page.content().lower()
                    or "este producto no está disponible" in page.content().lower()
                    or "not-found" in current_url
                    or ("gp/product" not in current_url and "/dp/" not in current_url)
                )

                if attempt > 1:
                    if is_dog_or_error:
                        log("⚠️ Detectada página de error/perro o desvío de URL. Redirigiendo a la página del producto...")
                        page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=15000)
                    else:
                        page.reload(wait_until="domcontentloaded", timeout=12000)

                check_captcha(page, notifier)

                # Buscar botones de compra o preventa disponibles (Comprar ya, Reserva ahora, Agregar al carrito)
                buy_now_selectors = [
                    "#buy-now-button",
                    "input#buy-now-button",
                    "#preOrderButton",
                    "input[name*='submit.preorder']",
                    "input[name*='submit.buy-now']",
                ]
                buy_now_btn = page.locator(", ".join(buy_now_selectors)).first

                add_to_cart_selectors = [
                    "#add-to-cart-button",
                    "input#add-to-cart-button",
                    "#add-to-cart-button-ubb",
                ]
                add_to_cart_btn = page.locator(", ".join(add_to_cart_selectors)).first

                has_buy_now = buy_now_btn.count() > 0 and buy_now_btn.is_visible()
                has_add_cart = add_to_cart_btn.count() > 0 and add_to_cart_btn.is_visible()

                if has_buy_now or has_add_cart:
                    price = extract_current_price(page)
                    seller_ok = is_official_amazon_seller(page) if STRICT_AMAZON_SELLER else True

                    log(f"✨ ¡STOCK/PREVENTA DETECTADO! (Intento #{attempt}) | Precio: {price} | Vendedor Oficial: {seller_ok}")

                    # Validar precio máximo
                    if MAX_PRICE > 0 and price is not None and price > MAX_PRICE:
                        log(
                            f"⛔ Precio actual (${price}) supera el máximo configurado (${MAX_PRICE}). Ignorando revendedor..."
                        )
                    elif STRICT_AMAZON_SELLER and not seller_ok:
                        log("⛔ El vendedor no parece ser Amazon.com oficial. Ignorando oferta de tercero...")
                    else:
                        snap_stock = str(SCREENSHOTS_DIR / f"stock_found_{int(time.time())}.png")
                        page.screenshot(path=snap_stock)
                        notifier.alert_stock_found(
                            price=price,
                            url=PRODUCT_URL,
                            photo_path=snap_stock,
                        )

                        if has_buy_now:
                            log("🚀 Haciendo clic en 'Comprar ahora / Reserva ahora'...")
                            buy_now_btn.click()
                            if complete_checkout(page, notifier, price=price):
                                log("✅ Compra exitosa. Manteniendo navegador abierto...")
                                time.sleep(300)
                                break
                            else:
                                log("↩️ Checkout no completado (posible drop agotado). Volviendo inmediatamente al producto...")
                                page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=10000)
                        elif has_add_cart:
                            log("🛒 Haciendo clic en 'Agregar al carrito'...")
                            add_to_cart_btn.click()
                            page.wait_for_load_state("domcontentloaded", timeout=8000)
                            proceed_btn = page.locator(
                                "input[name='proceedToRetailCheckout'], #sc-buy-box-ptc-button input, a[href*='proceedToCheckout']"
                            ).first
                            if proceed_btn.count() > 0 and proceed_btn.is_visible():
                                proceed_btn.click()
                            else:
                                page.goto(
                                    "https://www.amazon.com/gp/cart/view.html",
                                    wait_until="domcontentloaded",
                                )
                            if complete_checkout(page, notifier, price=price):
                                log("✅ Compra exitosa. Manteniendo navegador abierto...")
                                time.sleep(300)
                                break
                            else:
                                log("↩️ Checkout no completado. Volviendo inmediatamente al producto...")
                                page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=10000)
                else:
                    log(f"Intento #{attempt}: Sin stock disponible...")

            except Exception as e:
                log(f"⚠️ Error durante la comprobación (Intento #{attempt}): {e}")

            if max_cycles > 0 and attempt >= max_cycles:
                log(f"✅ Prueba de {max_cycles} ciclos completada correctamente.")
                break

            # Refresco rápido con jitter (variación de +/- 0.8s) para no ser detectado por Amazon
            import random
            target_delay = max(4.0, REFRESH_SECONDS)
            jittered_delay = target_delay + random.uniform(-0.8, 0.8)
            elapsed = time.time() - cycle_start
            sleep_time = max(1.5, jittered_delay - elapsed)
            time.sleep(sleep_time)


if __name__ == "__main__":
    main()
