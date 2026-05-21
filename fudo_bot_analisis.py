import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np
from datetime import datetime

# --- CONFIGURACIÓN DE RUTAS ---
base_path = os.path.join(os.getcwd(), "descargas")
temp_excel_path = os.path.join(base_path, "temp_excel")
ruta_excel = os.path.join(temp_excel_path, "ventas.xls")

# Función para limpiar y convertir valores monetarios de Fudo
def limpiar_numero(x):
    if pd.isna(x):
        return 0.0
    if isinstance(x, str):
        x = x.replace('$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(x)
    except ValueError:
        return 0.0

def procesar_y_analizar():
    print(f"Buscando archivo en: {ruta_excel}")
    
    if not os.path.exists(ruta_excel):
        print(f"❌ Error: No se encontró el archivo en {ruta_excel}")
        return

    # 1. CARGAR DATOS
    print("Cargando datos desde Excel...")
    try:
        df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
        df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
        df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
        df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')
    except Exception as e:
        print(f"❌ Error al leer las pestañas del Excel: {e}")
        return

    df_v.columns = df_v.columns.str.strip()
    
    # Procesamiento de fechas
    if not pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    else:
        df_v['Fecha_DT'] = df_v['Creación']
    
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Hora_Int'] = df_v['Fecha_DT'].dt.hour 

    # Asignación de Turnos
    df_v['Turno'] = df_v['Hora_Int'].apply(lambda h: "Mañana" if h < 16 else "Noche")

    # Limpiamos las columnas monetarias
    df_v['Total'] = df_v['Total'].apply(limpiar_numero)
    df_d['Valor'] = df_d['Valor'].apply(limpiar_numero)
    df_e['Valor'] = df_e['Valor'].apply(limpiar_numero)

    # 2. AGRUPAR ADICIONALES
    prod_resumen = df_a.groupby('Id. Venta')['Producto'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
    prod_resumen.columns = ['Id', 'Detalle_Productos']

    desc_resumen = df_d.groupby('Id. Venta')['Valor'].sum().reset_index()
    desc_resumen.columns = ['Id', 'Descuento_Total']

    envio_resumen = df_e.groupby('Id. Venta')['Valor'].sum().reset_index()
    envio_resumen.columns = ['Id', 'Costo_Envio']

    # 3. CONSOLIDACIÓN
    columnas_interes = ['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']
    consolidado = df_v[columnas_interes].copy()
    
    consolidado = consolidado.merge(prod_resumen, on='Id', how='left')
    consolidado = consolidado.merge(desc_resumen, on='Id', how='left')
    consolidado = consolidado.merge(envio_resumen, on='Id', how='left')

    # Rellenar valores vacíos
    consolidado['Descuento_Total'] = consolidado['Descuento_Total'].fillna(0.0)
    consolidado['Costo_Envio'] = consolidado['Costo_Envio'].fillna(0.0)
    consolidado['Total'] = consolidado['Total'].fillna(0.0)
    consolidado['Detalle_Productos'] = consolidado['Detalle_Productos'].fillna("Sin detalle")

    # === NUEVAS COLUMNAS Y REORDENAMIENTO ===
    
    # 1. Total_Productos_Bruto: Asumimos que Total = Bruto - Descuento + Envío
    consolidado['Total_Productos_Bruto'] = consolidado['Total'] + consolidado['Descuento_Total'] - consolidado['Costo_Envio']
    
    # 2. Inicializar métricas vacías en 0.0 para que sean tratadas como números en Sheets
    columnas_extra = [
        'Costo_Total_Venta', 'Comision_PeYa_$', 'Comision_Tienda_Online_$', 
        'Margen_Neto_$', 'Margen_Neto_%', 'Costo_MO_$'
    ]
    for col in columnas_extra:
        consolidado[col] = 0.0
        
    # 3. Pedidos_en_Turno: Cuenta automática de pedidos agrupados por fecha y turno
    consolidado['Pedidos_en_Turno'] = consolidado.groupby(['Fecha_Texto', 'Turno'])['Id'].transform('count')

    # 4. Definir el orden final exacto de las columnas
    columnas_finales = [
        'Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago',
        'Detalle_Productos', 'Total_Productos_Bruto', 'Descuento_Total', 'Costo_Envio',
        'Costo_Total_Venta', 'Comision_PeYa_$', 'Comision_Tienda_Online_$',
        'Margen_Neto_$', 'Margen_Neto_%', 'Costo_MO_$', 'Pedidos_en_Turno'
    ]
    
    # Filtramos y ordenamos el DataFrame
    consolidado = consolidado[columnas_finales]

    print(f"✅ Consolidado generado: {len(consolidado)} filas procesadas.")

    # 4. SUBIR A GOOGLE SHEETS
    subir_a_google(consolidado)

def subir_a_google(consolidado):
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    
    try:
        spreadsheet = client.open("Analisis Fudo")
        sheet_data = spreadsheet.worksheet("Hoja 1")
        
        sheet_data.clear()
        
        # Reemplazamos NaN para evitar errores JSON, conservando los formatos numéricos
        consolidado = consolidado.replace({np.nan: ""})
        
        datos_finales = [consolidado.columns.values.tolist()] + consolidado.values.tolist()
        
        sheet_data.update(range_name='A1', values=datos_finales)
        print("🚀 Hoja 1 actualizada con éxito en Google Sheets.")
    except Exception as e:
        print(f"❌ Error al subir a Google Sheets: {e}")

if __name__ == "__main__":
    procesar_y_analizar()
