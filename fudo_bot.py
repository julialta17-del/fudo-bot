# =====================
# IMPORTS
# =====================
import os
import json
import time
import re
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
# GOOGLE SHEETS
# =====================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

client = gspread.authorize(creds)
sheet = client.open("Prueba clientes PEYA").get_worksheet(0)

print("✅ Conectado a Google Sheets")


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
# LOGIN
# =====================
driver.get("https://app-v2.fu.do/app/#!/delivery")

user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
pass_input = driver.find_element(By.ID, "password")

user_input.send_keys(os.environ["FUDO_USER"])
pass_input.send_keys(os.environ["FUDO_PASS"])
pass_input.submit()

print("✅ Login OK")


# =====================
# ESPERAR CARGA
# =====================
time.sleep(5)
driver.refresh()
time.sleep(15)


# =====================
# CLICK ENTREGADOS
# =====================
try:
    entregados = driver.find_element(By.XPATH, "//*[contains(text(),'ENTREGADOS')]")
    driver.execute_script("arguments[0].click();", entregados)
    print("✅ Pestaña ENTREGADOS abierta")
except:
    print("⚠️ No se pudo abrir ENTREGADOS")

time.sleep(8)


# =====================
# ESPERAR TABLA
# =====================
print("⏳ Esperando tabla...")

wait.until(
    EC.presence_of_element_located((By.XPATH, "//table"))
)

time.sleep(5)

filas = driver.find_elements(By.XPATH, "//table//tbody//tr")
print(f"📦 Pedidos detectados: {len(filas)}")


# =====================
# TRANSCRIBIR SOLO TELÉFONO
# =====================
for fila in filas:
    try:
        celdas = fila.find_elements(By.TAG_NAME, "td")

        if len(celdas) >= 5:

            id_p = celdas[0].text.strip()
            hora = celdas[1].text.strip()
            total = celdas[-1].text.strip()

            telefono = "No encontrado"

            for celda in celdas:
                texto = celda.text.strip()

                # Extraer solo números
                numeros = re.sub(r"\D", "", texto)

                if len(numeros) >= 8:
                    telefono = numeros
                    break

            if id_p.lower() == "id" or id_p == "":
                continue

            sheet.append_row([id_p, hora, telefono, total])
            print(f"✅ Guardado: {id_p} | {telefono}")

    except Exception as e:
        print(f"❌ Error en fila: {e}")


print("🏁 PROCESO TERMINADO")
driver.quit()
