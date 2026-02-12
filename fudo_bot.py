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
# 1. INICIAR SESIÓN
# =====================
driver.get("https://app-v2.fu.do/app/#!/delivery")

user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
pass_input = driver.find_element(By.ID, "password")

user_input.send_keys(FUDO_USER)
pass_input.send_keys(FUDO_PASS)
pass_input.submit()

print("✅ Login OK")

# =====================
# 2. ACTUALIZAR PÁGINA
# =====================
time.sleep(5)
print("🔄 Actualizando página...")
driver.refresh()
time.sleep(15)

# =====================
# 3. SCROLL Y CLIC EN ENTREGADOS
# =====================
try:
    entregados = driver.find_element(By.XPATH, "//*[contains(text(),'ENTREGADOS')]")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", entregados)
    time.sleep(2)
    driver.execute_script("arguments[0].click();", entregados)
    print("✅ Pestaña ENTREGADOS abierta.")
    time.sleep(8)
except Exception as e:
    print("⚠️ No se pudo clickear ENTREGADOS:", e)

# =====================
# 4. MOSTRAR MÁS RESULTADOS
# =====================
try:
    btn_mas = driver.find_elements(By.XPATH, "//*[contains(text(), 'Mostrar más')]")
    if btn_mas and btn_mas[0].is_displayed():
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_mas[0])
        time.sleep(2)
        driver.execute_script("arguments[0].click();", btn_mas[0])
        print("✅ Botón 'Mostrar más' presionado.")
        time.sleep(8)
except:
    print("ℹ️ No se encontró botón de carga extra.")

# =====================
# 5. TRANSCRIBIR DATOS
# =====================
print("📝 Iniciando transcripción...")

filas = driver.find_elements(By.XPATH, "//tr[td]")
print(f"📦 Pedidos detectados: {len(filas)}")

for fila in filas:
    try:
        celdas = fila.find_elements(By.TAG_NAME, "td")

        if len(celdas) >= 5:

            id_p = celdas[0].text.strip()
            hora = celdas[1].text.strip()
            cli = celdas[4].text.strip()
            tot = celdas[-1].text.strip()

            telefono = "No encontrado"

            for celda in celdas:
                texto_celda = celda.text.strip()
                if "+54" in texto_celda:
                    telefono = texto_celda
                    break

            if id_p.lower() == "id" or id_p == "":
                continue

            sheet.append_row([id_p, hora, telefono, cli, tot])
            print(f"✅ Guardado pedido {id_p} | Tel: {telefono}")

    except Exception as e:
        print(f"❌ Error en fila: {e}")

print("🏁 PROCESO TERMINADO")

driver.quit()


