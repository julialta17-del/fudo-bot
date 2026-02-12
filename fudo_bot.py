import time
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ==============================
# GOOGLE SHEETS
# ==============================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credenciales.json", scope
)
client = gspread.authorize(creds)
sheet = client.open("Pedidos Fudo").sheet1

print("Conectado a Google Sheets OK")

# ==============================
# SELENIUM
# ==============================

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--start-maximized")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
)

driver.get("https://panel.fudo.com.ar/login")

time.sleep(3)

# LOGIN
driver.find_element(By.NAME, "email").send_keys("TU_MAIL")
driver.find_element(By.NAME, "password").send_keys("TU_PASSWORD")
driver.find_element(By.NAME, "password").send_keys(Keys.RETURN)

time.sleep(5)
print("Login OK")

# Ir a ENTREGADOS
driver.get("https://panel.fudo.com.ar/orders?status=delivered")

time.sleep(5)

print("Actualizando página...")
driver.refresh()
time.sleep(5)

# ==============================
# SCROLL HASTA QUE NO CARGUE MÁS
# ==============================

last_height = driver.execute_script("return document.body.scrollHeight")

while True:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    new_height = driver.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        break
    last_height = new_height

print("Scroll completo.")

# ==============================
# BUSCAR PEDIDOS
# ==============================

pedidos = driver.find_elements(By.XPATH, "//div[contains(@class,'order-card')]")

print(f"Pedidos detectados: {len(pedidos)}")

for pedido in pedidos:
    try:
        texto = pedido.text

        # Buscar cualquier número largo
        match = re.search(r'\d{10,13}', texto)

        telefono = "No encontrado"

        if match:
            numero = match.group()

            # Normalizar a +54
            if not numero.startswith("54"):
                numero = "54" + numero

            telefono = "+" + numero

        # Buscar fecha simple
        fecha_match = re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', texto)
        fecha = fecha_match.group() if fecha_match else "Sin fecha"

        sheet.append_row([fecha, telefono])

        print(f"Guardado | Fecha: {fecha} | Tel: {telefono}")

    except Exception as e:
        print("Error en pedido:", e)

driver.quit()
print("Proceso terminado.")
