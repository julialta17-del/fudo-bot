import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

def ejecutar_control_cancelaciones():
    print("🔍 Iniciando control de pedidos con precio $0...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope) if creds_json else Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    
    # 1. Leer datos actuales de Hoja 1
    df = pd.DataFrame(sheet_ventas.get_all_records())
    df.columns = df.columns.str.strip()

    # --- LÓGICA DE CONTROL ---
    # Aseguramos que el total sea numérico
    df['Total'] = pd.to_numeric(df['Total'], errors='coerce').fillna(0)
    
    # Definimos la columna de Estado si no existe
    if 'Estado_Control' not in df.columns:
        df['Estado_Control'] = "OK"

    # Aplicamos tu lógica:
    # Si Precio es 0 y es Pedidos Ya -> Venta Cancelada
    # Si Precio es 0 y Canal está vacío -> Pedido Borrado
    
    def clasificar_nulos(fila):
        precio = fila['Total']
        canal = str(fila.get('Origen', '')).strip().lower()
        
        if precio == 0:
            if 'pedidos ya' in canal or 'peya' in canal:
                return "VENTA CANCELADA (PeYa)"
            elif canal == "" or canal == "nan" or canal == "local":
                return "PEDIDO BORRADO (Manual)"
            else:
                return "PEDIDO ANULADO"
        return "VENTA REAL"

    df['Estado_Control'] = df.apply(clasificar_nulos, axis=1)

    # 2. Contabilizar para informar
    cancelados = df[df['Estado_Control'] == "VENTA CANCELADA (PeYa)"].shape[0]
    borrados = df[df['Estado_Control'] == "PEDIDO BORRADO (Manual)"].shape[0]

    # 3. Actualizar Hoja 1 con la nueva columna de control
    print(f"Sincronizando: {cancelados} cancelados y {borrados} borrados detectados.")
    
    df_subir = df.astype(str).replace(['nan', 'None'], "")
    datos = [df_subir.columns.tolist()] + df_subir.values.tolist()
    
    sheet_ventas.clear()
    sheet_ventas.update(values=datos, range_name='A1')
    
    print("✅ Hoja 1 actualizada con el control de estados.")

if __name__ == "__main__":
    ejecutar_control_cancelaciones()