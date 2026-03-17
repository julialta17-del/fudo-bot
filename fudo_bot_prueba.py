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
    temp = pd.to_numeric(
        serie.astype(str).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)
    return temp.round(0).astype(int).astype(str)

def limpiar_a_decimal_string(serie, decimales=2):
    """Para columnas como porcentajes donde se quieren mantener decimales"""
    temp = pd.to_numeric(
        serie.astype(str).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)
    return temp.round(decimales).astype(str)

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

        # Red de seguridad: cualquier numérico que haya escapado se convierte a int string
        for col in consolidado.select_dtypes(include=['float64', 'float32', 'int64', 'int32']).columns:
            consolidado[col] = consolidado[col].fillna(0).round(0).astype(int).astype(str)

        datos_finales = [consolidado.columns.values.tolist()] + \
                         consolidado.fillna("").astype(str).values.tolist()

        sheet_data.update(range_name='A1', values=datos_finales)
        print("🚀 ¡DATOS SIN DECIMALES ACTUALIZADOS EN HOJA 1!")

    except Exception as e:
        print(f"❌ ERROR EN GOOGLE SHEETS: {e}")

# --- SELENIUM ---
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

    found_zip = False
    for _ in range(30):
        zips = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if zips:
            found_zip = True
            break
        time.sleep(1)

    if not found_zip: raise Exception("No se descargó el ZIP")

    zip_path = os.path.join(base_path, zips[0])
    with zipfile.ZipFile(zip_path, 'r') as z:
        archivo_interno = z.namelist()[0]
        z.extract(archivo_interno, base_path)
        if os.path.exists(ruta_excel): os.remove(ruta_excel)
        shutil.move(os.path.join(base_path, archivo_interno), ruta_excel)

    # --- PROCESAMIENTO ---
    print("--- PASO: PROCESAMIENTO Y LIMPIEZA TOTAL ---")
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()

    if pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = df_v['Creación']
    else:
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')

    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Turno'] = df_v['Fecha_DT'].dt.hour.apply(lambda h: "Mañana" if h < 16 else "Noche")

    # ✅ FILTRO: solo filas con fecha de hoy
    hoy = datetime.now().date()
    df_v = df_v[df_v['Fecha_DT'].dt.date == hoy]

    if df_v.empty:
        raise Exception(f"No hay ventas para el día de hoy ({hoy.strftime('%d/%m/%Y')})")

    print(f"✅ Filas de hoy ({hoy.strftime('%d/%m/%Y')}): {len(df_v)}")

    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    prod = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    prod.columns = ['Id', 'Detalle_Productos']

    consolidado = df_v[['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Costo_Total_Venta', 'Origen', 'Medio de Pago']].copy()
    consolidado = consolidado.merge(prod, on='Id', how='left')

    desc = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    env = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()

    consolidado = consolidado.merge(desc, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1)
    consolidado = consolidado.merge(env, left_on='Id', right_on='Id. Venta', how='left').drop('Id. Venta', axis=1)

    consolidado.rename(columns={'Valor_x': 'Descuento', 'Valor_y': 'Envio'}, inplace=True)
    consolidado = consolidado.fillna(0)

    def a_num(s):
        return pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce').fillna(0)

    venta     = a_num(consolidado['Total'])
    costo     = a_num(consolidado['Costo_Total_Venta'])
    descuento = a_num(consolidado['Descuento'])

    consolidado['Margen_Neto']              = (venta - costo - descuento).round(0).astype(int)
    consolidado['Margen_Neto_$']            = consolidado['Margen_Neto']  # ajustá si tiene lógica distinta
    consolidado['Margen_Neto_%']            = ((consolidado['Margen_Neto'] / venta.replace(0, 1)) * 100).round(2)
    consolidado['Descuento_Total']          = descuento.round(0).astype(int)
    consolidado['Costo_Envio']              = a_num(consolidado['Envio']).round(0).astype(int)
    consolidado['Comision_PeYa_$']          = 0  # reemplazá con tu cálculo real
    consolidado['Comision_Tienda_Online_$'] = 0  # reemplazá con tu cálculo real

    # --- LIMPIEZA DE DECIMALES ---
    cols_enteras = [
        'Id',
        'Total',
        'Costo_Total_Venta',
        'Descuento',
        'Envio',
        'Margen_Neto',
        'Margen_Neto_$',
        'Descuento_Total',
        'Costo_Envio',
        'Comision_PeYa_$',
        'Comision_Tienda_Online_$',
    ]
    for col in cols_enteras:
        if col in consolidado.columns:
            consolidado[col] = limpiar_a_entero_string(consolidado[col])

    # Margen_Neto_% mantiene 2 decimales
    if 'Margen_Neto_%' in consolidado.columns:
        consolidado['Margen_Neto_%'] = limpiar_a_decimal_string(consolidado['Margen_Neto_%'], decimales=2)

    orden = [
        'Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Detalle_Productos',
        'Total', 'Costo_Total_Venta', 'Descuento', 'Descuento_Total', 'Envio', 'Costo_Envio',
        'Margen_Neto', 'Margen_Neto_$', 'Margen_Neto_%',
        'Comision_PeYa_$', 'Comision_Tienda_Online_$',
        'Origen', 'Medio de Pago'
    ]
    # Solo incluir columnas que realmente existan en el DataFrame
    orden = [c for c in orden if c in consolidado.columns]
    consolidado = consolidado[orden]

    subir_a_google(consolidado)

except Exception as e:
    print(f"❌ ERROR: {e}")
finally:
    driver.quit()
    print("--- PROCESO TERMINADO ---")
