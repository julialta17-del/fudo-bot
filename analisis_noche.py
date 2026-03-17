import os
import time
import zipfile
import shutil
import json
import pandas as pd
import numpy as np
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

# --- 1. CONFIGURACIÓN DE FECHAS ---
ahora = datetime.now()
ayer = ahora - timedelta(days=1)
manana = ahora + timedelta(days=1)
fecha_inicio = ayer.strftime("%Y-%m-%d")
fecha_fin = manana.strftime("%Y-%m-%d")

# --- 2. CONFIGURACIÓN DE RUTAS ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
nombre_final = "ventas.xls"
ruta_excel = os.path.join(temp_excel_path, nombre_final)

os.makedirs(temp_excel_path, exist_ok=True)

# --- 3. FUNCIÓN DE PROCESAMIENTO Y SUBIDA A GOOGLE ---
def procesar_y_subir_a_google(ruta_archivo):
    print(f"📊 Procesando datos desde: {ruta_archivo}")
    
    # CARGAR DATOS (Ventas, Adiciones, Descuentos, Envíos)
    df_v = pd.read_excel(ruta_archivo, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # Procesamiento de fechas
    if not pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    else:
        df_v['Fecha_DT'] = df_v['Creación']
    
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Turno'] = df_v['Fecha_DT'].dt.hour.apply(lambda h: "Mañana" if h < 16 else "Noche")

    # Cargar Hojas Adicionales
    df_a = pd.read_excel(ruta_archivo, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_archivo, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_archivo, sheet_name='Costos de Envío')

    # Consolidar información extra
    prod_resumen = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    prod_resumen.columns = ['Id', 'Detalle_Productos']

    desc_resumen = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    desc_resumen.columns = ['Id', 'Descuento_Total']

    envio_resumen = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()
    envio_resumen.columns = ['Id', 'Costo_Envio']

    # UNIFICAR (Merge)
    columnas_interes = ['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']
    consolidado = df_v[columnas_interes].merge(prod_resumen, on='Id', how='left')
    consolidado = consolidado.merge(desc_resumen, on='Id', how='left')
    consolidado = consolidado.merge(envio_resumen, on='Id', how='left')

    consolidado[['Descuento_Total', 'Costo_Envio']] = consolidado[['Descuento_Total', 'Costo_Envio']].fillna(0)
    consolidado['Detalle_Productos'] = consolidado['Detalle_Productos'].fillna("Sin detalle")

    # CONEXIÓN A GOOGLE SHEETS
    print("☁️ Subiendo a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_data = spreadsheet.worksheet("Hoja 1")
    
    sheet_data.clear()
    datos_finales = [consolidado.columns.values.tolist()] + consolidado.fillna("").astype(str).values.tolist()
    sheet_data.update(range_name='A1', values=datos_finales)
    print("🚀 ¡Hoja 1 actualizada con éxito!")

# --- 4. SELENIUM: DESCARGA DESDE FUDO ---
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": base_path,
    "download.prompt_for_download": False
})

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 25)

try:
    print("🔑 Iniciando sesión en Fudo...")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()

    print(f"📅 Aplicando filtros: {fecha_inicio} a {fecha_fin}")
    select_tipo_elem = wait.until(EC.presence_of_element_located((By.XPATH, "//select[@ng-model='type']")))
    Select(select_tipo_elem).select_by_value("string:r")
    
    input_desde = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@ng-model='model.t1']")))
    input_hasta = driver.find_element(By.XPATH, "//input[@ng-model='model.t2']")
    
    input_desde.clear()
    input_desde.send_keys(fecha_inicio)
    input_hasta.clear()
    input_hasta.send_keys(fecha_fin)
    
    time.sleep(3) # Espera técnica para Angular

    print("📥 Descargando archivo...")
    exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    exportar_btn.click()

    # Esperar el ZIP
    zip_file_path = None
    for _ in range(30):
        zips = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if zips:
            zip_file_path = os.path.join(base_path, max(zips, key=lambda f: os.path.getctime(os.path.join(base_path, f))))
            break
        time.sleep(1)

    if not zip_file_path:
        raise Exception("No se encontró el archivo ZIP descargado.")

    # EXTRAER Y MOVER
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        archivo_interno = zip_ref.namelist()[0]
        zip_ref.extract(archivo_interno, base_path)
        
        ruta_extraida = os.path.join(base_path, archivo_interno)
        if os.path.exists(ruta_excel): os.remove(ruta_excel)
        shutil.move(ruta_extraida, ruta_excel)

    os.remove(zip_file_path) # Limpiar el ZIP
    
    # --- EJECUTAR PROCESAMIENTO ---
    procesar_y_subir_a_google(ruta_excel)

except Exception as e:
    print(f"❌ ERROR CRÍTICO: {e}")
    driver.save_screenshot("error_debug.png")
finally:
    driver.quit()
    print("🏁 Proceso terminado.")
