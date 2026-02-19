import os
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import numpy as np

def calcular_margen_detallado():
    print("Iniciando cálculo de márgenes...")
    
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    sheet_costos = spreadsheet.worksheet("Maestro_Costos")

    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre']).to_dict()

    data_ventas = sheet_ventas.get_all_records()
    df_ventas = pd.DataFrame(data_ventas)

    def calcular_costo_acumulado(celda_productos):
        if not celda_productos or str(celda_productos).lower() == 'nan':
            return 0
        lista_items = [item.strip() for item in str(celda_productos).split(',')]
        return sum(dict_costos.get(producto, 0) for producto in lista_items)

    col_nombre_productos = 'Detalle_Productos' 
    df_ventas['Costo_Total_Venta'] = df_ventas[col_nombre_productos].apply(calcular_costo_acumulado)
    
    df_ventas['Margen_Neto_$'] = (df_ventas['Total'] - df_ventas['Costo_Total_Venta']).round(2)
    df_ventas['Margen_Neto_%'] = np.where(
        df_ventas['Total'] > 0, 
        ((df_ventas['Margen_Neto_$'] / df_ventas['Total']) * 100).round(1), 
        0
    )

    df_final = df_ventas.replace([np.nan, np.inf, -np.inf], 0)
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()
    
    sheet_ventas.clear()
    sheet_ventas.update(values=datos_subir, range_name='A1')
    print(f"✅ Éxito: Se calcularon márgenes para {len(df_final)} ventas.")

if __name__ == "__main__":
    calcular_margen_detallado()
