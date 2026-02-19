import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

def ejecutar_sincronizacion_macro():
    # 1. CONEXIÓN A GOOGLE SHEETS
    print("Conectando con Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope) if creds_json else Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    # 2. CARGAR HOJAS DE GOOGLE (No de Excel)
    try:
        sheet_uno = spreadsheet.worksheet("Hoja 1")
    except:
        print("Error: No se encontró la 'Hoja 1' en Google Sheets.")
        return

    # Traemos los datos actuales de la Hoja 1
    data_uno = pd.DataFrame(sheet_uno.get_all_records())
    if data_uno.empty:
        print("La Hoja 1 está vacía.")
        return

    # 3. GESTIÓN DEL HISTÓRICO
    try:
        sheet_hist = spreadsheet.worksheet("Historico")
        data_hist = pd.DataFrame(sheet_hist.get_all_records())
    except gspread.exceptions.WorksheetNotFound:
        print("Creando hoja 'Historico'...")
        sheet_hist = spreadsheet.add_worksheet(title="Historico", rows="50000", cols="30")
        sheet_hist.append_row(data_uno.columns.tolist())
        data_hist = pd.DataFrame(columns=data_uno.columns)

    # 4. LÓGICA DE COMPARACIÓN (Hoja 1 vs Historico)
    # Limpiamos IDs para asegurar que coincidan (quitando .0 si existen)
    data_uno['Id_Str'] = data_uno['Id'].astype(str).str.replace('.0', '', regex=False).str.strip()
    
    if not data_hist.empty and 'Id' in data_hist.columns:
        ids_viejos = data_hist['Id'].astype(str).str.replace('.0', '', regex=False).str.strip().tolist()
        # Filtramos lo nuevo de la Hoja 1 que NO esté en el Historico
        nuevos_datos = data_uno[~data_uno['Id_Str'].isin(ids_viejos)].copy()
    else:
        nuevos_datos = data_uno.copy()

    # 5. PASAR TODO AL HISTÓRICO (Sin pisar nada)
    if not nuevos_datos.empty:
        # Quitamos columna auxiliar y subimos todas las columnas originales
        filas_a_subir = nuevos_datos.drop(columns=['Id_Str']).fillna("")
        sheet_hist.append_rows(filas_a_subir.values.tolist())
        print(f"Éxito: Se agregaron {len(filas_a_subir)} filas nuevas al Historico.")
    else:
        print("El Historico ya está actualizado con lo que hay en la Hoja 1.")

    # 6. ANÁLISIS MACRO (Dashboard con Gráficos)
    print("Actualizando Dashboard Macro...")
    # Leemos el histórico actualizado
    df_macro = pd.DataFrame(sheet_hist.get_all_records())
    df_macro.columns = df_macro.columns.str.strip()

    # Identificamos columnas (Id, Total, Fecha, Medio de Pago)
    col_plata = next((c for c in df_macro.columns if 'Total' in str(c)), 'Total')
    col_fecha = next((c for c in df_macro.columns if 'Fecha' in str(c)), 'Fecha')
    col_pago = next((c for c in df_macro.columns if 'Medio de Pago' in str(c)), 'Medio de Pago')

    # Convertimos a números para operar
    df_macro[col_plata] = pd.to_numeric(df_macro[col_plata], errors='coerce').fillna(0)

    # A. Resumen por Día
    resumen_dia = df_macro.groupby(col_fecha).agg({'Id': 'count', col_plata: 'sum'}).reset_index()
    resumen_dia.columns = ['Fecha', 'Cant_Pedidos', 'Monto_Total_$']

    # B. Resumen por Medio de Pago
    if col_pago in df_macro.columns:
        resumen_pago = df_macro.groupby(col_pago).agg({col_plata: 'sum', 'Id': 'count'}).reset_index()
        resumen_pago.columns = ['Medio de Pago', 'Total $', 'Cant. Operaciones']
    else:
        resumen_pago = pd.DataFrame([["No encontrado", 0, 0]])

    # 7. ESCRIBIR EN DASHBOARD_MACRO
    try:
        sheet_dash = spreadsheet.worksheet("Dashboard_Macro")
    except:
        sheet_dash = spreadsheet.add_worksheet(title="Dashboard_Macro", rows="200", cols="20")
    
    sheet_dash.clear()
    
    # Tabla 1: Tiempo
    sheet_dash.update('A1', [["HISTÓRICO TEMPORAL"], resumen_dia.columns.tolist()] + resumen_dia.values.tolist())
    
    # Tabla 2: Pagos
    sheet_dash.update('E1', [["HISTÓRICO MEDIOS DE PAGO"], resumen_pago.columns.tolist()] + resumen_pago.values.tolist())
    
    # 8. GRÁFICOS AUTOMÁTICOS
    crear_graficos_bi(spreadsheet, sheet_dash.id, len(resumen_dia), len(resumen_pago))
    print("Dashboard Macro finalizado con éxito.")

def crear_graficos_bi(spreadsheet, sheet_id, l_dia, l_pago):
    requests = [
        # Gráfico: Evolución de ventas ($) y Pedidos (Cant)
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Macro: Ventas y Comandas por Día",
                        "basicChart": {
                            "chartType": "COMBO",
                            "legendPosition": "BOTTOM_LEGEND",
                            "domains": [{"domain": {"sourceRange": {"sources": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1+l_dia, "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
                            "series": [
                                {"series": {"sourceRange": {"sources": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1+l_dia, "startColumnIndex": 1, "endColumnIndex": 2}]}}, "type": "BAR", "targetAxis": "LEFT_AXIS"},
                                {"series": {"sourceRange": {"sources": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1+l_dia, "startColumnIndex": 2, "endColumnIndex": 3}]}}, "type": "LINE", "targetAxis": "RIGHT_AXIS"}
                            ]
                        }
                    },
                    "position": {"newSheet": False, "overlayPosition": {"anchorCell": {"sheetId": sheet_id, "rowIndex": 12, "columnIndex": 0}}}
                }
            }
        }
    ]
    try:
        spreadsheet.batch_update({"requests": requests})
    except:
        pass

if __name__ == "__main__":
    ejecutar_sincronizacion_macro()