# 3. LÓGICA DE NEGOCIO CON PANDAS
        print("Procesando lógicas de costos y descuentos...")
        
        # 1. Leer el archivo sin procesar cabeceras para buscar la fila real
        df_raw = pd.read_excel(ruta_excel, header=None)
        
        fila_cabecera = None
        # Recorremos las primeras filas para detectar dónde están 'Nombre' y 'Precio'
        for idx, row in df_raw.head(15).iterrows():
            valores_fila = [str(val).strip() for val in row.values if pd.notna(val)]
            if 'Nombre' in valores_fila and 'Precio' in valores_fila:
                fila_cabecera = idx
                break
        
        if fila_cabecera is None:
            print("❌ No se encontró la fila de cabecera automáticamente. Primeras filas:")
            print(df_raw.head(5))
            raise Exception("No se encontró la fila con las columnas del reporte de Fudo.")
            
        # 2. Volver a cargar el DataFrame usando la fila correcta como encabezado
        df = pd.read_excel(ruta_excel, header=fila_cabecera)
        
        # Limpiar espacios en blanco invisibles al principio o final de los nombres de columnas
        df.columns = df.columns.str.strip()

        # Debug: verificar nombres exactos de columnas del XLS
        print(f"   Fila de cabecera detectada: {fila_cabecera}")
        print(f"   Columnas cargadas en memoria: {df.columns.tolist()}")

        # 3. Filtrar las columnas necesarias
        df = df[['Nombre', 'Precio', 'Costo']].copy()
