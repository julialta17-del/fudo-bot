import os
import time
import zipfile
import shutil
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURACIÓN DE RUTAS (Linux/GitHub Compatible) ---
BASE_PATH = os.getcwd()
DOWNLOAD_PATH = os.path.join(BASE_PATH, "descargas")
TEMP_EXCEL_PATH = os.path.join(DOWNLOAD_PATH, "temp_excel")
NOMBRE_FINAL = "ventas.xls"
RUTA_EXCEL_FINAL = os.path.join(TEMP_EXCEL_PATH, NOMBRE_FINAL)

os.makedirs(DOWNLOAD_PATH, exist_ok=True)
os.makedirs(TEMP_EXCEL_PATH, exist_ok=True)

def descargar_desde_fudo():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Crucial para GitHub Actions
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    prefs = {
        "download.default_directory": DOWNLOAD_PATH,
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)

    try:
        print("Iniciando sesión en Fudo...")
        driver.get("https://app-v2.fu.do/app/#!/sales")
        
        # Uso de variables de entorno de GitHub Secrets
        user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
        pass_input = driver.find_element(By.ID, "password")
        
        user_input.send_keys(os.getenv("FUDO_USER"))
        pass_input.send_keys(os.getenv("FUDO_PASS"))
        pass_input.submit()
        
        print("Exportando archivo...")
        exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
        exportar_btn.click()
        
        # Espera dinámica al archivo ZIP
        timeout = 60
        seconds = 0
        while not any(f.endswith(".zip") for f in os.listdir(DOWNLOAD_PATH)) and seconds < timeout:
            time.sleep(1)
            seconds += 1

        archivos_zip = [os.path.join(DOWNLOAD_PATH, f) for f in os.listdir(DOWNLOAD_PATH) if f.lower().endswith(".zip")]
        if not archivos_zip:
            raise Exception("No se descargó el ZIP a tiempo.")

        zip_file = max(archivos_zip, key=os.path.getctime)
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            archivo_interno = zip_ref.namelist()[0]
            zip_ref.extract(archivo_interno, DOWNLOAD_PATH)
            
            ruta_extraida = os.path.join(DOWNLOAD_PATH, archivo_interno)
            if os.path.exists(RUTA_EXCEL_FINAL): os.remove(RUTA_EXCEL_FINAL)
            shutil.move(ruta_extraida, RUTA_EXCEL_FINAL)
        
        os.remove(zip_file)
        print("Descarga y extracción exitosa.")
        
    finally:
        driver.quit()

def procesar_y_subir():
    print("Iniciando procesamiento de datos...")
    # 1. CARGAR DATOS
    # Nota: xlrd es necesario para archivos .xls antiguos
    df_v = pd.read_excel(RUTA_EXCEL_FINAL, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # PROCESAMIENTO DE FECHA
    df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Hora_Int'] = df_v['Fecha_DT'].dt.hour

    def asignar_turno(h):
        if h < 15: return "Mañana"
        elif h >= 19: return "Noche"
        return "Tarde/Intermedio"

    df_v['Turno'] = df_v['Hora_Int'].apply(asignar_turno)

    # Cargar hojas secundarias
    df_p = pd.read_excel(RUTA_EXCEL_FINAL, sheet_name='Pagos')
    df_a = pd.read_excel(RUTA_EXCEL_FINAL, sheet_name='Adiciones')
    df_d = pd.read_excel(RUTA_EXCEL_FINAL, sheet_name='Descuentos')
    df_e = pd.read_excel(RUTA_EXCEL_FINAL, sheet_name='Costos de Envío')

    # A. Resúmenes
    prod_resumen = df_a.groupby('Id. Venta').agg({'Producto': lambda x: ', '.join(x.astype(str)), 'Precio': 'sum'}).reset_index().rename(columns={'Id. Venta': 'Id', 'Producto': 'Detalle_Productos', 'Precio': 'Total_Productos_Bruto'})
    desc_resumen = df_d.groupby('Id. Venta')['Valor'].sum().reset_index().rename(columns={'Id. Venta': 'Id', 'Valor': 'Descuento_Total'})
    envio_resumen = df_e.groupby('Id. Venta')['Valor'].sum().reset_index().rename(columns={'Id. Venta': 'Id', 'Valor': 'Costo_Envio'})

    # B. Consolidado
    columnas_interes = ['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']
    consolidado = df_v[columnas_interes].merge(prod_resumen, on='Id', how='left')
    consolidado = consolidado.merge(desc_resumen, on='Id', how='left').merge(envio_resumen, on='Id', how='left')
    consolidado[['Total_Productos_Bruto', 'Descuento_Total', 'Costo_Envio']] = consolidado[['Total_Productos_Bruto', 'Descuento_Total', 'Costo_Envio']].fillna(0)

    # C. Métricas
    ventas_turno = consolidado.groupby('Turno').agg({'Id': 'count', 'Total': 'sum'}).reset_index()
    top_5 = df_a['Producto'].value_counts().head(5).reset_index()
    pagos_resumen = df_p.groupby('Medio de Pago')['Monto'].sum().reset_index().sort_values(by='Monto', ascending=False)

    ticket_prom = consolidado['Total'].mean()
    turno_fuerte = ventas_turno.sort_values('Total', ascending=False).iloc[0]['Turno'] if not ventas_turno.empty else "N/A"

    consejos = [
        ["CONSEJOS ESTRATÉGICOS"],
        [f"1. El turno fuerte es: {turno_fuerte}."],
        [f"2. Ticket promedio: ${ticket_prom:.2f}."]
    ]

    # --- SUBIDA A GOOGLE ---
    print("Conectando con Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    spreadsheet = client.open("Analisis Fudo")
    
    # Hoja Datos
    sheet_data = spreadsheet.get_worksheet(0)
    sheet_data.clear()
    sheet_data.update('A1', [consolidado.columns.values.tolist()] + consolidado.fillna("").astype(str).values.tolist())

    # Hoja Resumen
    try: sheet_res = spreadsheet.worksheet("Resumen")
    except: sheet_res = spreadsheet.add_worksheet(title="Resumen", rows="100", cols="20")
    
    sheet_res.clear()
    sheet_res.update('A1', [["TOP 5 PRODUCTOS"]])
    sheet_res.update('A2', [top_5.columns.values.tolist()] + top_5.values.tolist())
    sheet_res.update('E1', [["VENTAS POR TURNO"]])
    sheet_res.update('E2', [ventas_turno.columns.values.tolist()] + ventas_turno.values.tolist())
    sheet_res.update('I1', [["PAGOS POR MEDIO"]])
    sheet_res.update('I2', [pagos_resumen.columns.values.tolist()] + pagos_resumen.values.tolist())
    sheet_res.update('A12', consejos)
    print("¡Proceso finalizado exitosamente!")

if __name__ == "__main__":
    descargar_desde_fudo()
    procesar_y_analizar = procesar_y_subir()
