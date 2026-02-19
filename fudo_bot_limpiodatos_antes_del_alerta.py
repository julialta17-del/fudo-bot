import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

def ejecutar_control_cancelaciones():
    print("🔍 Iniciando control de pedidos sin borrar columnas...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    
    # 1. Leer TODOS los datos actuales (incluyendo las columnas de Margen)
    records = sheet_ventas.get_all_records()
    if not records:
        print("La hoja está vacía.")
        return
        
    df = pd.DataFrame(records)
    df.columns = [str(c).strip() for c in df.columns]

    # 2. LÓGICA DE CLASIFICACIÓN (Sin filtrar filas, solo etiquetando)
    df['Total'] = pd.to_numeric(df['Total'], errors='coerce').fillna(0)
    
    def clasificar_nulos(fila):
        precio = fila['Total']
        canal = str(fila.get('Origen', '')).strip().lower()
        
        if precio == 0:
            if 'pedidos ya' in canal or 'peya' in canal:
                return "VENTA CANCELADA (PeYa)"
            elif canal in ["", "nan", "local"]:
                return "PEDIDO BORRADO (Manual)"
            else:
                return "PEDIDO ANULADO"
        return "VENTA REAL"

    # Creamos o actualizamos la columna de control conservando el resto
    df['Estado_Control'] = df.apply(clasificar_nulos, axis=1)

    # 3. GUARDADO SEGURO
    print("Sincronizando datos conservando márgenes...")
    
    # Reemplazamos valores que dan error en Google Sheets
    df_subir = df.fillna("").replace(['nan', 'None', 'inf', '-inf'], "")
    
    # Preparamos los datos: Encabezados + Filas
    datos_finales = [df_subir.columns.tolist()] + df_subir.astype(str).values.tolist()
    
    # Limpiamos y pegamos TODO el bloque completo
    sheet_ventas.clear()
    sheet_ventas.update(range_name='A1', values=datos_finales)
    
    print(f"✅ Proceso terminado. Se conservaron {len(df.columns)} columnas.")

if __name__ == "__main__":
    ejecutar_control_cancelaciones()
