from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import os
import json
from webdriver_manager.chrome import ChromeDriverManager
import gspread
from google.oauth2.service_account import Credentials

# =====================
# VARIABLES SEGURAS (GITHUB SECRETS)
# =====================
FUDO_USER = os.environ["FUDO_USER"]
FUDO_PASS = os.environ["FUDO_PASS"]
GOOGLE_CREDS_JSON = os.environ["GOOGLE_CREDENTIALS"]

# =====================
# CREAR credentials.json DESDE SECRET
# =====================
with open("credentials.json", "w") as f:
    f.write(GOOGLE_CREDS_JSON)

# =====================
# GOOGLE SHEETS
# =====================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=SCOPES
)

client = gspread.authorize(creds)
sheet = client.open("Prueba clientes PEYA").get_worksheet(0)

print("✅ Conectado a Google Sheets")

# =====================
# CHROME (GITHUB READY)
# =====================
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 30)

# =====================
# 1. LOGIN
# =====================
driver.get("https://app-v2.fu.do/app/")

user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
pass_input = driver.find_element(By.ID, "password")

user_input.send_keys(FUDO_USER)
pass_input.send_keys(FUDO_PASS)
pass_input.submit()

print("✅ Login enviado")
time.sleep(8)

# =====================
# 2. IR A DELIVERY Y ACTUALIZAR
# =====================
driver.get("https://app-v2.fu.do/app/#!/delivery")
time.sleep(8)

print("🔄 Actualizando...")
driver.refresh()
time.sleep(12)

# =====================
# 3. SCROLL HASTA ENTREGADOS Y CLICK
# =====================
print("🔍 Buscando pestaña ENTREGADOS...")

encontrado = False
for i in range(10):
    elementos = driver.find_elements(By.XPATH, "//*[contains(text(),'ENTREGADOS')]")
    if elementos:
        entregados = elementos[0]
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", entregados)
        time.sleep(2)
        driver.execute_script("arguments[0].click();", entregados)
        print("✅ Click en ENTREGADOS")
        encontrado = True
        break
    else:
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(2)

if not encontrado:
    print("❌ No se encontró ENTREGADOS")

time.sleep(8)

# =====================
# 4. CLIC EN "MOSTRAR MÁS" HASTA QUE NO EXISTA
# =====================
print("🔄 Cargando todos los pedidos...")

while True:
    botones = driver.find_elements(By.XPATH, "//*[contains(text(),'Mostrar más')]")
    if botones and botones[0].is_displayed():
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botones[0])
        time.sleep(2)
        driver.execute_script("arguments[0].click();", botones[0])
        print("➕ Click en Mostrar más")
        time.sleep(6)
    else:
        print("✅ No hay más resultados para cargar")
        break

# =====================
# 5. BUSCAR TODOS LOS +54 VISIBLES
# =====================
print("📞 Buscando teléfonos +54...")

elementos_tel = driver.find_elements(By.XPATH, "//*[contains(text(),'+54')]")
print(f"📦 Teléfonos encontrados: {len(elementos_tel)}")

for tel in elementos_tel:
    telefono = tel.text.strip()
    if telefono:
        sheet.append_row(["", "", telefono, "", ""])
        print(f"✅ Guardado: {telefono}")

print("🏁 PROCESO TERMINADO")


