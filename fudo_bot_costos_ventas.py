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
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope) if creds_json else Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    # Cargamos Hoja 1 e Historico (donde están los costos calculados)
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    sheet_costos = spreadsheet.worksheet("Maestro_Costos")

    print("2. Procesando diccionarios de costos...")
    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    # Creamos un diccionario: {'Nombre del Producto': Costo_Pesos}
    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre']).to_dict()

    print("3. Analizando ventas de Hoja 1...")
    data_ventas = sheet_ventas.get_all_records()
    df_ventas = pd.DataFrame(data_ventas)

    # --- FUNCIÓN CLAVE: SUMAR TODOS LOS PRODUCTOS DE LA VENTA ---
    def calcular_costo_acumulado(celda_productos):
        if not celda_productos or str(celda_productos).lower() == 'nan':
            return 0
        
        # Separamos por coma (ej: "Burger, Papa, Coca" -> ["Burger", "Papa", "Coca"])
        lista_items = [item.strip() for item in str(celda_productos).split(',')]
        
        costo_total_venta = 0
        for producto in lista_items:
            # Buscamos el costo de CADA item en el diccionario. Si no existe, suma 0.
            costo_total_venta += dict_costos.get(producto, 0)
            
        return costo_total_venta

    # Aplicamos la suma a cada fila de la Hoja 1
    # Asegúrate que la columna con los nombres de productos se llame exactamente 'Detalle_Productos' o 'Productos'
    col_nombre_productos = 'Detalle_Productos' # Cambiar si el nombre es otro
    
    df_ventas['Costo_Total_Venta'] = df_ventas[col_nombre_productos].apply(calcular_costo_acumulado)
    
    # Calculamos Márgenes
    df_ventas['Margen_Neto_$'] = (df_ventas['Total'] - df_ventas['Costo_Total_Venta']).round(2)
    df_ventas['Margen_Neto_%'] = np.where(
        df_ventas['Total'] > 0, 
        ((df_ventas['Margen_Neto_$'] / df_ventas['Total']) * 100).round(1), 
        0
    )

    print("4. Actualizando Hoja 1 con márgenes reales...")
    # Limpiamos nans para Google
    df_final = df_ventas.replace([np.nan, np.inf, -np.inf], 0)
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()
    
    sheet_ventas.clear()
    sheet_ventas.update(values=datos_subir, range_name='A1')
    
    print(f"✅ ¡Éxito! Se calcularon los costos de {len(df_final)} ventas sumando todos sus productos.")

if __name__ == "__main__":
    calcular_margen_detallado()