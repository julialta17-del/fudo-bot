import os
import time
import zipfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# --- RUTAS DINÁMICAS (Funcionan en GitHub y Windows) ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
nombre_final = "ventas.xls"

os.makedirs(base_path, exist_ok=True)
os.makedirs(temp_excel_path, exist_ok=True)

chrome_options = Options()
chrome_options.add_argument('--headless') # Invisible para la nube
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
    print("Accediendo a Fudo...")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    
    # Login
    user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
    pass_input = driver.find_element(By.ID, "password")
    user_input.send_keys("admin@bigsaladssexta")
    pass_input.send_keys("bigsexta")
    pass_input.submit()
    
    # Exportación
    exportar_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[ert-download-file='downloadSales()']")))
    exportar_btn.click()
    print("Descarga iniciada...")
    time.sleep(10) # Tiempo para que baje el ZIP

    # Localizar y extraer
    archivos_zip = [f for f in os.listdir(base_path) if f.lower().endswith(".zip")]
    if not archivos_zip:
        print("Error: No se encontró el ZIP.")
    else:
        zip_path = os.path.join(base_path, archivos_zip[0])
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            archivo_interno = zip_ref.namelist()[0]
            zip_ref.extract(archivo_interno, base_path)
            
            ruta_destino = os.path.join(temp_excel_path, nombre_final)
            if os.path.exists(ruta_destino): os.remove(ruta_destino)
            shutil.move(os.path.join(base_path, archivo_interno), ruta_destino)
            print(f"Éxito: Archivo listo en {ruta_destino}")
        os.remove(zip_path)

except Exception as e:
    print(f"Error: {e}")
finally:
    driver.quit()
