import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

# --- CAMBIO 1: Ruta para GitHub (No C:\) ---
ruta_excel = os.path.join(os.getcwd(), "descargas", "temp_excel", "ventas.xls")

def procesar_y_analizar():
    print(f"Buscando archivo en: {ruta_excel}")
    if not os.path.exists(ruta_excel):
        print(f"Error: No se encontró el archivo en {ruta_excel}")
        return

    # 1. CARGAR DATOS
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # Procesamiento de fechas
    if not pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    else:
        df_v['Fecha_DT'] = df_v['Creación']
    
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Hora_Int'] = df_v['Fecha_DT'].dt.hour 

    def asignar_turno(h):
        return "Mañana" if h < 16 else "Noche"

    df_v['Turno'] = df_v['Hora_Int'].apply(asignar_turno)

    # 2. CARGAR HOJAS ADICIONALES (Tus columnas de Descuento y Envío)
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    # Agrupar Productos
    prod_resumen = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    prod_resumen.columns = ['Id', 'Detalle_Productos']

    # Agrupar Descuentos
    desc_resumen = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    desc_resumen.columns = ['Id', 'Descuento_Total']

    # Agrupar Envíos
    envio_resumen = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()
    envio_resumen.columns = ['Id', 'Costo_Envio']

    # 3. CONSOLIDACIÓN (Unimos todo)
    consolidado = df_v[['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']].merge(prod_resumen, on='Id', how='left')
    consolidado = consolidado.merge(desc_resumen, on='Id', how='left')
    consolidado = consolidado.merge(envio_resumen, on='Id', how='left')

    # Rellenar vacíos
    consolidado[['Descuento_Total', 'Costo_Envio']] = consolidado[['Descuento_Total', 'Costo_Envio']].fillna(0)
    consolidado['Detalle_Productos'] = consolidado['Detalle_Productos'].fillna("Sin detalle")

    # 4. SUBIR A GOOGLE
    subir_a_google(consolidado)

def subir_a_google(consolidado):
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # CAMBIO 2: Credenciales desde Secreto de GitHub
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_data = spreadsheet.worksheet("Hoja 1")
    
    sheet_data.clear()
    
    # Convertimos a lista de listas y todo a STRING para evitar errores de formato
    datos_finales = [consolidado.columns.values.tolist()] + consolidado.fillna("").astype(str).values.tolist()
    
    # CAMBIO 3: Sintaxis de update compatible con GitHub
    sheet_data.update(range_name='A1', values=datos_finales)

    print(f"✅ Análisis completado. Se subieron {len(consolidado)} filas a la Hoja 1.")

if __name__ == "__main__":
    procesar_y_analizar()
