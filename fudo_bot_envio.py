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

def limpiar_dinero(serie):
    """Normaliza formatos de moneda (1.250,50 -> 1250.50) para evitar errores de magnitud."""
    serie = serie.astype(str).str.replace('$', '', regex=False).str.strip()
    def corregir_puntos_comas(val):
        if ',' in val and '.' in val: # Estilo 1.234,56
            return val.replace('.', '').replace(',', '.')
        if ',' in val: # Estilo 1234,56
            return val.replace(',', '.')
        return val
    serie = serie.apply(corregir_puntos_comas)
    return pd.to_numeric(serie, errors='coerce').fillna(0)

def enviar_reporte_pro(datos):
    mensaje = MIMEMultipart()
    mensaje["From"] = MAIL_REMITENTE
    mensaje["To"] = ", ".join(MAIL_DESTINATARIOS)
    mensaje["Subject"] = f"🥗 Big Salads Sexta: Resumen Ejecutivo - {datetime.now().strftime('%d/%m/%Y')}"

    cuerpo = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 25px; border-radius: 10px;">
            <h2 style="color: #2c3e50; text-align: center; border-bottom: 2px solid #27ae60; padding-bottom: 10px;">🥗 Big Salads Sexta</h2>
            
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                <p style="font-size: 18px; margin: 5px 0;">💰 <strong>Ventas Totales:</strong> ${datos['total_v']:,.2f}</p>
                <p style="font-size: 18px; margin: 5px 0; color: #27ae60;">💵 <strong>Ganancia Neta (Margen real):</strong> ${datos['margen_real']:,.2f}</p>
                <p style="font-size: 12px; color: #777; margin-bottom: 10px;"><i>* Sincronizado con Hoja 1.</i></p>
                <p style="font-size: 16px; margin: 5px 0;">🎫 <strong>Ticket Promedio:</strong> ${datos['ticket']:,.2f}</p>
                <hr style="border: 0; border-top: 1px solid #ddd; margin: 15px 0;">
                <p style="margin: 5px 0;">🌐 <strong>Origen:</strong> {datos['origen_str']}</p>
            </div>

            <h3 style="color: #2c3e50; margin-bottom: 10px;">🕒 Pedidos por Turno:</h3>
            <div style="background: #f4f4f4; padding: 10px; border-radius: 5px; margin-bottom: 25px;">
                <table width="100%" style="text-align: center;">
                    <tr>{datos['turnos_str']}</tr>
                </table>
            </div>

            <h3 style="color: #2c3e50; margin-bottom: 10px;">💳 Medios de Pago:</h3>
            <ul style="list-style: none; padding-left: 0; margin-bottom: 25px;">
                {datos['pagos_str']}
            </ul>

            <h3 style="color: #27ae60; border-top: 1px solid #eee; padding-top: 15px;">🎯 Seguimiento de Campaña</h3>
            <div style="background-color: #e8f5e9; padding: 15px; border-radius: 8px;">
                {datos['lista_nombres']}
            </div>

            <h3 style="color: #2c3e50; margin-top: 25px;">🔥 Top Productos Estrella</h3>
            <ul style="list-style: none; padding-left: 0; margin: 0;">
                {datos['top_html']}
            </ul>
            
            <div style="text-align: center; margin-top: 35px;">
                <a href="{URL_DASHBOARD}" style="background-color: #27ae60; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">📊 ABRIR PLANILLA DRIVE</a>
            </div>
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
    print("1. Conectando a Google Sheets desde GitHub...")
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    # --- VENTAS ---
    df_hoy = pd.DataFrame(spreadsheet.worksheet("Hoja 1").get_all_records())
    df_hoy.columns = df_hoy.columns.str.strip()
    
    # LIMPIEZA FORZADA DE MONEDA
    df_hoy['Total_Num'] = limpiar_dinero(df_hoy['Total'])
    df_hoy['Margen_Num'] = limpiar_dinero(df_hoy['Margen_Neto_$'])

    total_v = df_hoy['Total_Num'].sum()
    margen_total = df_hoy['Margen_Num'].sum()
    ticket = total_v / len(df_hoy) if len(df_hoy) > 0 else 0

    # Turnos
    turnos_str = "".join([f"<td><strong>{k}</strong><br>{v} tkt</td>" for k, v in df_hoy['Turno'].value_counts().items()])
    
    # Origen
    origen_stats = df_hoy.groupby('Origen')['Total_Num'].sum()
    origen_str = ", ".join([f"{(v/total_v*100):.1f}% {k}" for k, v in origen_stats.items()]) if total_v > 0 else "N/D"

    # Pagos
    pagos_resumen = df_hoy.groupby('Medio de Pago')['Total_Num'].sum().sort_values(ascending=False)
    pagos_str = "".join([f"<li>🔹 <strong>{i}:</strong> ${v:,.2f}</li>" for i, v in pagos_resumen.items()])
    
    # Productos
    df_hoy['Principal'] = df_hoy['Detalle_Productos'].astype(str).str.split(',').str[0].str.strip()
    top_html = "".join([f"<li>• {k}: <b>{v} vendidos</b></li>" for k, v in df_hoy['Principal'].value_counts().head(5).items()])

    # --- CAMPANAS (Sin Ñ) ---
    lista_nombres = "Sin retornos registrados."
    try:
        sheet_cp = spreadsheet.worksheet("campanas")
        vals = sheet_cp.get_all_values()
        if len(vals) > 1:
            df_c = pd.DataFrame(vals[1:], columns=[h.strip() for h in vals[0]])
            col_res = [c for c in df_c.columns if "resultado" in c.lower()]
            col_cli = [c for c in df_c.columns if "cliente" in c.lower()]
            if col_res and col_cli:
                exitos = df_c[df_c[col_res[0]].str.contains("EXITOSA", na=False, case=False)]
                if not exitos.empty:
                    lista_nombres = "🎯 <b>Volvieron:</b> " + ", ".join(exitos[col_cli[0]].astype(str).tolist())
    except:
        lista_nombres = "Hoja de campanas no disponible."

    datos_finales = {
        'total_v': total_v, 'margen_real': margen_total, 'ticket': ticket,
        'turnos_str': turnos_str, 'origen_str': origen_str, 
        'pagos_str': pagos_str, 'top_html': top_html, 
        'lista_nombres': lista_nombres
    }
    
    enviar_reporte_pro(datos_finales)
    print("✅ Proceso de envío completado.")

if __name__ == "__main__":
    ejecutar()



