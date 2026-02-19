import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

def ejecutar_control_cancelaciones():
    print("🔍 Iniciando control de pedidos...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    
    df = pd.DataFrame(sheet_ventas.get_all_records())
    df.columns = df.columns.str.strip()
    df['Total'] = pd.to_numeric(df['Total'], errors='coerce').fillna(0)
    
    def clasificar(fila):
        precio = fila['Total']
        canal = str(fila.get('Origen', '')).strip().lower()
        if precio == 0:
            if 'pedidos ya' in canal or 'peya' in canal: return "VENTA CANCELADA (PeYa)"
            return "PEDIDO BORRADO"
        return "VENTA REAL"

    df['Estado_Control'] = df.apply(clasificar, axis=1)
    df_subir = df.astype(str).replace(['nan', 'None'], "")
    
    sheet_ventas.clear()
    sheet_ventas.update([df_subir.columns.tolist()] + df_subir.values.tolist())
    print("✅ Hoja 1 limpia y clasificada.")

if __name__ == "__main__":
    ejecutar_control_cancelaciones()
