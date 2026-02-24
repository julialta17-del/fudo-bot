import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# --- CONFIGURACIÓN (GitHub Secrets) ---
MAIL_REMITENTE = "julialta17@gmail.com"
MAIL_DESTINATARIOS = ["julialta17@gmail.com"]
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
URL_DASHBOARD = "https://docs.google.com/spreadsheets/d/1uEFRm_0zEhsRGUX9PIomjUhiijxWVnCXnSMQuUJK5a8/edit"

def limpiar_dinero_pro(serie):
    """
    Versión avanzada para no perder magnitud con puntos y comas.
    """
    serie = serie.astype(str).str.replace('$', '', regex=False).str.strip()
    
    def procesar_valor(val):
        if not val or val.lower() in ['nan', 'none', '', '0']: return 0.0
        
        # Caso 1.250,50
        if '.' in val and ',' in val:
            return float(val.replace('.', '').replace(',', '.'))
        
        # Caso 1.250 (Miles sin decimales) o 1250,50 (Decimales sin miles)
        if ',' in val:
            partes = val.split(',')
            return float(val.replace(',', '.')) if len(partes[-1]) <= 2 else float(val.replace(',', ''))
        
        if '.' in val:
            partes = val.split('.')
            return float(val) if len(partes[-1]) <= 2 else float(val.replace('.', ''))
            
        try: return float(val)
        except: return 0.0

    return serie.apply(procesar_valor)

def enviar_reporte_pro(datos):
    # (Tu código de envío de email se mantiene igual...)
    mensaje = MIMEMultipart()
    mensaje["From"] = MAIL_REMITENTE
    mensaje["To"] = ", ".join(MAIL_DESTINATARIOS)
    mensaje["Subject"] = f"🥗 Big Salads Sexta: Resumen Ejecutivo - {datetime.now().strftime('%d/%m/%Y')}"
    
    # ... (Cuerpo del mensaje igual al anterior)
    mensaje.attach(MIMEText(datos['html_cuerpo'], "html"))
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(MAIL_REMITENTE, MAIL_PASSWORD)
    server.sendmail(MAIL_REMITENTE, MAIL_DESTINATARIOS, mensaje.as_string())
    server.quit()

def ejecutar():
    print("1. Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    # --- CARGA DE DATOS ---
    df_todo = pd.DataFrame(spreadsheet.worksheet("Hoja 1").get_all_records())
    df_todo.columns = df_todo.columns.str.strip()
    
    # --- LIMPIEZA DE NÚMEROS ---
    # Usamos la versión PRO para no perder decimales ni confundir miles
    df_todo['Total_Num'] = limpiar_dinero_pro(df_todo['Total'])
    # Asegúrate de que el nombre de la columna en Google Sheets sea exactamente "Margen_Neto_$"
    df_todo['Margen_Num'] = limpiar_dinero_pro(df_todo['Margen_Neto_$'])

    # --- FILTRO CRÍTICO ---
    # Solo sumamos lo que realmente es una venta (Total > 0)
    # Esto evita que los "PEDIDOS ANULADOS" ensucien la suma del margen
    df_ventas = df_todo[df_todo['Total_Num'] > 0].copy()

    total_v = df_ventas['Total_Num'].sum()
    margen_total = df_ventas['Margen_Num'].sum()
    
    # El ticket promedio ahora es real (Ventas Totales / Cantidad de Pedidos Reales)
    ticket = total_v / len(df_ventas) if len(df_ventas) > 0 else 0

    print(f"DEBUG: Filas procesadas: {len(df_todo)} | Ventas reales: {len(df_ventas)}")
    print(f"DEBUG: Margen total calculado: {margen_total}")

    # --- PREPARACIÓN DE STRINGS PARA EL EMAIL ---
    turnos_str = "".join([f"<td><strong>{k}</strong><br>{v} tkt</td>" for k, v in df_ventas['Turno'].value_counts().items()])
    
    origen_stats = df_ventas.groupby('Origen')['Total_Num'].sum()
    origen_str = ", ".join([f"{(v/total_v*100):.1f}% {k}" for k, v in origen_stats.items()]) if total_v > 0 else "N/D"

    pagos_resumen = df_ventas.groupby('Medio de Pago')['Total_Num'].sum().sort_values(ascending=False)
    pagos_str = "".join([f"<li>🔹 <strong>{i}:</strong> ${v:,.2f}</li>" for i, v in pagos_resumen.items()])
    
    df_ventas['Principal'] = df_ventas['Detalle_Productos'].astype(str).str.split(',').str[0].str.strip()
    top_html = "".join([f"<li>• {k}: <b>{v} vendidos</b></li>" for k, v in df_ventas['Principal'].value_counts().head(5).items()])

    # (Lógica de campanas se mantiene igual...)
    lista_nombres = "Sin retornos registrados."
    # ... [tu código de campanas]

    datos_finales = {
        'total_v': total_v, 
        'margen_real': margen_total, 
        'ticket': ticket,
        'turnos_str': turnos_str, 
        'origen_str': origen_str, 
        'pagos_str': pagos_str, 
        'top_html': top_html, 
        'lista_nombres': lista_nombres,
        'html_cuerpo': "" # Se llena dinámicamente si prefieres mover el HTML aquí
    }
    
    # Nota: He añadido un paso de validación. Si el margen es 0 pero hay ventas, algo anda mal en la Hoja 1.
    if margen_total == 0 and total_v > 0:
        print("⚠️ ALERTA: La suma del margen dio 0. Revisa la columna 'Margen_Neto_$' en Hoja 1.")
    
    # Para simplificar, pasamos el HTML completo como parte de datos
    # (Aquí deberías insertar el bloque HTML que ya tienes en enviar_reporte_pro)

    enviar_reporte_pro(datos_finales)
    print(f"✅ Reporte enviado. Venta: ${total_v:,.2f} | Margen: ${margen_total:,.2f}")

if __name__ == "__main__":
    ejecutar()
