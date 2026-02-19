import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

def calcular_margen_detallado():
    print("1. Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    sheet_costos = spreadsheet.worksheet("Maestro_Costos")

    # 2. Diccionario de Costos
    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    df_costos.columns = [str(c).strip() for c in df_costos.columns]
    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre']).to_dict()

    # 3. Datos de Ventas
    data_ventas = sheet_ventas.get_all_records()
    df_ventas = pd.DataFrame(data_ventas)
    df_ventas.columns = [str(c).strip() for c in df_ventas.columns]

    def calcular_costo_acumulado(celda_productos):
        if not celda_productos or str(celda_productos).lower() == 'nan': return 0
        items = [item.strip() for item in str(celda_productos).split(',')]
        return sum(dict_costos.get(p, 0) for p in items)

    # CÁLCULO DE COLUMNAS NUEVAS
    print("Calculando nuevas columnas...")
    df_ventas['Costo_Total_Venta'] = df_ventas['Detalle_Productos'].apply(calcular_costo_acumulado)
    df_ventas['Total'] = pd.to_numeric(df_ventas['Total'], errors='coerce').fillna(0)
    df_ventas['Margen_Neto_$'] = (df_ventas['Total'] - df_ventas['Costo_Total_Venta']).round(2)
    df_ventas['Margen_Neto_%'] = np.where(df_ventas['Total'] > 0, 
                                        ((df_ventas['Margen_Neto_$'] / df_ventas['Total']) * 100).round(1), 0)

    # 4. ACTUALIZACIÓN FORZADA DE HOJA 1
    print("Enviando datos a Hoja 1...")
    
    # Limpiamos valores que Google no acepta y convertimos a STRING
    df_final = df_ventas.replace([np.nan, np.inf, -np.inf], 0)
    
    # Preparamos el bloque de datos (Encabezados + Filas)
    # Convertir a string evita que Google Sheets rechace formatos numéricos de Python
    cuerpo_datos = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()

    # Operación de escritura
    sheet_ventas.clear() # Limpia la hoja vieja
    
    # IMPORTANTE: Usamos 'values' como argumento con nombre para compatibilidad en la nube
    sheet_ventas.update(range_name='A1', values=cuerpo_datos)
    
    print(f"✅ Hoja 1 actualizada con {len(df_final)} filas y nuevas columnas de Margen.")

if __name__ == "__main__":
    calcular_margen_detallado()
