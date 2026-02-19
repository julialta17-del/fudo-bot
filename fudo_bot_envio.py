import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import numpy as np

# --- 1. CONFIGURACIÓN (Rutas relativas para GitHub) ---
ruta_excel = os.path.join("descargas", "temp_excel", "ventas.xls")
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
    if not os.path.exists(ruta_excel):
        print(f"Error: No se encontró el archivo Excel en {ruta_excel}")
        return

    print("1. Procesando datos para el reporte...")
    # Leemos ventas y adiciones del Excel descargado en el Paso 1
    df_v = pd.read_excel(ruta_excel, sheet_name='Ventas', skiprows=3)
    df_a = pd.read_excel(ruta_excel, sheet_name='Adiciones')
    df_v.columns = [str(c).strip() for c in df_v.columns]
    
    # 2. CONEXIÓN A GOOGLE (Para actualización de histórico final si es necesario)
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    else:
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    # 3. CÁLCULOS PARA EL EMAIL
    df_v['Total_Num'] = pd.to_numeric(df_v['Total'], errors='coerce').fillna(0)
    total_v = df_v['Total_Num'].sum()
    ticket_p = total_v / len(df_v) if len(df_v) > 0 else 0
    
    top_5 = df_a['Producto'].value_counts().head(5).reset_index()
    top_5.columns = ['Producto', 'Cant']
    mejor_p = top_5.iloc[0]['Producto'] if not top_5.empty else "N/A"
    
    # Cálculo de Origen
    origen_perc_str = "Sin datos"
    if 'Origen' in df_v.columns and total_v > 0:
        stats_o = df_v.groupby('Origen')['Total_Num'].sum()
        perc = (stats_o / total_v * 100).round(1)
        origen_perc_str = ", ".join([f"{v}% {i}" for i, v in perc.items()])

    # Cálculo de Medios de Pago
    pagos_str = "<li>Sin datos</li>"
    col_pago = 'Medio de Pago'
    if col_pago in df_v.columns:
        stats_p = df_v.groupby(col_pago)['Total_Num'].sum().sort_values(ascending=False)
        pagos_str = "".join([f"<li>🔹 <strong>{i}:</strong> ${v:,.2f}</li>" for i, v in stats_p.items()])

    # Enviar reporte
    print("4. Enviando correo resumen...")
    enviar_resumen_email(total_v, ticket_p, mejor_p, top_5, origen_perc_str, pagos_str)

if __name__ == "__main__":
    ejecutar_sistema_envio()

