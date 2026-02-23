import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np
from datetime import datetime

def calcular_margen_detallado_big_salads():
    print("1. Conectando a Google Sheets desde GitHub...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Carga de credenciales desde Secrets de GitHub
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        # Fallback para pruebas locales
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    sheet_costos = spreadsheet.worksheet("Maestro_Costos")

    # 2. PROCESAR DICCIONARIO DE COSTOS
    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    # Limpieza de espacios en nombres de productos para matchear bien
    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre'].str.strip()).to_dict()

    # 3. LEER VENTAS ACTUALES
    data_ventas = sheet_ventas.get_all_records()
    df_ventas = pd.DataFrame(data_ventas)
    df_ventas.columns = df_ventas.columns.str.strip()

    # --- CÁLCULOS DE COSTO E INSUMOS ---
    def calcular_costo_acumulado(celda_productos):
        if not celda_productos or str(celda_productos).lower() == 'nan':
            return 0
        # Separar por coma y limpiar espacios
        lista_items = [item.strip() for item in str(celda_productos).split(',')]
        return sum(dict_costos.get(producto, 0) for producto in lista_items)

    df_ventas['Costo_Total_Venta'] = df_ventas['Detalle_Productos'].apply(calcular_costo_acumulado)

    # --- LÓGICA FINANCIERA (Comisión PeYa 30%) ---
    def procesar_finanzas(fila):
        venta = pd.to_numeric(fila['Total'], errors='coerce') or 0
        costo_insumos = fila['Costo_Total_Venta']
        origen = str(fila.get('Origen', '')).lower()
        
        # Cálculo de la tajada de Pedidos Ya
        comision = round(venta * 0.30, 2) if "pedidos ya" in origen else 0
        # Margen final: Venta - Insumos - Comisión
        margen = round(venta - costo_insumos - comision, 2)
        
        return pd.Series([comision, margen])

    df_ventas[['Comision_PeYa_$', 'Margen_Neto_$']] = df_ventas.apply(procesar_finanzas, axis=1)
    
    df_ventas['Margen_Neto_%'] = np.where(
        df_ventas['Total'] > 0, 
        ((df_ventas['Margen_Neto_$'] / df_ventas['Total']) * 100).round(1), 
        0
    )

    # --- 4. REORDENAMIENTO ESTRATÉGICO DE COLUMNAS ---
    # Identificamos todas las columnas excepto la de comisión
    columnas_resto = [c for c in df_ventas.columns if c != 'Comision_PeYa_$']
    # Creamos el nuevo orden poniendo 'Comision_PeYa_$' al final absoluto
    nuevo_orden = columnas_resto + ['Comision_PeYa_$']
    
    # Reestructuramos el DataFrame
    df_final = df_ventas[nuevo_orden].copy()

    print("5. Sincronizando Hoja 1 en Drive...")
    df_final = df_final.replace([np.nan, np.inf, -np.inf], 0)
    
    # Preparar matriz de datos (Headers + Filas)
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()
    
    # Limpiar y actualizar
    sheet_ventas.clear()
    sheet_ventas.update(range_name='A1', values=datos_subir)
    
    print(f"✅ Sincronización exitosa. La comisión quedó en la última columna de la derecha.")

if __name__ == "__main__":
    calcular_margen_detallado_big_salads()
