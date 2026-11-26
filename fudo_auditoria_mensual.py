import os
import time
import re
import json
import pandas as pd
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import Select

def limpiar_numero(val):
    if not val or str(val).strip() == "": return "0"
    match = re.search(r'([\d\.\,]+)', str(val))
    if match:
        v = match.group(1).replace('.', '').replace(',', '.')
        try:
            return str(int(round(float(v))))
        except:
            pass
    return "0"

def conectar_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    # Conecta al archivo "Analisis Fudo" y específicamente a la pestaña "Historico"
    return gspread.authorize(creds).open("Analisis Fudo").worksheet("Historico")

print("--- PASO 1: LEYENDO DATOS EXISTENTES EN GOOGLE SHEETS ---")
try:
    sheet = conectar_sheets()
    registros_sheets = sheet.get_all_records()
    
    mapa_sheets = {}
    for idx, fila in enumerate(registros_sheets, start=2):
        llave = f"{fila.get('Fecha_Texto', '')}_{fila.get('Hora_Exacta', '')}_{limpiar_numero(fila.get('Total', '0'))}"
        mapa_sheets[llave] = idx
        
    print(f"✅ Se encontraron {len(mapa_sheets)} registros en la hoja 'Historico'.")
except Exception as e:
    print(f"❌ Error leyendo Sheets: {e}")
    exit()

# --- SELENIUM ---
chrome_options = Options()
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1920,1080')
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {'timezoneId': 'America/Argentina/Buenos_Aires'})
wait = WebDriverWait(driver, 40)

nuevas_ventas = []
filas_a_eliminar = set()
llaves_encontradas_en_fudo = set()

try:
    print("--- PASO 2: EXTRACCIÓN DE DATOS EN FUDO ---")
    driver.get("https://app-v2.fu.do/app/#!/sales")
    time.sleep(5) 

    wait.until(EC.presence_of_element_located((By.ID, "user"))).send_keys("admin@bigsaladssexta")
    driver.find_element(By.ID, "password").send_keys("bigsexta")
    driver.find_element(By.ID, "password").submit()
    
    time.sleep(10)
    
    print("Cambiando filtro de fechas a 'Mensual'...")
    try:
        # Buscamos que sea interactuable antes de hacer nada
        dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.data-filter-type select")))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", dropdown)
        time.sleep(1)
        
        select_periodo = Select(dropdown)
        # Usamos el valor HTML interno en lugar del texto visible
        select_periodo.select_by_value("string:m")
        time.sleep(15) # Tiempo largo para que Angular cargue todo el mes
        
        # Validamos si realmente cambió
        if dropdown.get_attribute("value") != "string:m":
            raise Exception("El select no tomó el cambio.")
            
    except Exception as e:
        print("Forzando el filtro Mensual con eventos profundos de JavaScript...")
        driver.execute_script("""
            var select = document.querySelector('div.data-filter-type select');
            if(select){
                select.value = 'string:m';
                // Disparamos input y change para despertar a Angular
                select.dispatchEvent(new Event('input', { bubbles: true }));
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        time.sleep(15)
        
    print("Scrolleando la tabla para cargar todos los días del mes...")
    last_count = 0
    while True:
        filas = driver.find_elements(By.XPATH, "//table/tbody/tr")
        if len(filas) == last_count:
            break 
        last_count = len(filas)
        driver.execute_script("arguments[0].scrollIntoView();", filas[-1])
        time.sleep(2.5)
        
    print(f"Se cargaron {last_count} registros en pantalla. Iniciando auditoría...")

    filas_xpath = "//table/tbody/tr"
    
    for i in range(last_count):
        try:
            tr_list = driver.find_elements(By.XPATH, filas_xpath)
            if i >= len(tr_list): break
            fila = tr_list[i]
            celdas = fila.find_elements(By.TAG_NAME, "td")
            
            if len(celdas) < 8: continue
            
            estado = celdas[2].text.strip()
            hora_inicio_str = celdas[0].text.strip()
            cliente_str = celdas[5].text.strip()
            total_str = celdas[7].text.strip() 
            
            try:
                dt_obj = datetime.strptime(hora_inicio_str, "%d/%m/%y %H:%M:%S")
                fecha_texto = dt_obj.strftime("%d/%m/%Y")
                hora_exacta = dt_obj.strftime("%H:%M")
                turno = "Mañana" if dt_obj.hour < 16 else "Noche"
            except: continue 

            llave_actual = f"{fecha_texto}_{hora_exacta}_{limpiar_numero(total_str)}"
            llaves_encontradas_en_fudo.add(llave_actual)
            
            if estado.lower() != "cerrada":
                if llave_actual in mapa_sheets:
                    print(f"🗑️ Venta Cancelada/Abierta detectada en Fudo que está en Sheets: {llave_actual}. Marcando para eliminar.")
                    filas_a_eliminar.add(mapa_sheets[llave_actual])
                continue
                
            if llave_actual not in mapa_sheets:
                print(f"➕ Venta Faltante detectada: {fecha_texto} {hora_exacta} - ${total_str}. Extrayendo detalles...")
                
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", fila)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", fila)
                
                panel = wait.until(EC.presence_of_element_located((By.TAG_NAME, "ert-sales-show")))
                time.sleep(3)
                
                driver.execute_script("""
                    var panel_content = document.querySelector('ert-sales-show .content');
                    if (panel_content) { panel_content.scrollTo(0, panel_content.scrollHeight); }
                """)
                time.sleep(1.5)
                
                url_actual = driver.current_url
                id_venta = url_actual.split('/')[-1] if '/sales/' in url_actual else ""
                
                origen, medio_pago, detalle_productos, descuento, costo_envio = "", "", "", "0", "0"
                total_venta = total_str

                try:
                    total_venta = panel.find_element(By.CSS_SELECTOR, ".total strong").text
                except: pass

                try:
                    labels = panel.find_elements(By.CSS_SELECTOR, "ul.list.show li label")
                    for label in labels:
                        if "Tipo" in label.text:
                            if "Delivery" in label.text: origen = "Pedidos Ya"
                            elif "Mostrador" in label.text: origen = ""
                        if "Origen" in label.text and "Pedidos" in label.text: origen = "Pedidos Ya"
                except: pass

                try:
                    adiciones = panel.find_elements(By.CSS_SELECTOR, "ul.additions li.addition")
                    prods = []
                    for ad in adiciones:
                        if "canceled" not in ad.get_attribute("class"):
                            try:
                                qty = ad.find_element(By.CSS_SELECTOR, ".count").text.strip()
                                name = ad.find_element(By.CSS_SELECTOR, ".item-label").text.split('\n')[0].strip()
                                prods.append(f"{qty} {name}".strip())
                            except: pass
                    detalle_productos = " | ".join(prods)
                except: pass

                try:
                    modifiers = panel.find_elements(By.CSS_SELECTOR, "li.bill-modifier")
                    for mod in modifiers:
                        text = mod.text.lower()
                        try:
                            price = mod.find_element(By.CSS_SELECTOR, ".price").text
                            if "descuento" in text: descuento = price
                            elif "envío" in text or "envio" in text: costo_envio = price
                        except: pass
                except: pass

                try:
                    pagos_seccion = panel.find_element(By.CSS_SELECTOR, "ui-view[name='edit_payments']")
                    pagos_items = pagos_seccion.find_elements(By.CSS_SELECTOR, "li")
                    medios = []
                    for p in pagos_items:
                        if "canceled" not in p.get_attribute("class"):
                            try:
                                nombre_pago = p.find_element(By.CSS_SELECTOR, ".item-label").text.strip()
                                if nombre_pago: medios.append(nombre_pago)
                            except: pass
                    medio_pago = " | ".join(medios)
                except: pass

                nuevas_ventas.append([
                    id_venta, fecha_texto, hora_exacta, turno, cliente_str, limpiar_numero(total_venta), 
                    origen, medio_pago, detalle_productos, limpiar_numero(descuento), limpiar_numero(costo_envio), 
                    "", "", "", "", "", "", ""
                ])

        except Exception as error_fila:
            print(f"⚠️ Error en fila {i}. Saltando... {error_fila}")
            continue

    mes_actual = datetime.now().strftime("%m/%Y")
    for llave, fila_idx in mapa_sheets.items():
        if mes_actual in llave and llave not in llaves_encontradas_en_fudo:
            print(f"👻 Registro fantasma en Sheets (no existe en Fudo): {llave}. Marcando para eliminar.")
            filas_a_eliminar.add(fila_idx)

    print("\n--- PASO 3: SINCRONIZANDO CON GOOGLE SHEETS ---")
    
    if filas_a_eliminar:
        filas_ordenadas = sorted(list(filas_a_eliminar), reverse=True)
        print(f"Borrando {len(filas_ordenadas)} registros obsoletos o cancelados...")
        for f_idx in filas_ordenadas:
            try:
                sheet.delete_rows(f_idx)
                time.sleep(1.5) 
            except Exception as e:
                print(f"No se pudo borrar la fila {f_idx}: {e}")
    else:
        print("Ningún registro obsoleto para borrar.")

    if nuevas_ventas:
        print(f"Agregando {len(nuevas_ventas)} ventas faltantes al final del documento...")
        sheet.append_rows(nuevas_ventas, value_input_option='USER_ENTERED')
    else:
        print("No se encontraron ventas faltantes. Todo está sincronizado.")

    print("🚀 ¡AUDITORÍA MENSUAL FINALIZADA CON ÉXITO!")

except Exception as e:
    print(f"❌ ERROR CRÍTICO: {e}")
    
finally:
    driver.quit()
