import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np
from datetime import datetime

# --- CONFIGURACIÓN DE RUTAS ---
ruta_excel = os.path.join("descargas", "temp_excel", "ventas.xls")

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
    
    # --- FILTRO DE SEGURIDAD: SOLO HOY ---
    # Obtenemos la fecha de hoy en el mismo formato que Fudo
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    print(f"Filtrando ventas para la fecha: {fecha_hoy}")
    
    # Filtramos el DataFrame para que solo queden las filas de hoy
    df_v = df_v[df_v['Fecha_DT'].dt.strftime('%Y-%m-%d') == fecha_hoy].copy()
    
    if df_v.empty:
        print("⚠️ Atención: No hay ventas registradas con fecha de hoy en el archivo descargado.")
        # Opcional: podrías detener el proceso aquí para no borrar la Hoja 1 con datos vacíos
        # return 

    print(f"Se conservaron {len(df_v)} ventas de hoy.")

    # 2. CONTINUAR CON EL PROCESAMIENTO NORMAL
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Hora_Int'] = df_v['Fecha_DT'].dt.hour 

    def asignar_turno(h):
        if h < 16: return "Mañana"
        else: return "Noche"

    df_v['Turno'] = df_v['Hora_Int'].apply(asignar_turno)

    # Cargar adiciones (productos) y cruzar para tener el detalle
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    prod_resumen = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    prod_resumen.columns = ['Id', 'Detalle_Productos']

    # Unir datos
    consolidado = df_v[['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']].merge(prod_resumen, on='Id', how='left')

    # 3. SUBIR A GOOGLE SHEETS
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
    
    # Al hacer .clear() y luego .update(), nos aseguramos de que los datos viejos de ayer se borren
    sheet_data.clear()
    datos_finales = [consolidado.columns.values.tolist()] + consolidado.fillna("").astype(str).values.tolist()
    sheet_data.update(range_name='A1', values=datos_finales)

    print("✅ Hoja 1 actualizada solo con datos de hoy.")

if __name__ == "__main__":
    procesar_y_analizar()
