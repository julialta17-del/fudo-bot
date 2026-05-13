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
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    # LEER HISTORICO
    try:
        sheet_hist = spreadsheet.worksheet("Historico")
        df_h = pd.DataFrame(sheet_hist.get_all_records())
    except Exception as e:
        print(f"Error al acceder al Historico: {e}")
        return

    if df_h.empty:
        print("El Historico está vacío.")
        return

    df_h.columns = [str(c).strip() for c in df_h.columns]

    # --- TRATAMIENTO DE DATOS ---
    col_fecha = 'Fecha' if 'Fecha' in df_h.columns else 'Fecha_Texto'
    df_h['Fecha_DT'] = pd.to_datetime(df_h[col_fecha], dayfirst=True, errors='coerce')

    # FIX: limpiar formato numérico argentino antes de convertir
    # Elimina '$', puntos de miles y convierte coma decimal a punto
    df_h['Total_Num'] = (
        df_h['Total']
        .astype(str)
        .str.strip()
        .str.replace(r'[$\s]', '', regex=True)   # quita $ y espacios
        .str.replace('.', '', regex=False)         # quita separador de miles (punto)
        .str.replace(',', '.', regex=False)        # convierte coma decimal a punto
        .pipe(pd.to_numeric, errors='coerce')
        .fillna(0)
    )

    # DEBUG: imprime una muestra para verificar que los valores son correctos
    print("Muestra de Total_Num después de limpiar:")
    print(df_h[['Total', 'Total_Num']].head(10).to_string())

    print("2. Calculando promedios y Turno Habitual...")

    def obtener_moda(serie):
        if serie.empty: return "N/A"
        m = serie.mode()
        return m.iloc[0] if not m.empty else "N/A"

    # A) HÁBITOS
    habitos = df_h.groupby('Cliente').agg({
        'Turno': obtener_moda,
        'Origen': obtener_moda,
        'Medio de Pago': obtener_moda
    }).reset_index()
    habitos.columns = ['Cliente', 'Turno_Habitual', 'Canal_Habitual', 'Pago_Habitual']

    # B) MÉTRICAS
    metricas = df_h.groupby('Cliente').agg({
        'Id': 'count',
        'Total_Num': 'mean',
        'Fecha_DT': 'max',
        'Detalle_Productos': 'last'
    }).reset_index()
    metricas.columns = ['Cliente', 'Cant_Pedidos', 'Ticket_Promedio', 'Ultima_Visita', 'Ultimo_Pedido']

    resultado = pd.merge(metricas, habitos, on='Cliente', how='left')

    # --- SEGMENTACIÓN ---
    hoy = pd.Timestamp.now()
    resultado['Dias_Inactivo'] = (hoy - resultado['Ultima_Visita']).dt.days
    resultado['Ticket_Promedio'] = resultado['Ticket_Promedio'].round(2)

    def segmentar(fila):
        if fila['Cant_Pedidos'] >= 5:
            return "⭐ VIP" if fila['Dias_Inactivo'] <= 60 else "⚠️ VIP en Riesgo"
        elif fila['Dias_Inactivo'] > 45:
            return "💤 Dormido"
        elif fila['Cant_Pedidos'] >= 2:
            return "✅ Frecuente"
        else:
            return "🆕 Nuevo"

    resultado['Segmento'] = resultado.apply(segmentar, axis=1)
    resultado['Ultima_Visita'] = resultado['Ultima_Visita'].dt.strftime('%d/%m/%Y')

    columnas_finales = [
        'Cliente', 'Segmento', 'Cant_Pedidos', 'Ticket_Promedio',
        'Turno_Habitual', 'Canal_Habitual', 'Pago_Habitual',
        'Ultimo_Pedido', 'Ultima_Visita', 'Dias_Inactivo'
    ]

    df_final = resultado[columnas_finales].sort_values(by='Cant_Pedidos', ascending=False)

    # --- SUBIR RESULTADOS ---
    print("3. Actualizando hoja 'Analisis_Clientes'...")
    try:
        sheet_cli = spreadsheet.worksheet("Analisis_Clientes")
    except:
        sheet_cli = spreadsheet.add_worksheet(title="Analisis_Clientes", rows="5000", cols="15")

    sheet_cli.clear()
    df_final = df_final.fillna("N/A")
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()
    sheet_cli.update(values=datos_subir, range_name='A1')

    print(f"✅ ¡Hecho! Clientes analizados: {len(df_final)}")

if __name__ == "__main__":
    ejecutar_analisis_fidelizacion()
