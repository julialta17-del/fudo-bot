import os
import glob
import time
import zipfile
import shutil
import pandas as pd
import gspread
import json
import pytz
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# -------------------------------------------------------
# FECHAS AUTOMÁTICAS EN ZONA ARGENTINA
# -------------------------------------------------------
tz_arg = pytz.timezone("America/Argentina/Buenos_Aires")
ahora_arg = datetime.now(tz_arg)
fecha_desde = ahora_arg.strftime("%Y-%m-%d")
fecha_hoy_texto = ahora_arg.strftime("%d/%m/%Y")

if ahora_arg.hour >= 21:
    fecha_hasta = (ahora_arg + timedelta(days=1)).strftime("%Y-%m-%d")
    hora_hasta = "03:00"
    print(f"Modo NOCHE: {fecha_desde} 00:00 → {fecha_hasta} {hora_hasta}")
else:
    fecha_hasta = fecha_desde
    hora_hasta = "23:59"
    print(f"Modo DÍA: {fecha_desde} 00:00 → {fecha_hasta} {hora_hasta}")

print(f"Hora actual Argentina: {ahora_arg.strftime('%d/%m/%Y %H:%M')}")

# -------------------------------------------------------
# RUTAS
# -------------------------------------------------------
base_path = os.path.abspath(os.path.join(os.getcwd(), "descargas"))
temp_excel_path = os.path.join(base_path, "temp_excel")
nombre_final = "ventas.xls"
ruta_excel_final = os.path.join(temp_excel_path, nombre_final)
os.makedirs(base_path, exist_ok=True)
os.makedirs(temp_excel_path, exist_ok=True)
print(f"Ruta de descarga: {base_path}")

# -------------------------------------------------------
# CHROME HEADLESS
# -------------------------------------------------------
chrome_options = Options()
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": base_path,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})


def esperar_descarga(carpeta, timeout=60):
    """Espera en dos pasos: primero que inicie, luego que termine"""

    # Paso 1: esperar que aparezca el .crdownload (Chrome inició la descarga)
    print("Esperando que inicie la descarga...")
    fin = time.time() + 20
    while time.time() < fin:
        archivos = os.listdir(carpeta)
        en_curso = [f for f in archivos if f.endswith(".crdownload")]
        zips = [f for f in archivos if f.lower().endswith(".zip")]
        if en_curso:
            print(f"Descarga iniciada: {en_curso[0]}")
            break
        if zips:
            # A veces es tan rápido que ya terminó
            print(f"Descarga ya completa: {zips[0]}")
            return True
        time.sleep(1)

    # Paso 2: esperar que el .crdownload desaparezca y quede el .zip
    print("Esperando que termine la descarga...")
    fin = time.time() + timeout
    while time.time() < fin:
        archivos = os.listdir(carpeta)
        print(f"  Archivos: {archivos}")
        zips = [f for f in archivos if f.lower().endswith(".zip")]
        en_curso = [f for f in archivos if f.endswith(".crdownload")]
        if zips and not en_curso:
            print(f"✅ Descarga completa: {zips[0]}")
            return True
        time.sleep(2)

    return False


def buscar_zip_en_sistema():
    """Fallback: busca ZIPs en otras rutas del sistema"""
    rutas_posibles = [
        os.path.expanduser("~"),
        os.path.expanduser("~/Downloads"),
        "/tmp",
        "/root",
        "/home/runner",
        os.getcwd(),
    ]
    print("Buscando ZIPs en otras rutas del sistema...")
    for ruta in rutas_posibles:
        if os.path.exists(ruta):
            try:
                zips = glob.glob(os.path.join(ruta, "*.zip"))
                if zips:
                    print(f"  ✅ ZIP encontrado en {ruta}: {zips}")
                    return zips[0]
                archivos = os.listdir(ruta)
                if archivos:
                    print(f"  {ruta}: {archivos}")
            except Exception as ex:
                print(f"  No se pudo leer {ruta}: {ex}")
    return None


def ejecutar_todo():
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": base_path
    })

    wait = WebDriverWait(driver, 60)  # 60 segundos de timeout

    try:
        # -------------------------------------------------------
        # PARTE 1: LOGIN
        # -------------------------------------------------------
        print("Iniciando sesión en Fudo...")
        driver.get("https://app-v2.fu.do/app/#!/sales")
        wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys(os.environ["FUDO_USER"])
        driver.find_element(By.ID, "password").send_keys(os.environ["FUDO_PASS"])
        driver.find_element(By.ID, "password").submit()
        print("Login enviado, esperando redirección...")

        # Esperar que desaparezca el formulario de login
        wait.until(EC.invisibility_of_element_located((By.ID, "user")))
        print(f"Login OK. Página actual: {driver.current_url}")
        driver.save_screenshot("post_login.png")

        # Forzar navegación a ventas y esperar que cargue Angular
        driver.get("https://app-v2.fu.do/app/#!/sales")
        time.sleep(3)

        # -------------------------------------------------------
        # PARTE 2: FILTRO RANGO CON FECHAS AUTOMÁTICAS
        # -------------------------------------------------------
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'select[ng-model="type"]')))
        time.sleep(2)

        print("Configurando filtro tipo Rango...")
        driver.execute_script("""
            var select = document.querySelector('select[ng-model="type"]');
            var scope = angular.element(select).scope();
            scope.$apply(function() {
                scope.type = 'r';
                scope.refreshType();
            });
        """)
        time.sleep(1)

        print(f"Seteando rango: {fecha_desde} 00:00 → {fecha_hasta} {hora_hasta}")
        driver.execute_script("""
            var input = document.querySelector('input[ng-model="model.t1"]');
            var scope = angular.element(input).scope();
            scope.$apply(function() {
                scope.model.t1 = arguments[0];
                scope.model.t2 = arguments[1];
                scope.t1 = '00:00';
                scope.t2 = arguments[2];
                scope.refreshDate();
            });
        """, fecha_desde, fecha_hasta, hora_hasta)
        time.sleep(3)

        # -------------------------------------------------------
        # PARTE 3: EXPORTAR
        # -------------------------------------------------------
        print("Solicitando exportación...")
        exportar_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")
        ))

        # Cerrar Userpilot si existe
        try:
            driver.execute_script("""
                var iframe = document.getElementById('userpilotIframeContainer');
                if (iframe) iframe.remove();
            """)
            time.sleep(1)
            print("Modal de Userpilot cerrado.")
        except Exception:
            pass

        driver.save_screenshot("antes_click.png")

        # Click normal primero, JS como fallback
        try:
            exportar_btn.click()
            print("Click normal ejecutado.")
        except Exception:
            driver.execute_script("arguments[0].click();", exportar_btn)
            print("Click JS ejecutado.")

        # Darle tiempo a Chrome para iniciar la descarga
        time.sleep(2)
        driver.save_screenshot("despues_click.png")

        # -------------------------------------------------------
        # PARTE 4: ESPERAR Y LOCALIZAR ZIP
        # -------------------------------------------------------
        descarga_ok = esperar_descarga(base_path, timeout=60)

        if not descarga_ok:
            zip_encontrado = buscar_zip_en_sistema()
            if zip_encontrado:
                print(f"ZIP encontrado fuera de la carpeta: {zip_encontrado}")
                shutil.move(zip_encontrado, os.path.join(base_path, os.path.basename(zip_encontrado)))
            else:
                raise Exception("No se encontró ningún ZIP en el sistema")

        archivos_zip = [
            os.path.join(base_path, f)
            for f in os.listdir(base_path)
            if f.lower().endswith(".zip")
        ]
        zip_file = max(archivos_zip, key=os.path.getmtime)
        print(f"Extrayendo: {zip_file}")

        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            nombres = zip_ref.namelist()
            if not nombres:
                raise Exception("El ZIP está vacío")
            archivo_interno = nombres[0]
            zip_ref.extract(archivo_interno, base_path)
            ruta_extraida = os.path.join(base_path, archivo_interno)
            if os.path.exists(ruta_excel_final):
                os.remove(ruta_excel_final)
            shutil.move(ruta_extraida, ruta_excel_final)
            print(f"✅ Archivo listo en: {ruta_excel_final}")

        os.remove(zip_file)

        # -------------------------------------------------------
        # PARTE 5: PROCESAMIENTO CON PANDAS
        # -------------------------------------------------------
        print("Procesando datos con Pandas...")
        df_v = pd.read_excel(ruta_excel_final, sheet_name='Ventas', skiprows=3)
        df_a = pd.read_excel(ruta_excel_final, sheet_name='Adiciones')
        df_d = pd.read_excel(ruta_excel_final, sheet_name='Descuentos')
        df_e = pd.read_excel(ruta_excel_final, sheet_name='Costos de Envío')

        df_v.columns = df_v.columns.str.strip()

        if not pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
            df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
        else:
            df_v['Fecha_DT'] = df_v['Creación']

        df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
        df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
        df_v['Hora_Int'] = df_v['Fecha_DT'].dt.hour
        df_v['Turno'] = df_v['Hora_Int'].apply(lambda h: "Mañana" if h < 16 else "Noche")

        prod_resumen = df_a.groupby('Id. Venta')['Producto'].apply(
            lambda x: ', '.join(x.astype(str))
        ).reset_index()
        prod_resumen.columns = ['Id', 'Detalle_Productos']

        desc_resumen = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
        desc_resumen.columns = ['Id', 'Descuento_Total']

        envio_resumen = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()
        envio_resumen.columns = ['Id', 'Costo_Envio']

        columnas_interes = ['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']
        consolidado = df_v[columnas_interes].merge(prod_resumen, on='Id', how='left')
        consolidado = consolidado.merge(desc_resumen, on='Id', how='left')
        consolidado = consolidado.merge(envio_resumen, on='Id', how='left')
        consolidado[['Descuento_Total', 'Costo_Envio']] = consolidado[['Descuento_Total', 'Costo_Envio']].fillna(0)
        consolidado['Detalle_Productos'] = consolidado['Detalle_Productos'].fillna("Sin detalle")

        print(f"Filtrando datos de HOY: {fecha_hoy_texto}")
        consolidado = consolidado[consolidado['Fecha_Texto'] == fecha_hoy_texto].copy()

        if consolidado.empty:
            print(f"⚠️ No se encontraron ventas para hoy {fecha_hoy_texto}. Fin del proceso.")
            return

        # -------------------------------------------------------
        # PARTE 6: SUBIR A GOOGLE SHEETS
        # -------------------------------------------------------
        print("Subiendo a Google Sheets...")
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_json = os.environ.get("GOOGLE_CREDENTIALS")
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

        print(f"🚀 ÉXITO: {len(consolidado)} ventas de HOY subidas a Hoja 1.")

    except Exception as e:
        print(f"Error crítico: {e}")
        raise

    finally:
        driver.quit()
        print("Proceso terminado.")
        if os.path.exists(base_path):
            shutil.rmtree(base_path)


if __name__ == "__main__":
    ejecutar_todo()
