import os, time, zipfile, shutil, json, pytz
import pandas as pd
import gspread
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN DE TIEMPO ARGENTINA ---
arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
fecha_hoy_arg = datetime.now(arg_tz).strftime('%d/%m/%Y')

# --- 2. CONFIGURACIÓN DE RUTAS ---
base_path = os.path.join(os.getcwd(), "descargas")
ruta_excel = os.path.join(base_path, "ventas.xls")
os.makedirs(base_path, exist_ok=True)

def ejecutar_todo():
    # --- CONFIGURACIÓN CHROME ---
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_experimental_option("prefs", {"download.default_directory": base_path})

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 20)

    try:
        # LOGIN
        driver.get("https://app-v2.fu.do/app/#!/sales")
        wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
        driver.find_element(By.ID, "password").send_keys("bigsexta")
        driver.find_element(By.ID, "password").submit()

        # ESPERAR CARGA Y REFRESCAR
        time.sleep(5) 
        driver.refresh()
        print("Página refrescada. Esperando 5 segundos...")
        time.sleep(5)

        # DESCARGAR
        exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
        exportar_btn.click()
        time.sleep(10) # Tiempo para que baje el ZIP

        # PROCESAR ZIP
        archivos_zip = [os.path.join(base_path, f) for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if archivos_zip:
            zip_file = max(archivos_zip, key=os.path.getctime)
            with zipfile.ZipFile(zip_file, 'r') as z:
                z.extract(z.namelist()[0], base_path)
                os.rename(os.path.join(base_path, z.namelist()[0]), ruta_excel)
            os.remove(zip_file)

        # --- 3. PROCESAR CON PANDAS Y SUBIR ---
        df = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
        # Filtro de seguridad: Solo lo que diga la fecha de hoy en Argentina
        # (Esto evita el error de las 23:30)
        df['Fecha_Texto'] = pd.to_datetime(df['Creación'], unit='D', origin='1899-12-30').dt.strftime('%d/%m/%Y')
        consolidado = df[df['Fecha_Texto'] == fecha_hoy_arg]

        if not consolidado.empty:
            subir_a_google(consolidado)
            print(f"Éxito: {len(consolidado)} ventas subidas de la fecha {fecha_hoy_arg}")
        else:
            print(f"Ojo: No hay ventas para la fecha {fecha_hoy_arg} todavía.")

    finally:
        driver.quit()

def subir_a_google(df):
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Analisis Fudo").worksheet("Hoja 1")
    sheet.clear()
    datos = [df.columns.values.tolist()] + df.fillna("").astype(str).values.tolist()
    sheet.update(range_name='A1', values=datos)

if __name__ == "__main__":
    ejecutar_todo()
