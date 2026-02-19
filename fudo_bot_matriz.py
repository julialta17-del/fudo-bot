import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np

def ejecutar_matriz_estrella():
    print("1. Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope) if creds_json else Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    # Traemos los datos necesarios
    sheet_hist = spreadsheet.worksheet("Historico")
    sheet_costos = spreadsheet.worksheet("Maestro_Costos")
    sheet_adiciones = spreadsheet.worksheet("Hoja 1") # O donde tengas el detalle de productos

    df_hist = pd.DataFrame(sheet_hist.get_all_records())
    df_costos = pd.DataFrame(sheet_costos.get_all_records())
    
    print("2. Calculando popularidad y rentabilidad...")

    # A) Contamos cuántas veces se vendió cada producto (Popularidad)
    # Fudo separa productos por coma, así que los "explotamos" para contar uno por uno
    df_hist['Lista_Prod'] = df_hist['Detalle_Productos'].str.split(',')
    df_items = df_hist.explode('Lista_Prod')
    df_items['Lista_Prod'] = df_items['Lista_Prod'].str.strip()
    
    popularidad = df_items['Lista_Prod'].value_counts().reset_index()
    popularidad.columns = ['Nombre', 'Cantidad_Vendida']

    # B) Cruzamos con el Maestro de Costos (Rentabilidad)
    matriz = pd.merge(popularidad, df_costos, on='Nombre', how='inner')
    
    # Filtramos columnas útiles
    matriz = matriz[['Nombre', 'Cantidad_Vendida', 'Precio', 'Costo', 'Margen_$', 'Margen_%']]
    
    # C) Definimos los puntos de corte (Mediana)
    mediana_ventas = matriz['Cantidad_Vendida'].median()
    mediana_margen = matriz['Margen_$'].median()

    # D) Clasificación Matriz BCG
    def clasificar(row):
        if row['Cantidad_Vendida'] >= mediana_ventas and row['Margen_$'] >= mediana_margen:
            return "⭐ ESTRELLA"
        elif row['Cantidad_Vendida'] >= mediana_ventas and row['Margen_$'] < mediana_margen:
            return "🐴 CABALLITO"
        elif row['Cantidad_Vendida'] < mediana_ventas and row['Margen_$'] >= mediana_margen:
            return "💎 JOYA"
        else:
            return "🗑️ PERRO"

    matriz['Categoria_Estrategica'] = matriz.apply(clasificar, axis=1)
    matriz = matriz.sort_values(by=['Categoria_Estrategica', 'Cantidad_Vendida'], ascending=[True, False])

    print("3. Actualizando hoja Matriz_Productos...")
    try:
        sheet_matriz = spreadsheet.worksheet("Matriz_Productos")
    except:
        sheet_matriz = spreadsheet.add_worksheet(title="Matriz_Productos", rows="1000", cols="10")

    sheet_matriz.clear()
    datos_subir = [matriz.columns.tolist()] + matriz.astype(str).values.tolist()
    sheet_matriz.update(values=datos_subir, range_name='A1')

    print(f"✅ Matriz finalizada. Tenés {len(matriz)} productos analizados estratégicamente.")

if __name__ == "__main__":
    ejecutar_matriz_estrella()