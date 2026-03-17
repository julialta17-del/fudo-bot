import os
import time
import zipfile
import shutil
import json
import pandas as pd
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURACIÓN DE RUTAS ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
ruta_excel = os.path.join(temp_excel_path, "ventas.xls")

os.makedirs(temp_excel_path, exist_ok=True)

def limpiar_a_entero(serie):
    """Convierte montos (con comas o puntos) a entero redondeado"""
    return pd.to_numeric(serie.astype(str).str.replace(',', '.'), errors='coerce').fillna(0).round(0).astype(int)

def subir_a_google(consolidado):
    print("--- PASO: CONEXIÓN A GOOGLE SHEETS ---")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    
    try:
        spreadsheet = client.open("Analisis Fudo")
        sheet_data = spreadsheet.worksheet("Hoja 1")
        sheet_data.clear()
        
        datos_finales = [consolidado.columns.values.tolist()] + \
                         consolidado.fillna("").astype(str).values.tolist()
        
        sheet_data.update(range_name='A1', values=datos_finales)
        print("🚀 ¡DATOS ACTUALIZADOS EN GOOGLE SHEETS SIN DECIMALES!")
        
    except Exception as e:
        print(f"❌ ERROR EN GOOGLE SHEETS: {e}")

# --- SELENIUM: DESCARGA ---
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_experimental_option("prefs", {"download.default_directory": base_path})

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 30)

try:
    print("--- PASO: DESCARGA FUDO ---")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()

    time.sleep(10) 

    export_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    driver.execute_script("arguments[0].click();", export_btn)

    zip_found = False
    for _ in range(30):
        zips = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if zips:
            zip_found = True
            break
        time.sleep(1)
    
    if not zip_found: raise Exception("No se descargó el archivo ZIP de Fudo")

    zip_path = os.path.join(base_path, zips[0])
    with zipfile.ZipFile(zip_path, 'r') as z:
        archivo_interno = z.namelist()[0]
        z.extract(archivo_interno, base_path)
        if os.path.exists(ruta_excel): os.remove(ruta_excel)
        shutil.move(os.path.join(base_path, archivo_interno), ruta_excel)

    # --- PROCESAMIENTO PANDAS ---
    print("--- PASO: PROCESAMIENTO Y ELIMINACIÓN DE DECIMALES ---")
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip() # Limpia espacios en los nombres de columnas
    
    # Manejo de Fecha
    if pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = df_v['Creación']
    else:
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Turno'] = df_v['Fecha_DT'].dt.hour.apply(lambda h: "Mañana" if h < 16 else "Noche")

    # Limpieza de importes a ENTEROS
    df_v['Total'] = limpiar_a_entero(df_v['Total'])
    
    # Columna específica: Costo_Total_Venta
    nombre_col_costo = 'Costo_Total_Venta'
    if nombre_col_costo in df_v.columns:
        df_v['Costo_Limpio'] = limpiar_a_entero(df_v[nombre_col_costo])
    else:
        print(f"⚠️ Advertencia: No se encontró '{nombre_col_costo}', se usará 0.")
        df_v['Costo_Limpio'] = 0

    # Adicionales
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    desc = df_d.groupby('Id. Venta')['Valor'].apply(limpiar_a_entero).groupby(df_d['Id. Venta']).sum().reset_index()
    env = df_e.groupby('Id. Venta')['Valor'].apply(limpiar_a_entero).groupby(df_e['Id. Venta']).sum().reset_index()

    # Consolidar reporte
    cols_base = ['Id', 'Fecha_Texto', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago', 'Costo_Limpio']
    consolidado = df_v[cols_base].copy()
    
    consolidado = consolidado.merge(desc, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1, errors='ignore')
    consolidado = consolidado.merge(env, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1, errors='ignore')
    
    consolidado.rename(columns={'Valor_x': 'Descuento', 'Valor_y': 'Envio'}, inplace=True)
    consolidado = consolidado.fillna(0)

    # Margen Neto: Total - Costo - Descuento (Todo en enteros)
    consolidado['Margen_Neto'] = consolidado['Total'] - consolidado['Costo_Limpio'] - consolidado['Descuento']

    # Subir a Google Sheets
    subir_a_google(consolidado)

except Exception as e:
    print(f"❌ ERROR: {e}")
finally:
    driver.quit()
