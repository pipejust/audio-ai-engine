def get_base_email_html(title: str, content_html: str, preheader: str = "") -> str:
    """
    Genera el HTML base corporativo de Busco Fácil para correos electrónicos.
    
    Argumentos:
    - title: El título principal que aparece en el header del correo.
    - content_html: El contenido central a inyectar dentro de la tarjeta blanca.
    - preheader: (Opcional) Texto corto que leen los clientes de correo (Gmail/Outlook) como vista previa.
    """
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            /* Reset básico para clientes de correo */
            body, table, td, p, a {{
                font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif;
                -webkit-text-size-adjust: 100%;
                -ms-text-size-adjust: 100%;
                margin: 0;
                padding: 0;
            }}
            body {{
                background-color: #f4f7fb;
                color: #333333;
                line-height: 1.6;
            }}
            .email-wrapper {{
                width: 100%;
                background-color: #f4f7fb;
                padding: 40px 20px;
            }}
            .email-container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
            }}
            .header {{
                background-color: #054089;
                /* Degradado corporativo web */
                background: linear-gradient(135deg, #054089 0%, #074B97 100%);
                padding: 30px;
                text-align: center;
                color: white;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 700;
                letter-spacing: -0.5px;
            }}
            .content {{
                padding: 40px 30px;
                background-color: #ffffff;
            }}
            .content h2 {{
                color: #054089;
                font-size: 20px;
                margin-top: 0;
            }}
            .footer {{
                background-color: #f9fbfd;
                padding: 20px 30px;
                text-align: center;
                color: #718096;
                font-size: 13px;
                border-top: 1px solid #edf2f7;
            }}
            .btn-primary {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #2563eb;
                color: #ffffff !important;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                margin-top: 15px;
                margin-bottom: 20px;
            }}
            .btn-whatsapp {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #25D366;
                color: #ffffff !important;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                margin-top: 10px;
            }}
            .data-list {{
                margin: 20px 0;
                padding: 0;
                list-style: none;
            }}
            .data-list li {{
                padding: 10px 0;
                border-bottom: 1px solid #edf2f7;
            }}
            .data-list li:last-child {{
                border-bottom: none;
            }}
            .data-list strong {{
                color: #4a5568;
                width: 120px;
                display: inline-block;
            }}
        </style>
    </head>
    <body>
        <!-- Hidden Preheader -->
        <span style="display:none;font-size:1px;color:#333333;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
            {preheader if preheader else title}
        </span>
        
        <table class="email-wrapper" cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td align="center">
                    <table class="email-container" cellpadding="0" cellspacing="0" border="0" width="100%">
                        <!-- Header -->
                        <tr>
                            <td class="header">
                                <!-- Recomendación: Cambiar este texto por la imagen de <img src="logo.png" /> -->
                                <h1>Busco Fácil</h1> 
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td class="content">
                                {content_html}
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td class="footer">
                                <p>&copy; 2026 Busco Fácil. Todos los derechos reservados.</p>
                                <p>Este correo electrónico fue generado automáticamente, por favor no respondas a esta dirección.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
