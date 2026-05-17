import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import numpy as np


def calcular_margen_detallado_big_salads():
    print("1. Conectando a Google Sheets...")
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)

    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    sheet_costos = spreadsheet.worksheet("Maestro_Costos")

    # -------------------------------------------------------
    # 2. PROCESAR COSTOS — conversión robusta de decimales
    # -------------------------------------------------------
    print("2. Leyendo costos...")
    df_costos = pd.DataFrame(sheet_costos.get_all_records())

    # ✅ FIX: Fudo exporta números con formato argentino (ej: "4.462,50")
    # Eliminamos el separador de miles y convertimos la coma decimal a punto
    df_costos['Costo'] = pd.to_numeric(
        df_costos['Costo'].astype(str)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)

    dict_costos = pd.Series(df_costos['Costo'].values, index=df_costos['Nombre']).to_dict()

    # -------------------------------------------------------
    # 3. LEER VENTAS
    # -------------------------------------------------------
    print("3. Leyendo ventas...")
    df_ventas = pd.DataFrame(sheet_ventas.get_all_records())

    if df_ventas.empty:
        print("⚠️ No hay ventas en Hoja 1. Fin del proceso.")
        return

    # -------------------------------------------------------
    # 4. COSTO DE INSUMOS POR PEDIDO
    #    ✅ FIX: Si el costo es 0 (producto no encontrado),
    #    usa el 35% del total de la venta como estimado
    # -------------------------------------------------------
    def calcular_costo_acumulado(fila):
        celda_productos = fila.get('Detalle_Productos', '')
        venta = pd.to_numeric(fila.get('Total', 0), errors='coerce') or 0

        if not celda_productos or str(celda_productos).lower() == 'nan':
            return round(venta * 0.35)

        lista_items = [item.strip() for item in str(celda_productos).split(',')]
        costo = sum(dict_costos.get(producto, 0) for producto in lista_items)

        # Si no encontró costos en el maestro, estima 35% de la venta
        if costo == 0:
            return round(venta * 0.35)

        return costo

    df_ventas['Costo_Total_Venta'] = df_ventas.apply(calcular_costo_acumulado, axis=1)

    # -------------------------------------------------------
    # 5. COSTO DE MANO DE OBRA POR PEDIDO
    #    2 empleados x $3.600 = $7.200 por turno
    #    Se divide entre todos los pedidos de ese turno en ese día
    # -------------------------------------------------------
    print("4. Calculando costo de mano de obra por pedido...")

    COSTO_TURNO = 3600 * 2  # $7.200 por turno completo (2 empleados)

    df_ventas['_fecha_turno'] = (
        df_ventas['Fecha_Texto'].astype(str).str.strip() + " | " +
        df_ventas['Turno'].astype(str).str.strip()
    )

    pedidos_por_turno = (
        df_ventas.groupby('_fecha_turno')['_fecha_turno']
        .transform('count')
    )

    df_ventas['Costo_MO_$']      = (COSTO_TURNO / pedidos_por_turno).round(0).astype(int)
    df_ventas['Pedidos_en_Turno'] = pedidos_por_turno.astype(int)

    df_ventas.drop(columns=['_fecha_turno'], inplace=True)

    # -------------------------------------------------------
    # 6. COMISIONES Y MARGEN NETO
    # -------------------------------------------------------
    def procesar_finanzas(fila):
        venta         = pd.to_numeric(fila.get('Total', 0), errors='coerce') or 0
        envio         = pd.to_numeric(fila.get('Costo_Envio', 0), errors='coerce') or 0
        descuento     = pd.to_numeric(fila.get('Descuento_Total', 0), errors='coerce') or 0
        costo_insumos = fila.get('Costo_Total_Venta', 0)
        costo_mo      = fila.get('Costo_MO_$', 0)

        origen_raw       = str(fila.get('Origen', '')).lower().strip()
        origen_sin_tilde = origen_raw.replace('é', 'e').replace('ú', 'u')

        comision_peya   = 0
        comision_online = 0

        if "pedidos ya" in origen_sin_tilde:
            comision_peya = round(venta * 0.30)
        elif "menu online" in origen_sin_tilde:
            comision_online = round((venta + envio + descuento) * 0.023)

        margen = round(venta - costo_insumos - comision_peya - comision_online - costo_mo)

        return pd.Series([comision_peya, comision_online, margen])

    print("5. Calculando márgenes y comisiones...")
    df_ventas[['Comision_PeYa_$', 'Comision_Tienda_Online_$', 'Margen_Neto_$']] = \
        df_ventas.apply(procesar_finanzas, axis=1)

    df_ventas['Margen_Neto_%'] = np.where(
        df_ventas['Total'].astype(str).str.replace(',', '.').pipe(pd.to_numeric, errors='coerce').fillna(0) > 0,
        (
            df_ventas['Margen_Neto_$'] /
            df_ventas['Total'].astype(str).str.replace(',', '.').pipe(pd.to_numeric, errors='coerce').fillna(1)
            * 100
        ).round(1),
        0
    )

    # -------------------------------------------------------
    # 7. REORDENAMIENTO FINAL
    #    ✅ FIX: Costo_MO_$ y Pedidos_en_Turno van DESPUÉS de Margen_Neto_%
    # -------------------------------------------------------
    columnas_al_final = [
        'Costo_Total_Venta',
        'Comision_PeYa_$',
        'Comision_Tienda_Online_$',
        'Margen_Neto_$',
        'Margen_Neto_%',
        'Costo_MO_$',          # ← después de Margen_Neto_%
        'Pedidos_en_Turno',    # ← después de Margen_Neto_%
    ]
    columnas_principales = [c for c in df_ventas.columns if c not in columnas_al_final]
    df_final = df_ventas[columnas_principales + columnas_al_final].copy()

    # -------------------------------------------------------
    # 8. LIMPIEZA DE DECIMALES
    # -------------------------------------------------------
    df_final = df_final.replace([np.nan, np.inf, -np.inf], 0)

    cols_enteras = [
        'Costo_Total_Venta',
        'Costo_MO_$',
        'Pedidos_en_Turno',
        'Comision_PeYa_$',
        'Comision_Tienda_Online_$',
        'Margen_Neto_$'
    ]
    for col in cols_enteras:
        if col in df_final.columns:
            df_final[col] = (
                pd.to_numeric(df_final[col], errors='coerce')
                .fillna(0)
                .round(0)
                .astype(int)
                .astype(str)
            )

    if 'Margen_Neto_%' in df_final.columns:
        def formatear_pct(x):
            val = pd.to_numeric(x, errors='coerce')
            if pd.isna(val):
                return '0'
            val = round(val, 1)
            return str(int(val)) if val == int(val) else str(val)
        df_final['Margen_Neto_%'] = df_final['Margen_Neto_%'].apply(formatear_pct)

    # -------------------------------------------------------
    # 9. SUBIR A GOOGLE SHEETS
    # -------------------------------------------------------
    print("6. Actualizando Hoja 1 con mano de obra y márgenes...")
    datos_subir = [df_final.columns.tolist()] + df_final.astype(str).values.tolist()

    sheet_ventas.clear()
    sheet_ventas.update(values=datos_subir, range_name='A1')

    print(f"✅ ¡Proceso completado!")
    print(f"   Columnas finales: {', '.join(columnas_al_final)}")


if __name__ == "__main__":
    calcular_margen_detallado_big_salads()
