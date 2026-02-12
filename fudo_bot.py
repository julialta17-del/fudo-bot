# =====================
# IMPORTS
# =====================
import os
import json
import time
import gspread

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials


# =====================
# GOOGLE SHEETS (SEGURO)
# =====================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

client = gspread.authorize(creds)
sheet = client.open("Prueba clientes PEYA").get_worksheet(0)

print("✅ Conectado a Google Sheets OK")


# =====================
# CHROME HEADLESS
# =====================
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 30)


# =====================
# 1. LOGIN
# =====================
driver.get("https://app-v2.fu.do/app/#!/delivery")

user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
pass_input = driver.find_element(By.ID, "password")

# 🔐 Credenciales seguras desde GitHub Secrets
user_input.send_keys(os.environ["FUDO_USER"])
pass_input.send_keys(os.environ["FUDO_PASS"])
pass_input.submit()

print("✅ Login OK")


# =====================
# 2. REFRESH
# =====================
time.sleep(5)
print("🔄 Actualizando página...")
driver.refresh()
time.sleep(15)


# =====================
# 3. CLICK EN ENTREGADOS
# =====================
try:
    entregados = driver.find_element(By.XPATH, "//*[contains(text(),'ENTREGADOS')]")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", entregados)
    time.sleep(2)
    driver.execute_script("arguments[0].click();", entregados)
    print("✅ Pestaña ENTREGADOS abierta.")
except:
    print("⚠️ No se pudo clickear ENTREGADOS.")


# =====================
# 4. MOSTRAR MÁS
# =====================
time.sleep(5)

try:
    btn_mas = driver.find_elements(By.XPATH, "//*[contains(text(), 'Mostrar más')]")
    if btn_mas and btn_mas[0].is_displayed():
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_mas[0])
        time.sleep(2)
        driver.execute_script("arguments[0].click();", btn_mas[0])
        print("✅ Botón 'Mostrar más' presionado.")
        time.sleep(8)
except:
    print("⚠️ No se encontró botón 'Mostrar más'.")


# =====================
# 5. TRANSCRIBIR PEDIDOS
# =====================
print("📋 Iniciando transcripción...")

filas = driver.find_elements(By.XPATH, "//tr[td]")
print(f"📦 Pedidos detectados: {len(filas)}")

for fila in filas:
    try:
        celdas = fila.find_elements(By.TAG_NAME, "td")

        if len(celdas) >= 5:

            id_p = celdas[0].text.strip()
            hora = celdas[1].text.strip()
            total = celdas[-1].text.strip()

            telefono = "No encontrado"
            cliente = "No encontrado"

            for i, celda in enumerate(celdas):
                texto = celda.text.strip()

                if "+54" in texto:
                    telefono = texto

                    # Nombre en celda siguiente
                    if i + 1 < len(celdas):
                        cliente = celdas[i + 1].text.strip()
                    break

            # Evitar encabezados o filas vacías
            if id_p.lower() == "id" or id_p == "":
                continue

            sheet.append_row([id_p, hora, telefono, cliente, total])
            print(f"✅ Guardado: {id_p} | {cliente} | {telefono}")

    except Exception as e:
        print(f"❌ Error en fila: {e}")


print("🏁 PROCESO TERMINADO")
driver.quit()
