import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURACIÓN ---
MAIL_REMITENTE = "julialta17@gmail.com"
MAIL_DESTINATARIOS = ["julialta17@gmail.com"]
MAIL_PASSWORD = "flns hgiy nwyw rzda"
URL_DASHBOARD = "https://docs.google.com/spreadsheets/d/1uEFRm_0zEhsRGUX9PIomjUhiijxWVnCXnSMQuUJK5a8/edit#gid=487122359"

def enviar_alerta_critica(titulo, mensaje_html):
    mensaje = MIMEMultipart()
    mensaje["From"] = MAIL_REMITENTE
    mensaje["To"] = ", ".join(MAIL_DESTINATARIOS)
    mensaje["Subject"] = f"🚨 ALERTA DE GESTIÓN: {titulo}"

    cuerpo_final = f"""
    <html>
      <body style="font-family: Arial, sans-serif; border: 2px solid #e74c3c; padding: 20px; border-radius: 10px;">
        <h2 style="color: #e74c3c;">⚠️ Anomalía detectada en Ventas Reales</h2>
        <p>El sistema ha detectado movimientos que requieren revisión manual:</p>
        {mensaje_html}
        <br>
        <div style="text-align: center; margin-top: 20px;">
            <a href="{URL_DASHBOARD}" style="background-color: #e74c3c; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                REVISAR DASHBOARD
            </a>
        </div>
      </body>
    </html>
    """
    mensaje.attach(MIMEText(cuerpo_final, "html"))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587); server.starttls()
        server.login(MAIL_REMITENTE, MAIL_PASSWORD)
        server.sendmail(MAIL_REMITENTE, MAIL_DESTINATARIOS, mensaje.as_string()); server.quit()
        print(f"✉️ Alerta enviada: {titulo}")
    except Exception as e: print(f"❌ Error mail: {e}")

def ejecutar_monitoreo_alertas_reales():
    print("🔍 Iniciando monitoreo de ventas reales...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope) if creds_json else Credentials.from_service_account_file('credentials.json', scopes=scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")
    sheet_ventas = spreadsheet.worksheet("Hoja 1")
    
    df = pd.DataFrame(sheet_ventas.get_all_records())
    df.columns = df.columns.str.strip()

    # --- 1. FILTRAR SOLO VENTAS REALES ---
    # Ignoramos cualquier fila que en 'Estado_Control' diga CANCELADO o BORRADO
    # O simplemente ignoramos las que tengan Total = 0
    df_reales = df[df['Total'] > 0].copy()

    if df_reales.empty:
        print("No hay ventas reales para analizar en este momento.")
        return

    alertas_html = ""

    # --- 2. CHEQUEO DE MÁRGENES NEGATIVOS ---
    negativos = df_reales[df_reales['Margen_Neto_$'] < 0]
    if not negativos.empty:
        alertas_html += f"<h3>❌ Ventas a PÉRDIDA (Margen < $0):</h3>"
        alertas_html += negativos[['Id', 'Cliente', 'Total', 'Margen_Neto_$']].to_html(index=False, border=1)

    # --- 3. CHEQUEO DE RENTABILIDAD BAJA (< 10%) ---
    baja_renta = df_reales[(df_reales['Margen_Neto_%'] < 10)]
    if not baja_renta.empty:
        alertas_html += f"<h3>⚠️ Ventas con RENTABILIDAD BAJA (< 10%):</h3>"
        alertas_html += baja_renta[['Id', 'Cliente', 'Total', 'Margen_Neto_%']].to_html(index=False, border=1)

    # --- 4. CHEQUEO DE DESCUENTOS ALTOS ---
    if 'Descuento' in df_reales.columns:
        df_reales['Descuento'] = pd.to_numeric(df_reales['Descuento'], errors='coerce').fillna(0)
        mucho_desc = df_reales[df_reales['Descuento'] > 20] 
        if not mucho_desc.empty:
            alertas_html += f"<h3>💸 Descuentos excesivos detectados (> 20%):</h3>"
            alertas_html += mucho_desc[['Id', 'Cliente', 'Total', 'Descuento']].to_html(index=False, border=1)

    # --- 5. ENVÍO DE CORREO SI HAY ALERTAS ---
    if alertas_html != "":
        enviar_alerta_critica("Anomalías en Rentabilidad", alertas_html)
        print("✅ Se encontraron anomalías y se envió el correo.")
    else:
        print("✅ Todo en orden: No se detectaron anomalías en las ventas reales.")

if __name__ == "__main__":
    ejecutar_monitoreo_alertas_reales()