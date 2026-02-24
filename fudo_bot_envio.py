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
MAIL_DESTINATARIOS = ["julialta17@gmail.com", "matiasgabrielrebolledo@gmail.com"]
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
URL_DASHBOARD = "https://docs.google.com/spreadsheets/d/1uEFRm_0zEhsRGUX9PIomjUhiijxWVnCXnSMQuUJK5a8/edit"

def limpiar_dinero_pro(serie):
    """
    Específicamente diseñado para el formato: 12376,95
    Convierte la coma en punto para que Python pueda sumar correctamente.
    """
    # Convertimos a string y limpiamos espacios o símbolos $
    serie = serie.astype(str).str.replace('$', '', regex=False).str.strip()
    
    def procesar_valor(val):
        if not val or val.lower() in ['nan', 'none', '', '0']: 
            return 0.0
        
        # Si tiene punto de miles Y coma decimal (ej: 12.376,95)
        if '.' in val and ',' in val:
            return float(val.replace('.', '').replace(',', '.'))
        
        # Si tiene SOLO la coma decimal (tu ejemplo: 12376,95)
        if ',' in val:
            return float(val.replace(',', '.'))
            
        try:
            return float(val)
        except:
            return 0.0

    return serie.apply(procesar_valor)

def enviar_reporte_pro(datos):
    mensaje = MIMEMultipart()
    mensaje["From"] = MAIL_REMITENTE
    mensaje["To"] = ", ".join(MAIL_DESTINATARIOS)
    mensaje["Subject"] = f"🥗 Big Salads Sexta: Resumen Ejecutivo - {datos['fecha']}"

    cuerpo = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 25px; border-radius: 10px;">
            <h2 style="color: #2c3e50; text-align: center; border-bottom: 2px solid #27ae60; padding-bottom: 10px;">🥗 Big Salads Sexta</h2>
            <p style="text-align: center;">Datos del día: <strong>{datos['fecha']}</strong></p>
            
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                <p style="font-size: 18px; margin: 5px 0;">💰 <strong>Ventas Totales:</strong> ${datos['total_v']:,.2f}</p>
                <p style="font-size: 18px; margin: 5px 0; color: #27ae60;">💵 <strong>Margen Neto Total:</strong> ${datos['margen_real']:,.2f}</p>
                <p style="font-size: 16px; margin: 5px 0;">🎫 <strong>Ticket Promedio:</strong> ${datos['ticket']:,.2f}</p>
            </div>

            <h3 style="color: #2c3e50;">🕒 Pedidos por Turno:</h3>
            <table width="100%" style="text-align: center; background: #f4f4f4; border-radius: 5px;">
                <tr>{datos['turnos_str']}</tr>
            </table>

            <h3 style="color: #2c3e50;">💳 Medios de Pago:</h3>
            <ul>{datos['pagos_str']}</ul>
            
            <div style="text-align: center; margin-top: 35px;">
                <a href="{URL_DASHBOARD}" style="background-color: #27ae60; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">📊 ABRIR PLANILLA DRIVE</a>
            </div>
        </div>
      </body>
    </html>
    """
    mensaje.attach(MIMEText(cuerpo, "html"))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(MAIL_REMITENTE, MAIL_PASSWORD)
        server.sendmail(MAIL_REMITENTE, MAIL_DESTINATARIOS, mensaje.as_string())
        server.quit()
        print("✅ Email enviado con éxito.")
    except Exception as e:
        print(f"❌ Error al enviar mail: {e}")

def ejecutar():
    print("1. Conectando a Google Sheets...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    client = gspread.authorize(creds)
    
    # Abrimos la planilla por nombre
    spreadsheet = client.open("Analisis Fudo")
    df = pd.DataFrame(spreadsheet.worksheet("Hoja 1").get_all_records())
    df.columns = df.columns.str.strip()

    # --- LIMPIEZA Y CÁLCULOS ---
    # Usamos la nueva lógica para la coma decimal
    df['Total_Num'] = limpiar_dinero_pro(df['Total'])
    
    # IMPORTANTE: Revisa que la columna se llame exactamente así en tu Excel
    col_margen = 'Margen_Neto_$' if 'Margen_Neto_$' in df.columns else 'Margen_Neto'
    df['Margen_Num'] = limpiar_dinero_pro(df[col_margen])

    # Filtramos para no sumar pedidos anulados (Total 0)
    df_ventas = df[df['Total_Num'] > 0].copy()

    total_v = df_ventas['Total_Num'].sum()
    margen_total = df_ventas['Margen_Num'].sum()
    ticket = total_v / len(df_ventas) if len(df_ventas) > 0 else 0

    print(f"DEBUG: Venta Total: {total_v} | Margen Total: {margen_total}")

    # --- PREPARAR DATOS PARA EMAIL ---
    turnos_str = "".join([f"<td><strong>{k}</strong><br>{v} pedidos</td>" for k, v in df_ventas['Turno'].value_counts().items()])
    pagos_resumen = df_ventas.groupby('Medio de Pago')['Total_Num'].sum().sort_values(ascending=False)
    pagos_str = "".join([f"<li>🔹 <strong>{i}:</strong> ${v:,.2f}</li>" for i, v in pagos_resumen.items()])

    datos_finales = {
        'total_v': total_v,
        'margen_real': margen_total,
        'ticket': ticket,
        'fecha': datetime.now().strftime('%d/%m/%Y'),
        'turnos_str': turnos_str,
        'pagos_str': pagos_str
    }

    enviar_reporte_pro(datos_finales)

if __name__ == "__main__":
    ejecutar()
