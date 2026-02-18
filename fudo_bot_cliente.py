from selenium import webdriver

from selenium.webdriver.chrome.service import Service

from selenium.webdriver.common.by import By

from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.chrome.options import Options

import time

from webdriver_manager.chrome import ChromeDriverManager

import gspread

from google.oauth2.service_account import Credentials



# =====================

# GOOGLE SHEETS

# =====================

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)

client = gspread.authorize(creds)

# Asegurate de que el nombre de la hoja sea exacto (puedes probar con .get_worksheet(0) para la primera)

sheet = client.open("Prueba clientes PEYA").get_worksheet(0)



# =====================

# CHROME

# =====================

chrome_options = Options()

chrome_options.add_experimental_option("detach", True) 

service = Service(ChromeDriverManager().install()) 

driver = webdriver.Chrome(service=service, options=chrome_options)

wait = WebDriverWait(driver, 30)



# =====================

# 1. INICIAR SESIÓN

# =====================

driver.get("https://app-v2.fu.do/app/#!/delivery")

user_input = wait.until(EC.presence_of_element_located((By.ID, "user")))

pass_input = driver.find_element(By.ID, "password")

user_input.send_keys("admin@bigsaladssexta")

pass_input.send_keys("bigsexta")

pass_input.submit()

print("Login OK")



# =====================

# 2. ACTUALIZAR PÁGINA

# =====================

time.sleep(5)

print("Actualizando página...")

driver.refresh()

time.sleep(15) 



# =====================

# 3. INTENTAR IR A ENTREGADOS (OPCIONAL)

# =====================

try:

    # Si ya estás ahí, esto fallará pero el script seguirá

    entregados = driver.find_element(By.XPATH, "//*[contains(text(),'ENTREGADOS')]")

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", entregados)

    time.sleep(2)

    driver.execute_script("arguments[0].click();", entregados)

    print("Sección ENTREGADOS abierta.")

except:

    print("Ya en ENTREGADOS o botón no visible, procediendo...")



# =====================

# 4. MOSTRAR MÁS RESULTADOS (UN SOLO CLIC)

# =====================

time.sleep(5)

try:

    btn_mas = driver.find_elements(By.XPATH, "//*[contains(text(), 'Mostrar más')]")

    if btn_mas and btn_mas[0].is_displayed():

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_mas[0])

        time.sleep(2)

        driver.execute_script("arguments[0].click();", btn_mas[0])

        print("Botón 'Mostrar más' presionado.")

        time.sleep(8) 

except:

    print("No se encontró el botón de carga extra.")



# =====================

# 5. TRANSCRIBIR DATOS (MÉTODO REFORZADO)

# =====================

print("Iniciando transcripción...")

filas = driver.find_elements(By.XPATH, "//tr[td]")

print(f"Pedidos detectados: {len(filas)}")



for fila in filas:

    try:

        celdas = fila.find_elements(By.TAG_NAME, "td")

        if len(celdas) >= 5:

            # Extraemos texto crudo de cada celda importante

            id_p = celdas[0].text.strip()

            hora = celdas[1].text.strip()

            tel = celdas[3].text.strip()

            cli = celdas[4].text.strip()

            # El monto suele ser la última o penúltima celda

            tot = celdas[-1].text.strip()



            # Evitamos guardar la fila de encabezado comparando el texto

            if id_p.lower() == "id" or id_p == "":

                continue



            # Mandamos la fila al Excel

            sheet.append_row([id_p, hora, tel, cli, tot])

            print(f"ÉXITO: Guardado pedido {id_p} de {cli}")

            

    except Exception as e:

        print(f"Error procesando una fila: {e}")



print("PROCESO TERMINADO - Revisá tu Excel")