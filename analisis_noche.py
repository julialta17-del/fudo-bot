import os
import time
import zipfile
import shutil
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- 1. CONFIGURACIÓN DE FECHAS (Ayer a Mañana) ---
# Si hoy es 17, buscará del 16 al 18
ahora = datetime.now()
ayer = ahora - timedelta(days=1)
manana = ahora + timedelta(days=1)

fecha_inicio = ayer.strftime("%Y-%m-%d")
fecha_fin = manana.strftime("%Y-%m-%d")

# --- 2. CONFIGURACIÓN DE RUTAS ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
nombre_final = "ventas.xls"

os.makedirs(temp_excel_path, exist_ok=True)

# --- 3. CONFIGURACIÓN DE CHROME ---
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

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 25)

try:
    # --- 4. LOGIN ---
    driver.get("https://app-v2.fu.do/app/#!/sales")
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()

    # --- 5. APLICAR FILTROS ---
    print(f"Aplicando rango: {fecha_inicio} hasta {fecha_fin}")
    
    # Seleccionar "Rango" en el desplegable
    select_tipo_elem = wait.until(EC.presence_of_element_located((By.XPATH, "//select[@ng-model='type']")))
    Select(select_tipo_elem).select_by_value("string:r")
    
    # Llenar fechas
    input_desde = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@ng-model='model.t1']")))
    input_hasta = driver.find_element(By.XPATH, "//input[@ng-model='model.t2']")
    
    input_desde.clear()
    input_desde.send_keys(fecha_inicio)
    input_hasta.clear()
    input_hasta.send_keys(fecha_fin)
    
    time.sleep(2) # Esperar que Angular tome el cambio

    # --- 6. EXPORTAR ---
    exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    exportar_btn.click()
    print("Descarga iniciada. Esperando archivo...")

    # --- 7. ESPERAR Y PROCESAR ARCHIVO ---
    # Esperamos hasta 20 segundos a que aparezca un archivo .zip
    found = False
    for i in range(20):
        archivos_zip = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if archivos_zip:
            found = True
            break
        time.sleep(1)

    if not found:
        raise Exception(f"No se encontró el ZIP en {base_path} después de 20s")

    # Tomar el zip más nuevo
    zip_file_path = max([os.path.join(base_path, f) for f in archivos_zip], key=os.path.getctime)
    
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        archivo_interno = zip_ref.namelist()[0]
        zip_ref.extract(archivo_interno, base_path)
        
        ruta_extraida = os.path.join(base_path, archivo_interno)
        ruta_destino_final = os.path.join(temp_excel_path, nombre_final)

        # Reemplazo limpio
        if os.path.exists(ruta_destino_final):
            os.remove(ruta_destino_final)
        
        shutil.move(ruta_extraida, ruta_destino_final)
        print(f"¡ÉXITO! Archivo guardado en: {ruta_destino_final}")

    # Limpiar el zip
    os.remove(zip_file_path)

except Exception as e:
    print(f"ERROR CRÍTICO: {e}")
    driver.save_screenshot("error_fudo.png") # Para ver qué pasó si falla

finally:
    driver.quit()
    print("Proceso finalizado.")
