import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

def limpiar_dinero(serie):
    """
    Normaliza montos para que Python no confunda miles con decimales.
    Maneja: $1.250,50 -> 1250.50
    """
    serie = serie.astype(str).str.replace('$', '', regex=False).str.strip()
    
    def corregir_formato(val):
        if not val or val.lower() in ['nan', 'none', '']: return "0"
        
        # Caso 1.250,50 (Punto miles, coma decimal)
        if '.' in val and ',' in val:
            return val.replace('.', '').replace(',', '.')
        
        # Caso 1250,50 (Solo coma decimal)
        if ',' in val:
            partes = val.split(',')
            if len(partes[-1]) <= 2: return val.replace(',', '.') # Es decimal
            else: return val.replace(',', '') # Es miles tipo 1,250
                
        # Caso 1.250 (Solo punto de miles)
        if '.' in val:
            partes = val.split('.')
            if len(partes[-1]) <= 2: return val # Es decimal tipo 1250.50
            else: return val.replace('.', '') # Es miles tipo 1.250
        
        return val

    serie = serie.apply(corregir_formato)
    return pd.to_numeric(serie, errors='coerce').fillna(0)

def ejecutar_control_cancelaciones():
    print("🔍 Iniciando control de pedidos respetando formatos numéricos...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    
    records = sheet_ventas.get_all_records()
    if not records:
        print("La hoja está vacía.")
        return
        
    df = pd.DataFrame(records)
    df.columns = [str(c).strip() for c in df.columns]

    # --- CAMBIO CLAVE AQUÍ ---
    # En lugar de pd.to_numeric directo, usamos nuestra función de limpieza
    df['Total_Limpio'] = limpiar_dinero(df['Total'])
    
    def clasificar_nulos(fila):
        precio = fila['Total_Limpio']
        canal = str(fila.get('Origen', '')).strip().lower()
        
        if precio == 0:
            if 'pedidos ya' in canal or 'peya' in canal:
                return "VENTA CANCELADA (PeYa)"
            elif canal in ["", "nan", "local"]:
                return "PEDIDO BORRADO (Manual)"
            else:
                return "PEDIDO ANULADO"
        return "VENTA REAL"

    df['Estado_Control'] = df.apply(clasificar_nulos, axis=1)
    
    # Eliminamos la columna temporal antes de subir para no duplicar datos
    df = df.drop(columns=['Total_Limpio'])

    # 3. GUARDADO SEGURO
    print("Sincronizando datos...")
    df_subir = df.fillna("").replace(['nan', 'None', 'inf', '-inf'], "")
    datos_finales = [df_subir.columns.tolist()] + df_subir.astype(str).values.tolist()
    
    sheet_ventas.clear()
    sheet_ventas.update(range_name='A1', values=datos_finales)
    
    print(f"✅ Proceso terminado. Se mantuvo la integridad de los montos en {len(df)} filas.")

if __name__ == "__main__":
    ejecutar_control_cancelaciones()
