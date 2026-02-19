import os
import time
import zipfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuración de Rutas Universales (Funcionan en Windows y GitHub) ---
# Usamos el directorio actual del script para no depender de C:
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
nombre_final = "ventas.xls"

# Asegurar que las carpetas existan
os.makedirs(base_path, exist_ok=True)
os.makedirs(temp_excel_path, exist_ok=True)

chrome_options = Options()
# --- CONFIGURACIÓN PARA GITHUB ACTIONS ---
chrome_options.add_argument('--headless') # Navegador invisible
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--window-size=1920,1080')

chrome_options.add_experimental_option("prefs", {
    "download.default_directory": base_path,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})

# Inicializar Driver
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 25)

try:
    print(f"Iniciando sesión en Fudo... Guardando en: {base_path}")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    
    # Login
    user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
    pass_input = driver.find_element(By.ID, "password")
    user_input.send_keys("admin@bigsaladssexta")
    pass_input.send_keys("bigsexta")
    pass_input.submit()
    
    # Esperar y Click en Exportar
    exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    exportar_btn.click()
    print("Exportación iniciada. Esperando descarga...")
    
    # Esperar a que el archivo aparezca (máximo 30 segundos)
    timeout = 30
    seconds = 0
    zip_file = None
    
    while seconds < timeout:
        archivos = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if archivos:
            zip_file = os.path.join(base_path, max(archivos, key=lambda f: os.path.getctime(os.path.join(base_path, f))))
            break
        time.sleep(1)
        seconds += 1

    if not zip_file:
        print(f"Error: El tiempo de espera terminó y no se encontró el ZIP en {base_path}")
    else:
        print(f"Extrayendo: {zip_file}")
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            nombres = zip_ref.namelist()
            if nombres:
                archivo_interno = nombres[0]
                zip_ref.extract(archivo_interno, base_path)
                
                ruta_extraida = os.path.join(base_path, archivo_interno)
                ruta_destino_final = os.path.join(temp_excel_path, nombre_final)

                if os.path.exists(ruta_destino_final):
                    os.remove(ruta_destino_final)
                
                shutil.move(ruta_extraida, ruta_destino_final)
                print(f"¡ÉXITO! Archivo guardado en: {ruta_destino_final}")

        os.remove(zip_file)

except Exception as e:
    print(f"Error crítico: {e}")

finally:
    driver.quit()
    print("Proceso terminado.")
