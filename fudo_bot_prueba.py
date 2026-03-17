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

def limpiar_a_entero_string(serie):
    """Convierte a número, redondea y devuelve un string puro sin .0"""
    # Reemplaza coma por punto, convierte a número, rellena vacíos con 0
    temp = pd.to_numeric(serie.astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    # Redondea al entero más cercano y convierte a string
    return temp.round(0).astype(int).astype(str)

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
        
        # Convertimos todo el DataFrame a string antes de subir
        # Esto es el 'candado' para que no aparezcan .0 en Google Sheets
        datos_finales = [consolidado.columns.values.tolist()] + \
                         consolidado.fillna("").astype(str).values.tolist()
        
        sheet_data.update(range_name='A1', values=datos_finales)
        print("🚀 ¡DATOS SIN DECIMALES ACTUALIZADOS EN HOJA 1!")
        
    except Exception as e:
        print(f"❌ ERROR EN GOOGLE SHEETS: {e}")

# --- 2. SELENIUM: DESCARGA DIRECTA ---
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
    
    # Login
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()

    time.sleep(10) # Esperar que cargue la tabla por defecto

    export_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    driver.execute_script("arguments[0].click();", export_btn)

    # Esperar ZIP
    found_zip = False
    for _ in range(30):
        zips = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if zips:
            found_zip = True
            break
        time.sleep(1)
    
    if not found_zip: raise Exception("No se descargó el ZIP")

    # Extraer
    zip_path = os.path.join(base_path, zips[0])
    with zipfile.ZipFile(zip_path, 'r') as z:
        archivo_interno = z.namelist()[0]
        z.extract(archivo_interno, base_path)
        if os.path.exists(ruta_excel): os.remove(ruta_excel)
        shutil.move(os.path.join(base_path, archivo_interno), ruta_excel)

    # --- 3. PROCESAMIENTO PANDAS ---
    print("--- PASO: PROCESAMIENTO Y LIMPIEZA TOTAL ---")
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # Fechas y Turnos (Detección automática de formato)
    if pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = df_v['Creación']
    else:
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Turno'] = df_v['Fecha_DT'].dt.hour.apply(lambda h: "Mañana" if h < 16 else "Noche")

    # Cargar Adicionales (Productos, Descuentos, Envíos)
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    # Agrupar Productos por Id
    prod = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    prod.columns = ['Id', 'Detalle_Productos']

    # Consolidar todo el reporte
    # Usamos Id como clave de unión
    consolidado = df_v[['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Costo_Total_Venta', 'Origen', 'Medio de Pago']].copy()
    consolidado = consolidado.merge(prod, on='Id', how='left')
    
    # Sumar Descuentos y Envíos por Id
    desc = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    env = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()
    
    consolidado = consolidado.merge(desc, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1)
    consolidado = consolidado.merge(env, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1)
    
    consolidado.rename(columns={'Valor_x': 'Descuento', 'Valor_y': 'Envio'}, inplace=True)
    consolidado = consolidado.fillna(0)

    # --- CÁLCULO DE MARGEN Y LIMPIEZA DE DECIMALES ---
    def a_num(s): return pd.to_numeric(s.astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    
    # Calculamos Margen antes de pasar a string
    venta = a_num(consolidado['Total'])
    costo = a_num(consolidado['Costo_Total_Venta'])
    descuento = a_num(consolidado['Descuento'])
    consolidado['Margen_Neto'] = (venta - costo - descuento).round(0).astype(int)

    # Convertimos todas las columnas monetarias a ENTERO y luego a STRING (Adiós .0)
    cols_dinero = ['Total', 'Costo_Total_Venta', 'Descuento', 'Envio', 'Margen_Neto']
    for col in cols_dinero:
        consolidado[col] = limpiar_a_entero_string(consolidado[col])

    # Re-ordenar columnas para que Detalle_Productos se vea bien
    orden = ['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Detalle_Productos', 'Total', 'Costo_Total_Venta', 'Descuento', 'Envio', 'Margen_Neto', 'Origen', 'Medio de Pago']
    consolidado = consolidado[orden]

    # Subir a Google Sheets
    subir_a_google(consolidado)

except Exception as e:
    print(f"❌ ERROR: {e}")
finally:
    driver.quit()
    print("--- PROCESO TERMINADO ---")
