import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

# --- CONFIGURACIÓN DE RUTAS RELATIVAS ---
ruta_excel = os.path.join("descargas", "temp_excel", "ventas.xls")

def procesar_y_analizar():
    print(f"Buscando archivo en: {ruta_excel}")
    if not os.path.exists(ruta_excel):
        print(f"Error: No se encontró el archivo en {ruta_excel}")
        return

    # 1. CARGAR DATOS
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_v.columns = df_v.columns.str.strip()
    
    # Procesamiento de fechas (mantenemos tu lógica)
    if not pd.api.types.is_datetime64_any_dtype(df_v['Creación']):
        df_v['Fecha_DT'] = pd.to_datetime(df_v['Creación'], unit='D', origin='1899-12-30', errors='coerce')
    else:
        df_v['Fecha_DT'] = df_v['Creación']
    
    df_v['Fecha_Texto'] = df_v['Fecha_DT'].dt.strftime('%d/%m/%Y')
    df_v['Hora_Exacta'] = df_v['Fecha_DT'].dt.strftime('%H:%M')
    df_v['Hora_Int'] = df_v['Fecha_DT'].dt.hour 

    def asignar_turno(h):
        if h < 15: return "Mañana"
        elif h >= 19: return "Noche"
        else: return "Tarde/Intermedio"

    df_v['Turno'] = df_v['Hora_Int'].apply(asignar_turno)

    # Cargar hojas secundarias
    df_p = pd.read_excel(ruta_excel, sheet_name='Pagos')
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_d = pd.read_excel(ruta_excel, sheet_name='Descuentos')
    df_e = pd.read_excel(ruta_excel, sheet_name='Costos de Envío')

    # 2. PROCESAR MÉTRICAS
    prod_resumen = df_a.groupby('Id. Venta').agg({
        'Producto': lambda x: ', '.join(x.astype(str)),
        'Precio': 'sum'
    }).reset_index().rename(columns={'Id. Venta': 'Id', 'Producto': 'Detalle_Productos', 'Precio': 'Total_Productos_Bruto'})

    desc_resumen = df_d.groupby('Id. Venta')['Valor'].sum().reset_index().rename(columns={'Id. Venta': 'Id', 'Valor': 'Descuento_Total'})
    envio_resumen = df_e.groupby('Id. Venta')['Valor'].sum().reset_index().rename(columns={'Id. Venta': 'Id', 'Valor': 'Costo_Envio'})

    columnas_interes = ['Id', 'Fecha_Texto', 'Hora_Exacta', 'Turno', 'Cliente', 'Total', 'Origen', 'Medio de Pago']
    consolidado = df_v[columnas_interes].merge(prod_resumen, on='Id', how='left')
    consolidado = consolidado.merge(desc_resumen, on='Id', how='left')
    consolidado = consolidado.merge(envio_resumen, on='Id', how='left')
    consolidado[['Total_Productos_Bruto', 'Descuento_Total', 'Costo_Envio']] = consolidado[['Total_Productos_Bruto', 'Descuento_Total', 'Costo_Envio']].fillna(0)

    # Métricas Resumen
    ventas_turno = consolidado.groupby('Turno').agg({'Id': 'count', 'Total': 'sum'}).reset_index()
    top_5 = df_a['Producto'].value_counts().head(5).reset_index()
    pagos_resumen = df_p.groupby('Medio de Pago')['Monto'].sum().reset_index().sort_values(by='Monto', ascending=False)

    # 3. SUBIR A GOOGLE
    subir_a_google(consolidado, top_5, ventas_turno, pagos_resumen)

def subir_a_google(consolidado, top5, turnos, pagos):
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    sheet_data = spreadsheet.get_worksheet(0)
    sheet_data.clear()
    sheet_data.update([consolidado.columns.values.tolist()] + consolidado.fillna("").astype(str).values.tolist(), 'A1')

    print("✅ Análisis subido a Google Sheets.")

if __name__ == "__main__":
    procesar_y_analizar()
