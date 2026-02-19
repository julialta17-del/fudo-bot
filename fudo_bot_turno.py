import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

def ejecutar_analisis_fidelizacion():
    print("1. Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope) if creds_json else Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    # LEER HISTORICO
    sheet_hist = spreadsheet.worksheet("Historico")
    df_h = pd.DataFrame(sheet_hist.get_all_records())
    df_h.columns = [str(c).strip() for c in df_h.columns]

    # TRATAMIENTO DE DATOS
    df_h['Fecha_DT'] = pd.to_datetime(df_h['Fecha'], dayfirst=True, errors='coerce')
    df_h['Total_Num'] = pd.to_numeric(df_h['Total'], errors='coerce').fillna(0)

    print("2. Calculando promedios y Turno Habitual...")

    # Función para sacar la Moda (lo que más se repite)
    def obtener_moda(serie):
        if serie.empty: return "N/A"
        m = serie.mode()
        return m.iloc[0] if not m.empty else "N/A"

    # A) Calculamos HÁBITOS (Turno, Canal y Pago que más se repiten)
    habitos = df_h.groupby('Cliente').agg({
        'Turno': obtener_moda,
        'Origen': obtener_moda,
        'Medio de Pago': obtener_moda
    }).reset_index()
    habitos.columns = ['Cliente', 'Turno_Habitual', 'Canal_Habitual', 'Pago_Habitual']

    # B) Calculamos MÉTRICAS (Cantidad, Ticket Promedio, Última Visita)
    metricas = df_h.groupby('Cliente').agg({
        'Id': 'count',
        'Total_Num': 'mean',
        'Fecha_DT': 'max',
        'Detalle_Productos': 'last'
    }).reset_index()
    metricas.columns = ['Cliente', 'Cant_Pedidos', 'Ticket_Promedio', 'Ultima_Visita', 'Ultimo_Pedido']

    # UNIÓN FINAL
    resultado = pd.merge(metricas, habitos, on='Cliente', how='left')

    # SEGMENTACIÓN
    hoy = pd.Timestamp.now()
    resultado['Dias_Inactivo'] = (hoy - resultado['Ultima_Visita']).dt.days
    resultado['Ticket_Promedio'] = resultado['Ticket_Promedio'].round(2)
    resultado['Ultima_Visita'] = resultado['Ultima_Visita'].dt.strftime('%d/%m/%Y')

    def segmentar(fila):
        if fila['Cant_Pedidos'] >= 5: return "⭐ VIP"
        elif fila['Dias_Inactivo'] > 45: return "💤 Dormido"
        elif fila['Cant_Pedidos'] >= 2: return "✅ Frecuente"
        else: return "🆕 Nuevo"

    resultado['Segmento'] = resultado.apply(segmentar, axis=1)

    # ORDEN DE COLUMNAS FORZADO
    columnas_finales = [
        'Cliente', 
        'Segmento', 
        'Cant_Pedidos', 
        'Ticket_Promedio', 
        'Turno_Habitual', 
        'Canal_Habitual', 
        'Pago_Habitual', 
        'Ultimo_Pedido', 
        'Ultima_Visita', 
        'Dias_Inactivo'
    ]
    
    df_final = resultado[columnas_finales].sort_values(by='Cant_Pedidos', ascending=False)

    # SUBIR RESULTADOS
    print("3. Actualizando hoja 'Analisis_Clientes'...")
    try:
        sheet_cli = spreadsheet.worksheet("Analisis_Clientes")
    except:
        sheet_cli = spreadsheet.add_worksheet(title="Analisis_Clientes", rows="5000", cols="15")

    sheet_cli.clear()
    df_final = df_final.fillna("N/A")
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()
    sheet_cli.update(values=datos_subir, range_name='A1')

    print(f"✅ ¡LISTO! Clientes procesados: {len(df_final)}. Turno habitual calculado.")

if __name__ == "__main__":
    ejecutar_analisis_fidelizacion()