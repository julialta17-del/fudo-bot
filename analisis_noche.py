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

# --- CONFIGURACIÓN DE FECHAS ---
hoy = ayer = hoy + 1 
ayer = hoy - timedelta(days=1)

# Formato YYYY-MM-DD requerido por los inputs tipo date de HTML5
fecha_inicio = ayer.strftime("%Y-%m-%d") 
fecha_fin = hoy.strftime("%Y-%m-%d")

# --- CONFIGURACIÓN DE RUTAS ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
nombre_final = "ventas.xls"

os.makedirs(base_path, exist_ok=True)
os.makedirs(temp_excel_path, exist_ok=True)

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": base_path,
    "download.prompt_for_download": False,
    "safebrowsing.enabled": True
})

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 25)

try:
    # 1. LOGIN
    driver.get("https://app-v2.fu.do/app/#!/sales")
    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()

    # 2. APLICAR FILTROS DE FECHA
    print(f"Configurando rango: {fecha_inicio} al {fecha_fin}")
    
    # Seleccionar tipo "Rango"
    select_tipo = wait.until(EC.presence_of_element_located((By.NAME, "type") or (By.XPATH, "//select[@ng-model='type']")))
    Select(select_tipo).select_by_value("string:r")
    
    # Esperar a que los inputs de fecha aparezcan
    input_desde = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@ng-model='model.t1']")))
    input_hasta = driver.find_element(By.XPATH, "//input[@ng-model='model.t2']")

    # Limpiar y enviar fechas
    input_desde.clear()
    input_desde.send_keys(fecha_inicio)
    input_hasta.clear()
    input_hasta.send_keys(fecha_fin)
    
    time.sleep(2) # Pausa para que Angular procese el cambio

    # 3. EXPORTAR
    exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    exportar_btn.click()
    print("Descarga iniciada...")
    
    # Esperar a que el archivo aparezca (máximo 15 seg)
    timeout = 15
    while timeout > 0:
        archivos = [f for f in os.listdir(base_path) if f.endswith(".zip")]
        if archivos: break
        time.sleep(1)
        timeout -= 1

    # 4. PROCESAR ZIP
    archivos_zip = [os.path.join(base_path, f) for f in os.listdir(base_path) if f.lower().endswith(".zip")]
    if not archivos_zip:
        raise Exception("No se descargó ningún archivo ZIP.")

    zip_file = max(archivos_zip, key=os.path.getctime)
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        archivo_interno = zip_ref.namelist()[0]
        zip_ref.extract(archivo_interno, base_path)
        
        ruta_extraida = os.path.join(base_path, archivo_interno)
        ruta_destino_final = os.path.join(temp_excel_path, nombre_final)

        if os.path.exists(ruta_destino_final): os.remove(ruta_destino_final)
        shutil.move(ruta_extraida, ruta_destino_final)
        print(f"¡ÉXITO! Guardado en: {ruta_destino_final}")

    os.remove(zip_file)

except Exception as e:
    print(f"Error: {e}")
    # Captura de pantalla para debug en GitHub Actions si falla
    driver.save_screenshot("error_debug.png")

finally:
    driver.quit()
