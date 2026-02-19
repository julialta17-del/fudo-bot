import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

def calcular_margen_detallado():
    print("1. Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # --- CONEXIÓN SEGURA ---
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        # Esto solo corre en tu PC si tenés el archivo
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    try:
        sheet_ventas = spreadsheet.worksheet("Hoja 1")
        sheet_costos = spreadsheet.worksheet("Maestro_Costos")
    except Exception as e:
        print(f"❌ Error: No se encontraron las hojas necesarias. {e}")
        return

    print("2. Procesando diccionarios de costos...")
    # Leemos costos y limpiamos nombres de columnas
    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    df_costos.columns = [str(c).strip() for c in df_costos.columns]
    
    if 'Costo' not in df_costos.columns or 'Nombre' not in df_costos.columns:
        print("❌ Error: Maestro_Costos debe tener columnas 'Nombre' y 'Costo'.")
        return
        
    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre']).to_dict()

    print("3. Analizando ventas de Hoja 1...")
    data_ventas = sheet_ventas.get_all_records()
    if not data_ventas:
        print("⚠️ Hoja 1 vacía.")
        return
        
    df_ventas = pd.DataFrame(data_ventas)
    df_ventas.columns = [str(c).strip() for c in df_ventas.columns]

    # --- FUNCIÓN DE CÁLCULO ---
    def calcular_costo_acumulado(celda_productos):
        if not celda_productos or str(celda_productos).lower() in ['nan', 'none', '']:
            return 0
        lista_items = [item.strip() for item in str(celda_productos).split(',')]
        return sum(dict_costos.get(producto, 0) for producto in lista_items)

    col_prod = 'Detalle_Productos'
    if col_prod not in df_ventas.columns:
        print(f"❌ Error: No se encontró la columna '{col_prod}' en Hoja 1.")
        return

    # Cálculos matemáticos
    df_ventas['Costo_Total_Venta'] = df_ventas[col_prod].apply(calcular_costo_acumulado)
    df_ventas['Total'] = pd.to_numeric(df_ventas['Total'], errors='coerce').fillna(0)
    
    df_ventas['Margen_Neto_$'] = (df_ventas['Total'] - df_ventas['Costo_Total_Venta']).round(2)
    
    # Evitar división por cero en el porcentaje
    df_ventas['Margen_Neto_%'] = np.where(
        df_ventas['Total'] > 0, 
        ((df_ventas['Margen_Neto_$'] / df_ventas['Total']) * 100).round(1), 
        0
    )

    print("4. Actualizando Hoja 1...")
    # Reemplazo de valores no aptos para JSON/Google Sheets
    df_final = df_ventas.replace([np.nan, np.inf, -np.inf], 0)
    
    sheet_ventas.clear()
    # Formateamos para subir: lista de listas
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()
    sheet_ventas.update(values=datos_subir, range_name='A1')
    
    print(f"✅ ¡Éxito! Margen calculado para {len(df_final)} ventas.")

if __name__ == "__main__":
    calcular_margen_detallado()
