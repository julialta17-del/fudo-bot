import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

def calcular_margen_detallado_big_salads():
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

    # 2. PROCESAR COSTOS
    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    # Limpieza de nombres en el maestro de costos
    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre'].astype(str).str.strip()).to_dict()

    # 3. LEER VENTAS
    data_ventas = sheet_ventas.get_all_records()
    df_ventas = pd.DataFrame(data_ventas)
    
    # --- ARREGLO PARA EL ERROR DE COLUMNAS ---
    # Forzamos que cada nombre de columna sea texto y quitamos espacios invisibles
    df_ventas.columns = [str(col).strip() for col in df_ventas.columns]

    # Eliminamos duplicados de columnas de cálculo por si el script falló antes
    cols_viejas = ['Costo_Total_Venta', 'Comision_PeYa_$', 'Margen_Neto_$', 'Margen_Neto_%']
    df_ventas = df_ventas.drop(columns=[c for c in cols_viejas if c in df_ventas.columns])

    # --- CÁLCULOS ---
    def calcular_costo_acumulado(celda_productos):
        if not celda_productos or str(celda_productos).lower() in ['nan', '']:
            return 0
        # Separamos productos por coma
        lista_items = [item.strip() for item in str(celda_productos).split(',')]
        return sum(dict_costos.get(producto, 0) for producto in lista_items)

    # Verificación de seguridad antes de aplicar
    if 'Detalle_Productos' in df_ventas.columns:
        df_ventas['Costo_Total_Venta'] = df_ventas['Detalle_Productos'].apply(calcular_costo_acumulado)
    else:
        print(f"❌ Error: No se encontró 'Detalle_Productos'. Columnas disponibles: {df_ventas.columns}")
        return

    def procesar_finanzas(fila):
        venta = pd.to_numeric(fila.get('Total', 0), errors='coerce') or 0
        costo_insumos = fila.get('Costo_Total_Venta', 0)
        origen = str(fila.get('Origen', '')).lower()
        
        # 30% PeYa
        comision = round(venta * 0.30, 2) if "pedidos ya" in origen else 0
        margen = round(venta - costo_insumos - comision, 2)
        return pd.Series([comision, margen])

    df_ventas[['Comision_PeYa_$', 'Margen_Neto_$']] = df_ventas.apply(procesar_finanzas, axis=1)
    
    df_ventas['Margen_Neto_%'] = np.where(
        df_ventas['Total'] > 0, 
        ((df_ventas['Margen_Neto_$'] / df_ventas['Total'].replace(0, 1)) * 100).round(1), 
        0
    )

    # --- REORDENAMIENTO FORZADO ---
    # Mandamos la comisión al final
    cols_final = [c for c in df_ventas.columns if c != 'Comision_PeYa_$'] + ['Comision_PeYa_$']
    df_final = df_ventas[cols_final].copy()

    print("5. Sincronizando Hoja 1...")
    df_final = df_final.replace([np.nan, np.inf, -np.inf], 0)
    datos_subir = [df_final.columns.tolist()] + df_final.values.tolist()
    
    sheet_ventas.clear()
    sheet_ventas.update(values=datos_subir, range_name='A1')
    print("✅ Proceso completado con éxito.")

if __name__ == "__main__":
    calcular_margen_detallado_big_salads()
