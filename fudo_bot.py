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
# ESPERAR CARGA COMPLETA
# =====================
print("⏳ Esperando carga de pedidos...")
time.sleep(15)


# =====================
# ESPERAR TABLA
# =====================
wait.until(
    EC.presence_of_element_located((By.XPATH, "//table"))
)

time.sleep(5)


# =====================
# OBTENER FILAS
# =====================
filas = driver.find_elements(By.XPATH, "//table//tr")

print(f"📦 Filas detectadas: {len(filas)}")


# =====================
# TRANSCRIBIR PEDIDOS
# =====================
for fila in filas:
    try:
        celdas = fila.find_elements(By.TAG_NAME, "td")

        # Saltar encabezado
        if len(celdas) < 5:
            continue

        id_p = celdas[0].text.strip()
        hora = celdas[1].text.strip()
        telefono = celdas[3].text.strip()  # En tu imagen es la 4ta columna
        total = celdas[6].text.strip()     # En tu imagen es la última columna

        if id_p.lower() == "id" or id_p == "":
            continue

        sheet.append_row([id_p, hora, telefono, total])
        print(f"✅ Guardado: {id_p} | {telefono}")

    except Exception as e:
        print(f"❌ Error en fila: {e}")


print("🏁 PROCESO TERMINADO")
driver.quit()
