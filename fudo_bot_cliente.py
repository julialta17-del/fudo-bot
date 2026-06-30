import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def ejecutar_bot_clientes():
    # --- CONEXIÓN SEGURA A GOOGLE ---
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
        
    client = gspread.authorize(creds)
    sheet = client.open("Prueba clientes PEYA").get_worksheet(0)
    print("Conectado a Google Sheets OK")

    # --- CONFIGURACIÓN CHROME (MODO NUBE) ---
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    service = Service(ChromeDriverManager().install()) 
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 40)

    try:
        # 1. LOGIN
        driver.get("https://app-v2.fu.do/app/#!/delivery")
        user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))
        pass_input = driver.find_element(By.ID, "password")
        user_input.send_keys("admin@bigsaladssexta")
        pass_input.send_keys("bigsexta")
        pass_input.submit()
        print("Login OK")

        time.sleep(5)
        print("Actualizando página...")
        driver.refresh()
        time.sleep(12) 

        # 2. SELECCIONAR ENTREGADOS
        try:
            entregados = wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'ENTREGADOS')]")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", entregados)
            time.sleep(2)
            driver.execute_script("arguments[0].click();", entregados)
            print("Sección ENTREGADOS abierta.")
        except Exception as e:
            print(f"Sección entregados no clickeable, continuando... Detalle: {e}")

        # 3. ESPERA INTELIGENTE A QUE APAREZCA LA TABLA CON DATOS
        print("Esperando renderizado de las filas de Fudo...")
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//tr[td]")))
            time.sleep(3)
        except:
            print("Alerta: No se detectaron filas en el tiempo de espera. Probablemente la tabla está vacía.")

        # 4. TRANSCRIBIR
        filas = driver.find_elements(By.XPATH, "//tr[td]")
        print(f"Pedidos detectados en pantalla: {len(filas)}")

        for fila in filas:
            try:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                
                # Verificamos que tenga suficientes columnas para ser un pedido válido
                if len(celdas) >= 5:
                    
                    # ========================================================
                    # MODO DEBUG (DETECTOR DE COLUMNAS)
                    # Esto te va a imprimir en consola qué hay exactamente en cada número
                    # ========================================================
                    print("\n--- LEYENDO NUEVO PEDIDO ---")
                    for i, celda in enumerate(celdas): 
                        print(f"Índice {i}: {celda.text.strip()}")
                    print("----------------------------")

                    # Asignamos los valores (ajusta el índice de 'cli' si el Debug te muestra otro número)
                    id_p = celdas[0].text.strip()
                    hora = celdas[1].text.strip()
                    
                    # ⚠️ OJO AQUÍ: Según tu foto, visualmente es la 4. 
                    # Si el log de arriba te muestra que el nombre está en la 5, cambia este número a 5.
                    cli = celdas[4].text.strip() 
                    
                    tot = celdas[-1].text.strip() # El -1 siempre agarra la última columna (Total)

                    # Lógica para encontrar el teléfono sea donde sea que esté escondido
                    tel = "No encontrado"
                    for celda in celdas:
                        texto_celda = celda.text.strip()
                        if "+54" in texto_celda:
                            tel = texto_celda
                            break

                    # Saltamos cabeceras o filas rotas
                    if id_p.lower() == "id" or not id_p:
                        continue

                    # Subida de datos a la nube
                    sheet.append_row([id_p, hora, tel, cli, tot])
                    print(f"ÉXITO: Guardado pedido {id_p} | Cliente: {cli} | Tel: {tel}")
            
            except Exception as e_fila:
                print(f"Error procesando una fila individual: {e_fila}")

    except Exception as e:
        print(f"Error general del bot: {e}")
    finally:
        driver.quit()
        print("Navegador cerrado. PROCESO TERMINADO")

if __name__ == "__main__":
    ejecutar_bot_clientes()
