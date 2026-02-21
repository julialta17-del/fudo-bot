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
MAIL_DESTINATARIOS = ["julialta17@gmail.com", "matiasgabrielrebolledo@gmail.com"]
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") 
URL_DASHBOARD = "https://docs.google.com/spreadsheets/d/1uEFRm_0zEhsRGUX9PIomjUhiijxWVnCXnSMQuUJK5a8/edit"

def enviar_reporte_pro(datos):
    mensaje = MIMEMultipart()
    mensaje["From"] = MAIL_REMITENTE
    mensaje["To"] = ", ".join(MAIL_DESTINATARIOS)
    mensaje["Subject"] = f"🥗 Big Salads Sexta: Reporte Estratégico - {datetime.now().strftime('%d/%m/%Y')}"

    cuerpo = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 25px; border-radius: 10px;">
            <h2 style="color: #2c3e50; text-align: center; border-bottom: 2px solid #27ae60; padding-bottom: 10px;">🥗 Big Salads Sexta</h2>
            
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                <p style="font-size: 16px; margin: 5px 0;">💰 <strong>Ventas Totales:</strong> ${datos['total_v']:,.2f}</p>
                <p style="font-size: 16px; margin: 5px 0; color: #27ae60;">💵 <strong>Ganancia Neta (Margen real):</strong> ${datos['margen_real']:,.2f}</p>
                <p style="font-size: 12px; color: #777; margin-bottom: 10px;"><i>* Descontado 30% comision PeYa y costos de producción (Costo_Total_Venta).</i></p>
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

            <h3 style="color: #27ae60; border-top: 1px solid #eee; padding-top: 15px;">🎯 Seguimiento de Campaña</h3>
            <div style="background-color: #e8f5e9; padding: 15px; border-radius: 8px;">
                {datos['lista_nombres']}
            </div>

            <h3 style="color: #2c3e50; margin-top: 25px;">🔥 Top Productos Estrella</h3>
            <ul style="list-style: none; padding-left: 0; margin: 0;">
                {datos['top_html']}
            </ul>
            
            <div style="text-align: center; margin-top: 35px;">
                <a href="{URL_DASHBOARD}" style="background-color: #27ae60; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">📊 ABRIR DRIVE</a>
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
    # 1. CONEXIÓN USANDO SECRETS
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open("Analisis Fudo")

    # 2. PROCESAR VENTAS
    df_hoy = pd.DataFrame(spreadsheet.worksheet("Hoja 1").get_all_records())
    df_hoy.columns = df_hoy.columns.str.strip()
    
    df_hoy['Total_Num'] = pd.to_numeric(df_hoy['Total'], errors='coerce').fillna(0)
    df_hoy['Costo_Num'] = pd.to_numeric(df_hoy.get('Costo_Total_Venta', 0), errors='coerce').fillna(0)

    # Lógica Margen Real Big Salads
    def calcular_margen(f):
        t, c = f['Total_Num'], f['Costo_Num']
        return t - c - (t * 0.3) if "pedidos ya" in str(f.get('Origen', '')).lower() else t - c
    
    df_hoy['Margen_Real'] = df_hoy.apply(calcular_margen, axis=1)
    total_v, margen_total = df_hoy['Total_Num'].sum(), df_hoy['Margen_Real'].sum()
    ticket = total_v / len(df_hoy) if len(df_hoy) > 0 else 0

    # Formateo de datos secundarios
    turnos_str = "".join([f"<td><strong>{k}</strong><br>{v} tkt</td>" for k, v in df_hoy['Turno'].value_counts().items()])
    origen_str = ", ".join([f"{v:.1f}% {k}" for k, v in (df_hoy.groupby('Origen')['Total_Num'].sum() / total_v * 100).items()])
    df_hoy['Principal'] = df_hoy['Detalle_Productos'].str.split(',').str[0].str.strip()
    top_html = "".join([f"<li style='padding:5px 0; border-bottom:1px dashed #eee;'>• {k}: <b>{v}</b></li>" for k, v in df_hoy['Principal'].value_counts().head(5).items()])
    pagos_str = "".join([f"<li>🔹 {i}: ${v:,.2f}</li>" for i, v in df_hoy.groupby('Medio de Pago')['Total_Num'].sum().sort_values(ascending=False).items()])

    # 3. PROCESAR CAMPAÑAS (LECTURA ROBUSTA)
    sheet_cp = spreadsheet.worksheet("campañas")
    vals = sheet_cp.get_all_values()
    if len(vals) > 1:
        headers = [h.strip() for h in vals[0]]
        df_c = pd.DataFrame(vals[1:], columns=headers)
        
        col_res = [c for c in df_c.columns if "resultado" in c.lower()]
        col_cli = [c for c in df_c.columns if "cliente" in c.lower()]
        
        if col_res and col_cli:
            exitos = df_c[df_c[col_res[0]].str.contains("EXITOSA", na=False, case=False)]
            lista_nombres = "🎯 <b>Volvieron:</b> " + ", ".join(exitos[col_cli[0]].tolist()) if not exitos.empty else "Sin retornos hoy."
        else:
            lista_nombres = "⚠️ Columnas de campaña no detectadas."
    else:
        lista_nombres = "Hoja de campañas vacía."

    datos_finales = {
        'total_v': total_v, 'margen_real': margen_total, 'ticket': ticket,
        'turnos_str': turnos_str, 'origen_str': origen_str, 'top_html': top_html,
        'lista_nombres': lista_nombres, 'pagos_str': pagos_str
    }
    
    enviar_reporte_pro(datos_finales)

if __name__ == "__main__":
    ejecutar()
