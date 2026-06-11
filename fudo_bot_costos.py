import os
import time
import zipfile
import shutil
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# --- CONFIGURACIÓN DE RUTAS ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel2")
nombre_final = "productos.xls"

os.makedirs(base_path, exist_ok=True)
os.makedirs(temp_excel_path, exist_ok=True)

# --- CONFIGURACIÓN CHROME ---
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

chrome_options.add_experimental_option("prefs", {
    "download.default_directory": base_path,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})


def preparar_fila(row):
    """Convierte una fila a tipos nativos de Python para que gspread
    envíe números reales en lugar de strings."""
    resultado = []
    for val in row:
        if pd.isna(val):
            resultado.append("")
        elif isinstance(val, (float, int)):
            resultado.append(round(float(val), 2))
        else:
            resultado.append(str(val))
    return resultado


def ejecutar_sincronizacion_costos():
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 25)

    try:
        # 1. LOGIN Y EXPORTAR DESDE FUDO
        print("Iniciando sesión en Fudo...")
        driver.get("https://app-v2.fu.do/app/") 
        user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
        pass_input = driver.find_element(By.ID, "password")

        user_input.send_keys("admin@bigsaladssexta")
        pass_input.send_keys("bigsexta")
        pass_input.submit()

        print("Esperando que cargue el menú principal...")
        # Esperamos a que aparezca el botón en el menú lateral usando su href
        btn_productos = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "a[href='#!/products']")
        ))
        
        print("Haciendo clic en la sección 'Productos'...")
        btn_productos.click()
        
        # Le damos unos segundos a Angular para que pinte la tabla en pantalla
        time.sleep(5) 

        print("Descargando archivo ZIP...")
        exportar_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "a[ert-download-file='downloadProducts()']")
        ))
        exportar_btn.click()

        time.sleep(15)

        # 2. PROCESAR EL ARCHIVO ZIP
        archivos_zip = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if not archivos_zip:
            raise Exception("No se encontró el archivo ZIP descargado.")

        zip_path = os.path.join(base_path, archivos_zip[0])
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            archivo_interno = zip_ref.namelist()[0]
            zip_ref.extract(archivo_interno, base_path)

            ruta_excel = os.path.join(temp_excel_path, nombre_final)
            if os.path.exists(ruta_excel):
                os.remove(ruta_excel)
            shutil.move(os.path.join(base_path, archivo_interno), ruta_excel)

        # 3. LÓGICA DE NEGOCIO CON PANDAS
        print("Procesando lógicas de costos y descuentos...")
        
        # Leemos el archivo en bruto sin asignar cabeceras
        df_raw = pd.read_excel(ruta_excel, header=None)
        
        # Búsqueda implacable de la fila de encabezados
        fila_cabecera = None
        for idx, row in df_raw.iterrows():
            valores = [str(v).strip().lower() for v in row.values]
            if 'nombre' in valores and 'precio' in valores and 'costo' in valores:
                fila_cabecera = idx
                break
                
        if fila_cabecera is None:
            print("❌ IMPRESIÓN DE DEPURACIÓN (Primeras 15 filas):")
            print(df_raw.head(15).to_string())
            raise Exception("Error crítico: No se encontró la fila con 'Nombre', 'Precio' y 'Costo'.")
            
        # Recargar el DataFrame usando la fila detectada exactamente
        df = pd.read_excel(ruta_excel, header=fila_cabecera)
        
        # Limpieza extrema de los nombres de las columnas
        df.columns = (df.columns
                      .astype(str)
                      .str.strip()
                      .str.replace('\n', '', regex=False)
                      .str.replace('\r', '', regex=False))
        
        print(f"✅ Columnas detectadas y limpias: {df.columns.tolist()}")
        
        # Filtrar las columnas necesarias
        df = df[['Nombre', 'Precio', 'Costo']].copy()

        # Procesamiento estricto como números nativos de Pandas
        df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0).round(2)
        df['Costo']  = pd.to_numeric(df['Costo'], errors='coerce').fillna(0).round(2)

        print("   Muestra de valores leídos:")
        print(df[['Nombre', 'Precio', 'Costo']].head(8).to_string(index=False))

        # Si el costo es 0, se estima como 35% del precio de venta
        sin_costo = df['Costo'] == 0
        df.loc[sin_costo, 'Costo'] = (df.loc[sin_costo, 'Precio'] * 0.35).round(2)
        df['Costo_Estimado'] = sin_costo  # True = estimado, False = dato real de Fudo

        # Margen estándar
        df['Margen_$'] = (df['Precio'] - df['Costo']).round(2)
        df['Margen_%'] = (
            (df['Margen_$'] / df['Precio'])
            .replace([float('inf'), -float('inf')], 0)
            .fillna(0)
            .round(4)
        )

        # Con descuento 30%
        df['Precio_con_30%_Desc'] = (df['Precio'] * 0.70).round(2)
        df['Margen_$_con_Desc']   = (df['Precio_con_30%_Desc'] - df['Costo']).round(2)
        df['Margen_%_con_Desc']   = (
            (df['Margen_$_con_Desc'] / df['Precio_con_30%_Desc'])
            .replace([float('inf'), -float('inf')], 0)
            .fillna(0)
            .round(4)
        )

        # 4. SUBIR A GOOGLE SHEETS
        print("Conectando con Google Sheets...")
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_json = os.getenv("GOOGLE_CREDENTIALS")

        if creds_json:
            creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
        else:
            creds = Credentials.from_service_account_file('credentials.json', scopes=scope)

        client = gspread.authorize(creds)

        spreadsheet = client.open("Analisis Fudo")
        sheet = spreadsheet.worksheet("Maestro_Costos")
        sheet.clear()

        headers = df.columns.values.tolist()
        filas = [preparar_fila(row) for _, row in df.iterrows()]
        datos_subir = [headers] + filas

        sheet.update(range_name='A1', values=datos_subir, value_input_option='RAW')

        print("✅ Proceso completado: Maestro_Costos actualizado.")
        print(f"   → Productos con costo real de Fudo:   {(~sin_costo).sum()}")
        print(f"   → Productos con costo estimado (35%): {sin_costo.sum()}")

    except Exception as e:
        print(f"❌ Error durante la ejecución: {e}")
        raise
    finally:
        driver.quit()
        if os.path.exists(base_path):
            shutil.rmtree(base_path)


if __name__ == "__main__":
    ejecutar_sincronizacion_costos()
