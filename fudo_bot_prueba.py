import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np
from datetime import datetime

# --- CONFIGURACIÓN DE RUTAS (Adaptadas para GitHub) ---
ruta_excel = os.path.join("descargas", "temp_excel", "ventas.xls")

def procesar_y_analizar():
    print(f"Buscando archivo en: {ruta_excel}")
    if not os.path.exists(ruta_excel):
        print(f"Error: No se encontró el archivo en {ruta_excel}")
        return

    # 1. CARGAR DATOS
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # Procesamiento de fecha original de Fudo
    if not pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    else:
        df_v['Fecha_DT'] = df_v['Creación']
    
    # --- FILTRO DE SEGURIDAD: SOLO HOY ---
    fecha_hoy_str = datetime.now().strftime('%d/%m/%Y')
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    
    print(f"Filtrando ventas para hoy: {fecha_hoy_str}")
    df_v = df_v[df_v['Fecha_Texto'] == fecha_hoy_str].copy()

    # 2. PROCESAMIENTO DE HORA Y TURNO
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Hora_Int'] = df_v['Fecha_DT'].dt.hour 

    def asignar_turno(h):
        return "Mañana" if h < 16 else "Noche"

    df_v['Turno'] = df_v['Hora_Int'].apply(asignar_turno)

    # 3. CARGAR HOJAS ADICIONALES (PRODUCTOS, DESCUENTOS, ENVÍOS)
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    # Resumen de Productos por Venta
    prod_resumen = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    prod_resumen.columns = ['Id', 'Detalle_Productos']

    # Resumen de Descuentos
    desc_resumen = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    desc_resumen.columns = ['Id', 'Descuento_Total']

    # Resumen de Costos de Envío
    envio_resumen = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()
    envio_resumen.columns = ['Id', 'Costo_Envio']

    # 4. CONSOLIDACIÓN FINAL (Aquí sumamos tus columnas clave)
    consolidado = df_v[['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']].merge(prod_resumen, on='Id', how='left')
    consolidado = consolidado.merge(desc_resumen, on='Id', how='left')
    consolidado = consolidado.merge(envio_resumen, on='Id', how='left')

    # Rellenar ceros en columnas numéricas si no hubo descuento o envío
    consolidado[['Descuento_Total', 'Costo_Envio']] = consolidado[['Descuento_Total', 'Costo_Envio']].fillna(0)
    consolidado['Detalle_Productos'] = consolidado['Detalle_Productos'].fillna("Sin detalle")

    # 5. SUBIR A GOOGLE SHEETS
    subir_a_google(consolidado)

def subir_a_google(consolidado):
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_data = spreadsheet.worksheet("Hoja 1")
    
    sheet_data.clear()
    # Convertimos a string para asegurar compatibilidad total en la subida
    datos_finales = [consolidado.columns.values.tolist()] + consolidado.fillna("").astype(str).values.tolist()
    sheet_data.update(range_name='A1', values=datos_finales)

    print(f"✅ Hoja 1 actualizada con {len(consolidado)} ventas de hoy (incluye Descuentos y Envíos).")

if __name__ == "__main__":
    procesar_y_analizar()
