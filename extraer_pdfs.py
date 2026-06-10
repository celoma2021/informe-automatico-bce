"""
extraer_pdfs.py
Extrae datos estructurados del balance (EECC) y del informe NOSIS
enviándolos a Claude API como documentos PDF.

Requiere variable de entorno: ANTHROPIC_API_KEY
"""

import sys
import os
import json
import base64
import urllib.request
import urllib.error

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-20250514"

PROMPT_BALANCE = """Sos un analista contable argentino. Analizá estos estados contables y extraé TODOS los datos numéricos y textuales listados.

Devolvé ÚNICAMENTE un objeto JSON válido, sin texto adicional, sin markdown, sin backticks.

{
  "razon_social": "",
  "cuit": "",
  "domicilio": "",
  "actividad": "",
  "fecha_cierre": "",
  "fecha_cierre_anterior": "",
  "nro_ejercicio": 0,
  "consejo_protocolizante": "",
  "nombre_auditor": "",
  "tiene_salvedades": false,
  "activo_corriente": { "caja_bancos": 0, "inversiones": 0, "creditos_por_ventas": 0, "otros_creditos": 0, "bienes_de_cambio": 0, "total": 0 },
  "activo_no_corriente": { "bienes_de_uso": 0, "inversiones_permanentes": 0, "total": 0 },
  "total_activo": 0,
  "pasivo_corriente": { "deudas_comerciales": 0, "deudas_bancarias": 0, "remuneraciones": 0, "cargas_fiscales": 0, "otras_deudas": 0, "total": 0 },
  "pasivo_no_corriente": { "deudas_bancarias": 0, "cargas_fiscales": 0, "aportes_irrevocables": 0, "total": 0 },
  "total_pasivo": 0,
  "patrimonio_neto": 0,
  "activo_corriente_anterior": { "caja_bancos": 0, "inversiones": 0, "creditos_por_ventas": 0, "otros_creditos": 0, "bienes_de_cambio": 0, "total": 0 },
  "activo_no_corriente_anterior": { "bienes_de_uso": 0, "total": 0 },
  "total_activo_anterior": 0,
  "pasivo_corriente_anterior": { "deudas_comerciales": 0, "deudas_bancarias": 0, "remuneraciones": 0, "cargas_fiscales": 0, "otras_deudas": 0, "total": 0 },
  "pasivo_no_corriente_anterior": { "total": 0 },
  "total_pasivo_anterior": 0,
  "patrimonio_neto_anterior": 0,
  "ventas_netas": 0,
  "otros_ingresos": 0,
  "costo_ventas": 0,
  "resultado_bruto": 0,
  "gastos_comercializacion": 0,
  "gastos_administracion": 0,
  "gastos_financieros": 0,
  "recpam": 0,
  "resultado_operativo": 0,
  "ganancia_neta": 0,
  "ventas_netas_anterior": 0,
  "costo_ventas_anterior": 0,
  "resultado_bruto_anterior": 0,
  "gastos_comercializacion_anterior": 0,
  "gastos_administracion_anterior": 0,
  "gastos_financieros_anterior": 0,
  "resultado_operativo_anterior": 0,
  "ganancia_neta_anterior": 0,
  "amortizaciones": 0,
  "compras_periodo": 0
}

IMPORTANTE:
- Todos los importes deben estar en MILES de pesos. Si el balance está en pesos completos, dividí cada valor por 1000.
- Si un valor no figura, usá 0.
- Para RECPAM: buscalo en gastos financieros ("Incluye RFyT" o línea separada).
- fecha_cierre formato: "DD de mes de YYYY" (ej: "31 de julio de 2025")
- nro_ejercicio: número del ejercicio (ej: 12)
- Buscá el CUIT en el informe del auditor o en la constancia de legalización.
"""

PROMPT_NOSIS = """Sos un analista crediticio argentino. Analizá este informe NOSIS y extraé los datos indicados.

Devolvé ÚNICAMENTE un objeto JSON válido, sin texto adicional, sin markdown, sin backticks.

{
  "razon_social": "",
  "cuit": "",
  "domicilio": "",
  "actividad_principal": "",
  "tipo_sociedad": "",
  "fecha_contrato_social": "",
  "score": 0,
  "resultado_cda": "",
  "endeudamiento_sf_actual": 0,
  "compromisos_mensuales": 0,
  "situacion_bcra": "",
  "tiene_cheques_rechazados": false,
  "tiene_deuda_previsional": false,
  "deuda_previsional_detalle": "",
  "srt_vigente": false,
  "srt_aseguradora": "",
  "cantidad_empleados": "",
  "entidades_deuda": [{"entidad": "", "monto": 0, "situacion": ""}],
  "consultas_ultimos_12_meses": 0,
  "socios": [{"nombre": "", "porcentaje": 0, "cargo": ""}]
}

IMPORTANTE:
- endeudamiento_sf_actual: en miles de pesos (si dice $1.087.000, devolvé 1087)
- compromisos_mensuales: en miles de pesos
- situacion_bcra: "Normal", "Con seguimiento especial", etc.
- socios: buscalos en el árbol de relaciones o en la sección SOCIEDADES
"""

def pdf_a_base64(ruta):
    with open(ruta, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")

def llamar_api(prompt, pdf_base64, max_tokens=2000):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Falta la variable de entorno ANTHROPIC_API_KEY")

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_base64
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    with urllib.request.urlopen(req) as resp:
        respuesta = json.loads(resp.read().decode("utf-8"))

    texto = respuesta["content"][0]["text"].strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(texto)

def extraer_datos(ruta_balance, ruta_nosis):
    print("  Leyendo PDFs...", file=sys.stderr)
    b64_balance = pdf_a_base64(ruta_balance)
    b64_nosis   = pdf_a_base64(ruta_nosis)

    print("  Extrayendo datos del balance (puede tardar ~20s)...", file=sys.stderr)
    datos_balance = llamar_api(PROMPT_BALANCE, b64_balance, max_tokens=2000)

    print("  Extrayendo datos de NOSIS...", file=sys.stderr)
    datos_nosis = llamar_api(PROMPT_NOSIS, b64_nosis, max_tokens=1000)

    return {"balance": datos_balance, "nosis": datos_nosis}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 extraer_pdfs.py <balance.pdf> <nosis.pdf>")
        sys.exit(1)
    resultado = extraer_datos(sys.argv[1], sys.argv[2])
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
