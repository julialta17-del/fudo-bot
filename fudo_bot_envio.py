import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# --- CONFIGURACIÓN ---
MAIL_REMITENTE = "julialta17@gmail.com"
MAIL_DESTINATARIOS = ["julialta17@gmail.com"]
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
URL_DASHBOARD = "https://docs.google.com/spreadsheets/d/1uEFRm_0zEhsRGUX9PIomjUhiijxWVnCXnSMQuUJK5a8/edit"

def limpiar_dinero_blindado(serie):
    """
    Elimina puntos de miles y convierte comas decimales.
    Si el valor es '1.250,50' -> '1250.50'
    Si el valor es '12376,95' -> '12376.95'
    """
    def procesar(val):
        val = str(val).replace('$', '').strip()
        if not val or val.lower() in ['nan', 'none', '0', '']:
            return 0.0
        
        # 1. Si detectamos el formato con punto y coma (1.250,50)
        if '.' in val and ',' in val:
            # Quitamos el punto (miles) y cambiamos la coma por punto (decimal)
            val = val.replace('.', '').replace(',', '.')
        
        # 2. Si solo hay una coma (12376,95)
        elif ',' in val:
            val = val.replace(',', '.')
            
        # 3. Si hay un punto, pero NO hay coma, hay que saber si es miles o decimal
        # Regla: Si hay 3 dígitos después del punto, es miles (1.250 -> 1250)
        elif '.' in val:
            partes = val.split('.')
            if len(partes[-1]) != 2: 
                val = val.replace('.', '')
        
        try:
            return float(val)
        except:
            return 0.0

    return serie.apply(procesar)

def enviar_reporte_pro(datos):
    mensaje = MIMEMultipart()
    mensaje["From"] = MAIL_REMITENTE
    mensaje["To"] = ", ".join(MAIL_DESTINATARIOS)
    mensaje["Subject"] = f"🥗 Resumen Ejecutivo: {datos['fecha']}"

    # Formateamos los números con separador de miles para el mail
    venta_fmt = "{:,.2f}".format(datos['total_v']).replace(',', 'X').replace('.', ',').replace('X', '.')
    margen_fmt = "{:,.2f}".format(datos['margen_real']).replace(',', 'X').replace('.', ',').replace('X', '.')

    cuerpo = f"""
    <html>
      <body style="font-family: Arial, sans-serif;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
            <h2 style="color: #2c3e50; text-align: center;">🥗 Big Salads Sexta</h2>
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px;">
                <p style="font-size: 18px;">💰 <strong>Ventas Totales:</strong> ${venta_fmt}</p>
                <p style="font-size: 18px; color: #27ae60;">💵 <strong>Margen Neto Real:</strong> ${margen_fmt}</p>
            </div>
            <p style="text-align: center; margin-top: 20px;">
                <a href="{URL_DASHBOARD}" style="color: #27ae60; font-weight: bold;">📊 Ver Dashboard en Drive</a>
            </p>
        </div>
      </body>
    </html>
    """
    mensaje.attach(MIMEText(cuerpo, "html"))
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(MAIL_REMITENTE, MAIL_PASSWORD)
    server.sendmail(MAIL_REMITENTE, MAIL_DESTINATARIOS, mensaje.as_string())
    server.quit()

def ejecutar():
    print("Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    client = gspread.authorize(creds)
    
    sheet = client.open("Analisis Fudo").worksheet("Hoja 1")
    
    # IMPORTANTE: Forzamos que todo se lea como texto para que Pandas no rompa los números
    df = pd.DataFrame(sheet.get_all_records(numericise_ignore=['all']))
    df.columns = df.columns.str.strip()

    # Aplicamos limpieza blindada
    df['Total_Num'] = limpiar_dinero_blindado(df['Total'])
    
    # Buscamos la columna de margen (flexible por si cambia el nombre)
    col_margen = 'Margen_Neto_$' if 'Margen_Neto_$' in df.columns else 'Margen_Neto'
    df['Margen_Num'] = limpiar_dinero_blindado(df[col_margen])

    # Filtro: solo pedidos reales
    df_ventas = df[df['Total_Num'] > 0].copy()

    total_v = df_ventas['Total_Num'].sum()
    margen_total = df_ventas['Margen_Num'].sum()

    print(f"Cálculo final -> Venta: {total_v} | Margen: {margen_total}")

    datos = {
        'total_v': total_v,
        'margen_real': margen_total,
        'fecha': datetime.now().strftime('%d/%m/%Y')
    }

    enviar_reporte_pro(datos)
    print("✅ Proceso completado.")

if __name__ == "__main__":
    ejecutar()
