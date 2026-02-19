import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import numpy as np

# --- 1. CONFIGURACIÓN ---
URL_DASHBOARD = "https://docs.google.com/spreadsheets/d/1uEFRm_0zEhsRGUX9PIomjUhiijxWVnCXnSMQuUJK5a8/edit#gid=487122359"

MAIL_REMITENTE = "julialta17@gmail.com"
MAIL_DESTINATARIOS = ["julialta17@gmail.com"]
MAIL_PASSWORD = "flns hgiy nwyw rzda" 

def enviar_resumen_email(total, ticket, mejor_prod, top5_df, origen_perc_str, pagos_str):
    mensaje = MIMEMultipart()
    mensaje["From"] = MAIL_REMITENTE
    mensaje["To"] = ", ".join(MAIL_DESTINATARIOS)
    mensaje["Subject"] = f"📊 Resumen Ejecutivo - {pd.Timestamp.now().strftime('%d/%m/%Y')}"

    # Formateo de la tabla HTML para el mail
    tabla_html = top5_df.to_html(index=False, border=1, justify='left')
    tabla_html = tabla_html.replace('border="1"', 'style="border-collapse: collapse; width: 100%; font-family: sans-serif;"')
    tabla_html = tabla_html.replace('<th>', '<th style="border: 1px solid #ddd; padding: 8px; background-color: #f2f2f2; text-align: left;">')
    tabla_html = tabla_html.replace('<td>', '<td style="border: 1px solid #ddd; padding: 8px;">')

    cuerpo = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px; border-radius: 10px;">
            <h2 style="color: #2c3e50;">📊 Reporte de Ventas Diario</h2>
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px;">
                <p>💰 <strong>Ventas Totales:</strong> ${total:,.2f}</p>
                <p>💵 <strong>Ticket Promedio:</strong> ${ticket:,.2f}</p>
                <p>⭐ <strong>Producto Estrella:</strong> {mejor_prod}</p>
                <p>🌐 <strong>Origen:</strong> {origen_perc_str}</p>
                <hr style="border: 0; border-top: 1px solid #ddd;">
                <p>💳 <strong>Medios de Pago:</strong></p>
                <ul style="list-style: none; padding-left: 0;">
                    {pagos_str}
                </ul>
            </div>
            <h3>🔥 Top 5 Productos:</h3>
            {tabla_html}
            <div style="text-align: center; margin-top: 20px;">
                <a href="{URL_DASHBOARD}" style="background-color: #3498db; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">VER DASHBOARD COMPLETO</a>
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
        print("✉️ Correo enviado con éxito.")
    except Exception as e:
        print(f"❌ Error al enviar mail: {e}")

def ejecutar_sistema_envio():
    print("1. Conectando a Google Sheets para leer el Resumen...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    
    # 2. LEER DATOS DE LA HOJA RESUMEN (No del Excel)
    try:
        sheet_res = spreadsheet.worksheet("Resumen")
        data = sheet_res.get_all_values()
    except Exception as e:
        print(f"❌ Error: No se encontró la hoja 'Resumen'. {e}")
        return

    # 3. EXTRAER MÉTRICAS DESDE LAS CELDAS DEL RESUMEN
    # Asumiendo la estructura que crea el bot de análisis en el Resumen:
    # A2:A7 -> Top 5 Productos | E2:F... -> Ventas por Turno | etc.
    
    df_resumen = pd.DataFrame(data)
    
    # Top 5 Productos (A2:B7 aprox)
    top_5 = pd.DataFrame(data[2:7], columns=data[1][0:2])
    mejor_p = top_5.iloc[0, 0] if not top_5.empty else "N/A"

    # Para los totales, ticket y origen, los tomaremos de la Hoja 1 
    # (ya que el Resumen es visual y la Hoja 1 es la base limpia)
    sheet_h1 = spreadsheet.worksheet("Hoja 1")
    df_h1 = pd.DataFrame(sheet_h1.get_all_records())
    df_h1.columns = [str(c).strip() for c in df_h1.columns]

    df_h1['Total'] = pd.to_numeric(df_h1['Total'], errors='coerce').fillna(0)
    total_v = df_h1['Total'].sum()
    ticket_p = total_v / len(df_h1) if len(df_h1) > 0 else 0

    # Cálculo de Origen
    origen_perc_str = "Sin datos"
    if 'Origen' in df_h1.columns and total_v > 0:
        stats_o = df_h1.groupby('Origen')['Total'].sum()
        perc = (stats_o / total_v * 100).round(1)
        origen_perc_str = ", ".join([f"{v}% {i}" for i, v in perc.items()])

    # Cálculo de Medios de Pago
    pagos_str = "<li>Sin datos</li>"
    if 'Medio de Pago' in df_h1.columns:
        stats_p = df_h1.groupby('Medio de Pago')['Total'].sum().sort_values(ascending=False)
        pagos_str = "".join([f"<li>🔹 <strong>{i}:</strong> ${v:,.2f}</li>" for i, v in stats_p.items()])

    # Enviar reporte
    print("4. Enviando correo resumen basado en Google Sheets...")
    enviar_resumen_email(total_v, ticket_p, mejor_p, top_5, origen_perc_str, pagos_str)

if __name__ == "__main__":
    ejecutar_sistema_envio()
