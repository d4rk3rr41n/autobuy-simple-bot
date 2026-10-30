# 🎮 Amazon Auto-Buy & Restock Bot (Python + Playwright)

Bot automatizado de monitoreo de stock y compra rápida en **Amazon** desarrollado en **Python** con **Playwright**. Diseñado originalmente para capturar preventas y *drops* de alta demanda (como la **Nintendo Switch™ 2 – The Legend of Zelda™ – 40th Anniversary Edition**), ejecutándose en un perfil de **Google Chrome independiente** con alertas enriquecidas en **Telegram** y **alarma sonora local**.

---

## ✨ Características Principales

* 🌐 **Navegador Chrome Independiente y Persistente:** Abre una instancia aislada de Google Chrome (`chrome_profile/`) que conserva tus cookies y sesión de Amazon sin interferir con tu navegador personal.
* ⚡ **Monitoreo Inteligente con *Jitter* Anti-Detección:** Refresca la página en intervalos rápidos configurables (ej. ~4.2 a 5.8 segundos) con variación aleatoria para evitar bloqueos de IP o WAF de Amazon.
* 🛡️ **Filtro Anti-Revendedores (*Anti-Scalpers*):** Verifica en milisegundos que el precio no supere tu presupuesto máximo (`MAX_PRICE`) y que el vendedor sea **Amazon.com Oficial**.
* 👻 **Detección Instantánea de Stock Fantasma (*Ghost Stock*):** Si Amazon muestra el botón de preventa en caché pero reporta `"Cantidad: 0"` en el checkout, el bot lo detecta en `< 300ms` y regresa inmediatamente a monitorear sin quedarse atascado.
* 🔄 **Autorecuperación de Navegación:** Si Amazon muestra una página de error (*"Dogs of Amazon"*) o desvía la URL durante un intento fallido, el bot redirige automáticamente a la ficha del producto.
* 📲 **Notificaciones HTML Personalizadas en Telegram:** Envía alertas detalladas con capturas de pantalla adjuntas y autodetecta tu `TELEGRAM_CHAT_ID` con solo escribirle un mensaje a tu bot.
* 🔊 **Alarma Sonora Asíncrona en PC (Windows):** Reproduce patrones de sonido distintos en segundo plano (detección de stock, fanfarria de compra exitosa o alerta de CAPTCHA/CVV) sin retrasar los clics de compra.
* 🧪 **Modo de Prueba Seguro (`DRY_RUN`):** Permite simular todo el flujo hasta la pantalla final de pago sin realizar cargos reales.

---

## 📋 Requisitos Previos

* **Sistema Operativo:** Windows 10/11 (para la alarma sonora nativa con `winsound`; compatible con Linux/macOS desactivando el sonido o usando solo Telegram).
* **Python:** 3.10 o superior.
* **Google Chrome:** Instalado en el sistema.

---

## 🚀 Instalación y Configuración

### 1. Clonar el repositorio e instalar dependencias

```powershell
git clone https://github.com/d4rk3rr41n/autobuy-simple-bot.git
cd autobuy-simple-bot

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configurar las variables de entorno (`.env`)

Copia el archivo de plantilla [`.env.example`](.env.example) a un nuevo archivo llamado `.env`:

```powershell
Copy-Item .env.example .env
```

Edita `.env` con tus parámetros:

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `PRODUCT_URL` | Enlace directo al producto en Amazon | URL del producto |
| `ASIN` | Código ASIN del producto en Amazon | `B0HJ6F8L6V` |
| `MAX_PRICE` | Precio máximo permitido en USD (`0` para sin límite) | `550.00` |
| `STRICT_AMAZON_SELLER` | Solo comprar si es vendido por Amazon.com (`true`/`false`) | `true` |
| `REFRESH_SECONDS` | Tiempo base de refresco en segundos (aplica *jitter* de `±0.8s`) | `5` |
| `DRY_RUN` | `true` = Modo prueba (no paga) / `false` = Compra real automática | `true` |
| `TELEGRAM_BOT_TOKEN` | Token de tu bot entregado por `@BotFather` | `tu_token_aqui` |
| `TELEGRAM_CHAT_ID` | Tu Chat ID de Telegram (se autodetecta si le escribes al bot) | `tu_chat_id_aqui` |
| `ENABLE_SOUND_ALARM` | Activa o desactiva la alarma sonora en la PC (`true`/`false`) | `true` |

---

## 📲 Configuración de Notificaciones en Telegram

1. Abre Telegram, busca a **`@BotFather`** y envía el comando `/newbot`.
2. Copia el **Token** que te entregue y pégalo en `TELEGRAM_BOT_TOKEN` dentro de tu archivo `.env`.
3. Abre el chat de tu nuevo bot en Telegram y presiona **"Iniciar" (`/start`)** o envíale un `"Hola"`.
4. Ejecuta el comando de prueba para verificar el sonido y autodetectar tu Chat ID:
   ```powershell
   python bot.py --test-alert
   ```

---

## 🔐 Paso Previo Obligatorio: Iniciar Sesión en Amazon (`--setup`)

Para que la compra se realice en un clic sin pedir contraseña ni códigos OTP en el momento crítico, guarda tu sesión en el perfil aislado antes de iniciar el monitoreo:

```powershell
python bot.py --setup
```

1. Se abrirá una ventana independiente de **Google Chrome**.
2. Inicia sesión en tu cuenta de Amazon marcando la casilla **"Recuérdame"**.
3. Verifica que tengas configurada una **dirección de envío** y un **método de pago predeterminados** (activa la opción *Comprar ya / 1-Click* en tu cuenta).
4. Regresa a la terminal y presiona **ENTER** para guardar el perfil y cerrar el navegador.

---

## 🛒 Uso y Comandos Disponibles

### Iniciar monitoreo continuo
```powershell
python bot.py
```

### Probar alarma local y plantillas de Telegram
```powershell
python bot.py --test-alert
```

### Ejecutar un número limitado de ciclos de prueba
```powershell
python bot.py --max-cycles=2
```

---

## 🔒 Seguridad y Privacidad (Git)

El archivo [`.gitignore`](.gitignore) está configurado para proteger tu información sensible y **evitar que se suban a GitHub**:
* `.env` (Tus tokens de Telegram y configuración personal).
* `chrome_profile/` (Tus cookies y sesión activa de Amazon).
* `screenshots/` (Capturas de pantalla del checkout que pueden mostrar tu nombre o dirección).
* `.venv/` (Entorno virtual de Python).

---

## ⚠️ Aviso Legal (*Disclaimer*)

Este software fue creado únicamente con fines educativos y de uso personal. El usuario es responsable de cumplir con los Términos de Servicio de Amazon y de verificar el límite de precio (`MAX_PRICE`) y el estado del modo `DRY_RUN` antes de dejar el bot en ejecución desatendida.
