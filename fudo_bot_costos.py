import os
import time
import zipfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuración de Rutas con formato 'raw' para Windows ---
base_path = r"C:\fudo_bot\descargas"
temp_excel_path = r"C:\fudo_bot\descargas\temp_excel2"
nombre_final = "productos.xls"

# Asegurar que las carpetas existan
os.makedirs(base_path, exist_ok=True)
os.makedirs(temp_excel_path, exist_ok=True)

chrome_options = Options()
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": base_path,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})

driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 20)

try:
    # 1. LOGIN Y EXPORTAR (Tu lógica de Fudo)
    driver.get("https://app-v2.fu.do/app/#!/products")
    user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
    pass_input = driver.find_element(By.ID, "password")
    user_input.send_keys("admin@bigsaladssexta")
    pass_input.send_keys("bigsexta")
    pass_input.submit()
    
    exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadProducts()']")))
    exportar_btn.click()
    print("Exportación iniciada. Esperando 5 segundos...")
    
    time.sleep(5) # Tiempo de gracia para que el ZIP aparezca

    # 2. LOCALIZAR EL ZIP
    archivos_zip = [os.path.join(base_path, f) for f in os.listdir(base_path) if f.lower().endswith(".zip")]
    
    if not archivos_zip:
        print(f"Error: No se encontró el ZIP en {base_path}")
    else:
        # El más reciente
        zip_file = max(archivos_zip, key=os.path.getctime)
        print(f"Extrayendo: {zip_file}")

        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            nombres = zip_ref.namelist()
            if nombres:
                archivo_interno = nombres[0]
                # Extraemos temporalmente en la carpeta base
                zip_ref.extract(archivo_interno, base_path)
                
                ruta_extraida = os.path.join(base_path, archivo_interno)
                ruta_destino_final = os.path.join(temp_excel_path, nombre_final)

                # --- LÓGICA DE REEMPLAZO FORZADO ---
                if os.path.exists(ruta_destino_final):
                    os.remove(ruta_destino_final)
                    print("Archivo anterior eliminado para reemplazo.")

                # Movemos y renombramos al mismo tiempo
                shutil.move(ruta_extraida, ruta_destino_final)
                print(f"¡ÉXITO! Archivo guardado en: {ruta_destino_final}")

        # Limpieza del ZIP
        os.remove(zip_file)
        print("ZIP temporal borrado.")

except Exception as e:
    print(f"Error crítico: {e}")

finally:
    driver.quit()
    print("Proceso terminado.")