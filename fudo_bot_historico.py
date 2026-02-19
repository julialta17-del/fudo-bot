import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

def ejecutar_sincronizacion_macro():
    print("Conectando con Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # --- CONEXIÓN SEGURA ---
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    try:
        sheet_uno = spreadsheet.worksheet("Hoja 1")
        data_uno = pd.DataFrame(sheet_uno.get_all_records())
    except Exception as e:
        print(f"Error al leer Hoja 1: {e}")
        return

    if data_uno.empty:
        print("La Hoja 1 está vacía. Terminando.")
        return

    # GESTIÓN DEL HISTÓRICO
    try:
        sheet_hist = spreadsheet.worksheet("Historico")
        data_hist = pd.DataFrame(sheet_hist.get_all_records())
    except gspread.exceptions.WorksheetNotFound:
        sheet_hist = spreadsheet.add_worksheet(title="Historico", rows="50000", cols="30")
        sheet_hist.append_row(data_uno.columns.tolist())
        data_hist = pd.DataFrame(columns=data_uno.columns)

    # LÓGICA DE COMPARACIÓN POR ID
    data_uno['Id_Str'] = data_uno['Id'].astype(str).str.replace('.0', '', regex=False).str.strip()
    
    if not data_hist.empty and 'Id' in data_hist.columns:
        ids_viejos = data_hist['Id'].astype(str).str.replace('.0', '', regex=False).str.strip().tolist()
        nuevos_datos = data_uno[~data_uno['Id_Str'].isin(ids_viejos)].copy()
    else:
        nuevos_datos = data_uno.copy()

    if not nuevos_datos.empty:
        filas_a_subir = nuevos_datos.drop(columns=['Id_Str']).fillna("")
        sheet_hist.append_rows(filas_a_subir.values.tolist())
        print(f"✅ Se agregaron {len(filas_a_subir)} filas nuevas.")
    else:
        print("El Historico ya está actualizado.")

    print("Actualizando Dashboard Macro...")
    df_macro = pd.DataFrame(sheet_hist.get_all_records())
    df_macro.columns = df_macro.columns.str.strip()

    # Operaciones de Dashboard (se mantiene tu lógica)
    col_plata = next((c for c in df_macro.columns if 'Total' in str(c)), 'Total')
    df_macro[col_plata] = pd.to_numeric(df_macro[col_plata], errors='coerce').fillna(0)
    
    # ... (Resto de tu lógica de agrupación)

if __name__ == "__main__":
    ejecutar_sincronizacion_macro()
