import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

def calcular_margen_detallado():
    print("1. Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Priorizamos la variable de entorno de GitHub
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    sheet_costos = spreadsheet.worksheet("Maestro_Costos")

    print("2. Procesando diccionarios de costos...")
    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    
    # Limpiamos espacios en nombres por seguridad
    df_costos.columns = [str(c).strip() for c in df_costos.columns]
    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre']).to_dict()

    print("3. Analizando ventas de Hoja 1...")
    data_ventas = sheet_ventas.get_all_records()
    df_ventas = pd.DataFrame(data_ventas)
    df_ventas.columns = [str(c).strip() for c in df_ventas.columns]

    def calcular_costo_acumulado(celda_productos):
        if not celda_productos or str(celda_productos).lower() == 'nan':
            return 0
        lista_items = [item.strip() for item in str(celda_productos).split(',')]
        costo_total_venta = 0
        for producto in lista_items:
            costo_total_venta += dict_costos.get(producto, 0)
        return costo_total_venta

    col_nombre_productos = 'Detalle_Productos'
    
    # Aseguramos que las columnas existan antes de operar
    if col_nombre_productos in df_ventas.columns:
        df_ventas['Costo_Total_Venta'] = df_ventas[col_nombre_productos].apply(calcular_costo_acumulado)
        df_ventas['Total'] = pd.to_numeric(df_ventas['Total'], errors='coerce').fillna(0)
        
        df_ventas['Margen_Neto_$'] = (df_ventas['Total'] - df_ventas['Costo_Total_Venta']).round(2)
        df_ventas['Margen_Neto_%'] = np.where(
            df_ventas['Total'] > 0, 
            ((df_ventas['Margen_Neto_$'] / df_ventas['Total']) * 100).round(1), 
            0
        )
    else:
        print(f"Error: No se encontró la columna {col_nombre_productos}")
        return

    print("4. Actualizando Hoja 1 con márgenes reales...")
    # Limpieza de nans e infinitos para Google
    df_final = df_ventas.replace([np.nan, np.inf, -np.inf], 0)
    
    # CONVERSIÓN CRUCIAL PARA GITHUB:
    # Pasamos todo a string y usamos el formato de lista de listas
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()
    
    # En la nube, clear() + update() es más seguro que solo update()
    sheet_ventas.clear()
    
    # AJUSTE TÉCNICO: Pasamos 'values' como argumento nombrado para evitar errores de versión
    sheet_ventas.update(range_name='A1', values=datos_subir)
    
    print(f"✅ ¡Éxito! Se actualizaron {len(df_final)} ventas.")

if __name__ == "__main__":
    calcular_margen_detallado()
