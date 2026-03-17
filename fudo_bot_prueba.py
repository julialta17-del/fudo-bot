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
    """
    Convierte cualquier valor (con comas o puntos) a número entero.
    Si el valor es 1250,50 lo transforma en 1251.
    """
    # Reemplaza coma por punto para que Pandas lo reconozca como decimal, luego redondea y convierte a entero
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
        # IMPORTANTE: Verifica que el nombre del archivo sea el correcto
        spreadsheet = client.open("Quinta Analisis Fudo")
        sheet_data = spreadsheet.worksheet("Hoja 1")
        
        print("🧹 Limpiando Hoja 1...")
        sheet_data.clear()
        
        # Convertimos a string para la subida final para evitar errores de formato en la API
        datos_finales = [consolidado.columns.values.tolist()] + \
                         consolidado.fillna("").astype(str).values.tolist()
        
        sheet_data.update(range_name='A1', values=datos_finales)
        print("🚀 ¡DATOS SIN DECIMALES PEGADOS CON ÉXITO!")
        
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
    print("--- PASO: DESCARGA FUDO (SIN FILTROS) ---")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    
    # Login
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()

    # Esperamos a que el botón de exportar esté disponible
    print("Esperando botón de exportar...")
    time.sleep(10) # Tiempo para que cargue la lista por defecto

    export_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    driver.execute_script("arguments[0].click();", export_btn)

    # Esperar la descarga del ZIP
    found_zip = False
    for _ in range(30):
        zips = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if zips:
            found_zip = True
            break
        time.sleep(1)
    
    if not found_zip: raise Exception("No se encontró el archivo descargado.")

    # Extraer archivo
    zip_path = os.path.join(base_path, zips[0])
    with zipfile.ZipFile(zip_path, 'r') as z:
        archivo_interno = z.namelist()[0]
        z.extract(archivo_interno, base_path)
        if os.path.exists(ruta_excel): os.remove(ruta_excel)
        shutil.move(os.path.join(base_path, archivo_interno), ruta_excel)

    # --- 3. PROCESAMIENTO PANDAS ---
    print("--- PASO: PROCESAMIENTO Y ELIMINACIÓN DE DECIMALES ---")
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # Aplicar limpieza a ENTEROS en las columnas de dinero
    columnas_dinero = ['Total', 'Costo Total']
    for col in columnas_dinero:
        if col in df_v.columns:
            df_v[col] = limpiar_a_entero(df_v[col])
    
    # Procesar fechas básicas
    df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Turno'] = df_v['Fecha_DT'].dt.hour.apply(lambda h: "Mañana" if h < 16 else "Noche")

    # Adicionales (Descuentos y Envíos)
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    # Sumar y limpiar descuentos/envíos
    df_d['Valor'] = limpiar_a_entero(df_d['Valor'])
    desc = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()

    df_e['Valor'] = limpiar_a_entero(df_e['Valor'])
    env = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()

    # Consolidar
    cols_interes = ['Id', 'Fecha_Texto', 'Turno', 'Cliente', 'Total', 'Costo Total', 'Origen', 'Medio de Pago']
    consolidado = df_v[cols_interes].merge(desc, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1, errors='ignore')
    consolidado = consolidado.merge(env, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1, errors='ignore')
    
    consolidado.rename(columns={'Valor_x': 'Descuento', 'Valor_y': 'Envio'}, inplace=True)
    consolidado = consolidado.fillna(0)

    # Calcular Margen Neto (Venta - Costo - Descuento) sin decimales
    consolidado['Margen_Neto'] = consolidado['Total'] - consolidado['Costo Total'] - consolidado['Descuento']

    # Subir todo lo procesado
    subir_a_google(consolidado)

except Exception as e:
    print(f"❌ ERROR: {e}")
finally:
    driver.quit()
