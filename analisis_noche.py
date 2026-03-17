import os
import time
import zipfile
import shutil
import json
import pandas as pd
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- 1. CONFIGURACIÓN ---
ahora = datetime.now()
ayer = ahora - timedelta(days=1)
manana = ahora + timedelta(days=1)
fecha_inicio = ayer.strftime("%Y-%m-%d")
fecha_fin = manana.strftime("%Y-%m-%d")

base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
ruta_excel = os.path.join(temp_excel_path, "ventas.xls")

os.makedirs(temp_excel_path, exist_ok=True)

def subir_a_google(consolidado):
    print("--- PASO: CONEXIÓN A GOOGLE ---")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Intento de lectura de credenciales
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        if not os.path.exists('credentials.json'):
            print("❌ ERROR: No existe el archivo credentials.json ni la variable de entorno.")
            return
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    
    try:
        # ⚠️ VERIFICA QUE EL NOMBRE DEL LIBRO SEA EXACTAMENTE ESTE:
        spreadsheet = client.open("Analisis Fudo")
        # ⚠️ VERIFICA QUE LA PESTAÑA SE LLAME "Hoja 1":
        sheet_data = spreadsheet.worksheet("Hoja 1")
        
        print("🧹 Limpiando Hoja 1...")
        sheet_data.clear()
        
        print("📝 Preparando datos para subir...")
        datos_finales = [consolidado.columns.values.tolist()] + \
                         consolidado.fillna("").astype(str).values.tolist()
        
        # Usamos update sin especificar rango para que tome todo automáticamente
        sheet_data.update(datos_finales)
        print("🚀 ¡DATOS PEGADOS CON ÉXITO EN GOOGLE SHEETS!")
        
    except gspread.exceptions.SpreadsheetNotFound:
        print("❌ ERROR: No se encontró el archivo 'Analisis Fudo'. ¿Compartiste el archivo con el email del bot?")
    except gspread.exceptions.WorksheetNotFound:
        print("❌ ERROR: No se encontró la pestaña 'Hoja 1'.")
    except Exception as e:
        print(f"❌ ERROR INESPERADO EN GOOGLE: {e}")

# --- 2. SELENIUM ---
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_experimental_option("prefs", {"download.default_directory": base_path})

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 25)

try:
    print("--- PASO: DESCARGA FUDO ---")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()

    print(f"Filtrando: {fecha_inicio} a {fecha_fin}")
    select_tipo = wait.until(EC.presence_of_element_located((By.XPATH, "//select[@ng-model='type']")))
    Select(select_tipo).select_by_value("string:r")
    
    wait.until(EC.presence_of_element_located((By.XPATH, "//input[@ng-model='model.t1']"))).send_keys(fecha_inicio)
    driver.find_element(By.XPATH, "//input[@ng-model='model.t2']").send_keys(fecha_fin)
    time.sleep(3)

    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']"))).click()
    
    # Esperar el archivo ZIP
    for _ in range(20):
        zips = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if zips: break
        time.sleep(1)
    
    if not zips: raise Exception("No se descargó el ZIP")

    # Extraer
    zip_path = os.path.join(base_path, zips[0])
    with zipfile.ZipFile(zip_path, 'r') as z:
        archivo_interno = z.namelist()[0]
        z.extract(archivo_interno, base_path)
        shutil.move(os.path.join(base_path, archivo_interno), ruta_excel)
    
    print(f"✅ Archivo listo en: {ruta_excel}")

    # --- PASO: PROCESAR CON PANDAS ---
    print("--- PASO: PROCESAMIENTO PANDAS ---")
    # Fudo a veces exporta .xls que son en realidad HTML. xlrd suele fallar, usa engine='openpyxl' si es .xlsx
    # Pero para los .xls de Fudo, a veces hay que usar pd.read_html o simplemente read_excel
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    # (Lógica de consolidación igual a la anterior...)
    df_v.columns = df_v.columns.str.strip()
    df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Turno'] = df_v['Fecha_DT'].dt.hour.apply(lambda h: "Mañana" if h < 16 else "Noche")

    prod = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    desc = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    env = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()

    consolidado = df_v[['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']].merge(prod, on='Id', how='left')
    consolidado = consolidado.merge(desc, left_on='Id', right_on='Id', how='left').merge(env, left_on='Id', right_on='Id', how='left')
    
    # IMPORTANTE: Llamar a la función de subida
    subir_a_google(consolidado)

except Exception as e:
    print(f"❌ ERROR: {e}")
finally:
    driver.quit()
