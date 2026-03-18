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
fecha_hoy_str = ahora.strftime("%d/%m/%Y")
ayer = ahora - timedelta(days=1)
manana = ahora + timedelta(days=1)
fecha_inicio = ayer.strftime("%Y-%m-%d")
fecha_fin = manana.strftime("%Y-%m-%d")

base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
ruta_excel = os.path.join(temp_excel_path, "ventas.xls")
os.makedirs(temp_excel_path, exist_ok=True)

def subir_a_google(consolidado):
    print("--- PASO: CONEXIÓN A GOOGLE SHEETS ---")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope) if creds_json else Credentials.from_service_account_file('credentials.json', scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        spreadsheet = client.open("Analisis Fudo")
        sheet_data = spreadsheet.worksheet("Hoja 1")
        
        # LIMPIEZA TOTAL: Asegura que no quede nada previo
        print("🧹 Limpiando Hoja 1 por completo...")
        sheet_data.batch_clear(['A1:Z5000']) 
        
        if not consolidado.empty:
            print(f"📝 Pegando {len(consolidado)} filas de hoy ({fecha_hoy_str})...")
            datos_finales = [consolidado.columns.values.tolist()] + \
                             consolidado.fillna("").astype(str).values.tolist()
            sheet_data.update(range_name='A1', values=datos_finales)
            print("🚀 ¡DATOS ACTUALIZADOS!")
        else:
            print("⚠️ No hay datos para subir hoy.")
            
    except Exception as e:
        print(f"❌ ERROR EN GOOGLE SHEETS: {e}")

# --- 2. SELENIUM ---
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_experimental_option("prefs", {"download.default_directory": base_path, "download.prompt_for_download": False})
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 30)

try:
    print("--- PASO: DESCARGA FUDO ---")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()
    time.sleep(7) 

    select_tipo = wait.until(EC.presence_of_element_located((By.XPATH, "//select[@ng-model='type']")))
    Select(select_tipo).select_by_value("string:r")
    time.sleep(2)

    input_desde = driver.find_element(By.XPATH, "//input[@ng-model='model.t1']")
    input_hasta = driver.find_element(By.XPATH, "//input[@ng-model='model.t2']")
    driver.execute_script("arguments[0].value = arguments[1];", input_desde, fecha_inicio)
    driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", input_desde)
    driver.execute_script("arguments[0].value = arguments[1];", input_hasta, fecha_fin)
    driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", input_hasta)
    time.sleep(3)

    export_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    driver.execute_script("arguments[0].click();", export_btn)

    found_zip = False
    for _ in range(30):
        zips = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if zips:
            found_zip = True
            break
        time.sleep(1)
    
    if not found_zip: raise Exception("El ZIP no descargó.")
    zip_path = os.path.join(base_path, zips[0])
    with zipfile.ZipFile(zip_path, 'r') as z:
        archivo_interno = z.namelist()[0]
        z.extract(archivo_interno, base_path)
        if os.path.exists(ruta_excel): os.remove(ruta_excel)
        shutil.move(os.path.join(base_path, archivo_interno), ruta_excel)

    # --- 3. PANDAS: LIMPIEZA NIVEL DIOS ---
    print("--- PASO: PROCESAMIENTO PANDAS ---")
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # Procesar Fecha_DT
    df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    
    # Generar Fecha_Texto y LIMPIAR CUALQUIER COSA QUE NO SEA NÚMERO O BARRA
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y').astype(str)
    
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Turno'] = df_v['Fecha_DT'].dt.hour.apply(lambda h: "Mañana" if h < 16 else "Noche")

    # Joins con otras hojas
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')
    prod = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    desc = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    env = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()

    cols = ['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']
    consolidado = df_v[cols].merge(prod, on='Id', how='left')
    consolidado = consolidado.merge(desc, left_on='Id', right_on='Id', how='left')
    consolidado = consolidado.merge(env, left_on='Id', right_on='Id', how='left')
    consolidado.rename(columns={'Producto': 'Detalle_Productos', 'Valor_x': 'Descuento', 'Valor_y': 'Envio'}, inplace=True)

    # --- 4. FILTRO FINAL DINÁMICO ---
    # Convertimos a string y quitamos el apóstrofe explícitamente antes de comparar
    consolidado['Fecha_Texto'] = consolidado['Fecha_Texto'].astype(str).str.replace("'", "", regex=False).str.strip()
    
    # Filtro: debe contener la fecha de hoy
    consolidado_hoy = consolidado[consolidado['Fecha_Texto'].str.contains(fecha_hoy_str, na=False)].copy()

    print(f"Buscando hoy: {fecha_hoy_str}")
    if not consolidado.empty:
        print(f"Muestra de datos en Excel: {consolidado['Fecha_Texto'].unique()[:3]}")

    subir_a_google(consolidado_hoy)

except Exception as e:
    print(f"❌ ERROR: {e}")
finally:
    driver.quit()
    # Limpieza de temporales para que no se mezclen en la próxima corrida
    if os.path.exists(base_path): shutil.rmtree(base_path)
    print("--- PROCESO TERMINADO ---")
