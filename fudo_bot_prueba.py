import os
import time
import zipfile
import shutil
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuración de Rutas Dinámicas (GitHub y Linux compatibles) ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
nombre_final = "ventas.xls"

# Asegurar que las carpetas existan
os.makedirs(base_path, exist_ok=True)
os.makedirs(temp_excel_path, exist_ok=True)

# --- Configuración de Chrome ---
chrome_options = Options()
chrome_options.add_argument('--headless')  # Indispensable para GitHub Actions
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--window-size=1920,1080')

chrome_options.add_experimental_option("prefs", {
    "download.default_directory": base_path,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})

# Inicializar Driver con WebDriver Manager
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
wait = WebDriverWait(driver, 25)

try:
    print(f"Iniciando sesión en Fudo... Guardando en: {base_path}")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    
    # 1. LOGIN
    user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
    pass_input = driver.find_element(By.ID, "password")
    user_input.send_keys("admin@bigsaladssexta")
    pass_input.send_keys("bigsexta")
    pass_input.submit()
    
    # 2. APLICAR FILTRO "HOY" (Para evitar descargar días anteriores)
    print("Esperando carga de página para filtrar por 'Hoy'...")
    time.sleep(5) # Tiempo para que cargue la interfaz de ventas
    
    try:
        # Hacer clic en el selector de fechas
        selector_fecha = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.ert-date-filter-container")))
        selector_fecha.click()
        time.sleep(1)
        
        # Seleccionar la opción "Hoy"
        boton_hoy = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(),'Hoy')]")))
        boton_hoy.click()
        print("Filtro 'Hoy' aplicado con éxito.")
        time.sleep(3) # Esperar que la tabla se actualice
    except Exception as e:
        print(f"No se pudo aplicar el filtro de fecha (usando predeterminado): {e}")

    # 3. EXPORTAR
    exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    exportar_btn.click()
    print("Exportación iniciada. Esperando descarga...")
    
    # 4. LOCALIZAR Y PROCESAR EL ZIP
    timeout = 30
    seconds = 0
    zip_file = None
    
    while seconds < timeout:
        archivos = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
        if archivos:
            # Tomamos el más nuevo
            archivos_full = [os.path.join(base_path, f) for f in archivos]
            zip_file = max(archivos_full, key=os.path.getctime)
            break
        time.sleep(1)
        seconds += 1

    if not zip_file:
        print(f"Error: No se encontró el ZIP en {base_path}")
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
        print("Limpieza de archivos temporales completada.")

except Exception as e:
    print(f"Error crítico: {e}")
    # Opcional: Tomar captura de pantalla en caso de error para debug en GitHub
    driver.save_screenshot("error_fudo.png")

finally:
    driver.quit()
    print("Proceso terminado.")
