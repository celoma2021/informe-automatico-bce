"""
generar_informe.py
Uso:
  python3 generar_informe.py <balance.pdf> <nosis.pdf> [<output.docx>]

Variables de entorno requeridas:
  ANTHROPIC_API_KEY   — clave de la API de Anthropic

Flujo:
  1. Extrae datos del balance y NOSIS via Claude API (extraer_pdfs.py)
  2. Calcula índices financieros
  3. Llama a Claude API para generar el texto de las 3 secciones
  4. Genera el .docx final
"""

import sys, os, json, asyncio, subprocess, tempfile, math
from pathlib import Path
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-20250514"


# ─────────────────────────────────────────────────────────────────────────────
# PASO 1: Extraer datos de los PDFs
# ─────────────────────────────────────────────────────────────────────────────
def extraer_datos_pdf(ruta_balance, ruta_nosis):
    script = Path(__file__).parent / "extraer_pdfs.py"
    env = {**os.environ}
    resultado = subprocess.run(
        ["python3", str(script), str(ruta_balance), str(ruta_nosis)],
        capture_output=True, text=True, env=env
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"Error en extraer_pdfs.py:\n{resultado.stderr}")
    return json.loads(resultado.stdout)


# ─────────────────────────────────────────────────────────────────────────────
# PASO 2: Calcular índices
# ─────────────────────────────────────────────────────────────────────────────
def safe_div(a, b, default=0):
    try:
        return round(a / b, 4) if b else default
    except:
        return default

def pct(a, b):
    """Variación porcentual de b a a"""
    if not b:
        return None
    return round((a - b) / abs(b) * 100, 1)

def calcular_indices(b):
    """b = datos del balance (dict)"""
    ac  = b.get("activo_corriente", {})
    anc = b.get("activo_no_corriente", {})
    pc  = b.get("pasivo_corriente", {})
    pnc = b.get("pasivo_no_corriente", {})

    at  = b.get("total_activo", 0)
    pt  = b.get("total_pasivo", 0)
    pn  = b.get("patrimonio_neto", 0)
    at_ant = b.get("total_activo_anterior", 0)
    pt_ant = b.get("total_pasivo_anterior", 0)
    pn_ant = b.get("patrimonio_neto_anterior", 0)

    ac_t  = ac.get("total", 0)
    pc_t  = pc.get("total", 0)
    anc_t = anc.get("total", 0)
    pnc_t = pnc.get("total", 0)
    ac_ant = b.get("activo_corriente_anterior", {}).get("total", 0)
    pc_ant = b.get("pasivo_corriente_anterior", {}).get("total", 0)

    bc  = ac.get("bienes_de_cambio", 0)
    bu  = anc.get("bienes_de_uso", 0)
    cxv = ac.get("creditos_por_ventas", 0)

    vtas  = b.get("ventas_netas", 0)
    cmv   = b.get("costo_ventas", 0)
    rb    = b.get("resultado_bruto", 0)
    gcom  = b.get("gastos_comercializacion", 0)
    gadm  = b.get("gastos_administracion", 0)
    gfin  = b.get("gastos_financieros", 0)
    recpam = b.get("recpam", 0)
    rop   = b.get("resultado_operativo", 0)
    gn    = b.get("ganancia_neta", 0)
    amort = b.get("amortizaciones", 0)
    compras = b.get("compras_periodo", 0)

    vtas_ant = b.get("ventas_netas_anterior", 0)
    cmv_ant  = b.get("costo_ventas_anterior", 0)
    rb_ant   = b.get("resultado_bruto_anterior", 0)
    gcom_ant = b.get("gastos_comercializacion_anterior", 0)
    gadm_ant = b.get("gastos_administracion_anterior", 0)
    rop_ant  = b.get("resultado_operativo_anterior", 0)
    gn_ant   = b.get("ganancia_neta_anterior", 0)

    # Patrimoniales
    solvencia       = safe_div(at, pt)
    endeudamiento   = safe_div(pt, pn)
    end_diferido    = safe_div(pnc_t, pn)
    inmovilizacion  = safe_div(bu, pn)
    financiamiento_propio = safe_div(pn, at) * 100

    # Financieros
    liquidez_corriente = safe_div(ac_t, pc_t)
    liquidez_acida     = safe_div(ac_t - bc, pc_t)
    capital_trabajo    = ac_t - pc_t

    # Rotaciones
    rotacion_bc   = safe_div(bc * 365, cmv) if cmv else 0
    rotacion_cxv  = safe_div(cxv * 365, vtas) if vtas else 0
    rotacion_prov = safe_div(pc.get("deudas_comerciales", 0) * 365, compras) if compras else 0

    # Económicos
    margen_bruto       = safe_div(rb, vtas) * 100
    margen_bruto_ant   = safe_div(rb_ant, vtas_ant) * 100
    margen_operativo   = safe_div(rop, vtas) * 100
    margen_operativo_ant = safe_div(rop_ant, vtas_ant) * 100
    margen_neto        = safe_div(gn, vtas) * 100
    margen_neto_ant    = safe_div(gn_ant, vtas_ant) * 100
    rent_activo        = safe_div(gn, at) * 100
    rent_pn            = safe_div(gn, pn) * 100

    # EBITDA
    ebitda = rop + amort
    ebitda_sobre_ventas = safe_div(ebitda, vtas) * 100

    # Variaciones
    var_ac    = pct(ac_t, ac_ant)
    var_at    = pct(at, at_ant)
    var_pt    = pct(pt, pt_ant)
    var_pn    = pct(pn, pn_ant)
    var_pc    = pct(pc_t, pc_ant)
    var_vtas  = pct(vtas, vtas_ant)
    var_rb    = pct(rb, rb_ant)
    var_rop   = pct(rop, rop_ant)
    var_gn    = pct(gn, gn_ant)
    var_lc    = pct(liquidez_corriente, safe_div(ac_ant, pc_ant))
    var_bc    = pct(bc, b.get("activo_corriente_anterior", {}).get("bienes_de_cambio", 0))
    var_cxv   = pct(cxv, b.get("activo_corriente_anterior", {}).get("creditos_por_ventas", 0))
    var_bu    = pct(bu, b.get("activo_no_corriente_anterior", {}).get("bienes_de_uso", 0))
    var_dc    = pct(pc.get("deudas_comerciales",0), b.get("pasivo_corriente_anterior",{}).get("deudas_comerciales",0))
    var_db    = pct(pc.get("deudas_bancarias",0), b.get("pasivo_corriente_anterior",{}).get("deudas_bancarias",0))
    var_gcom  = pct(safe_div(gcom, vtas), safe_div(gcom_ant, vtas_ant)) if vtas_ant else None
    var_gadm  = pct(safe_div(gadm, vtas), safe_div(gadm_ant, vtas_ant)) if vtas_ant else None
    var_mb    = pct(margen_bruto, margen_bruto_ant)
    var_mo    = pct(margen_operativo, margen_operativo_ant)

    def fmt_pct(v, label=""):
        if v is None:
            return "sin dato"
        sign = "aumentó" if v > 0 else ("disminuyó" if v < 0 else "se mantuvo")
        return f"{sign} en un {abs(v):.1f}%"

    estructura = "mejoró" if var_pt is not None and var_at is not None and (var_at or 0) > (var_pt or 0) else "empeoró"

    return {
        # Ratios patrimoniales
        "solvencia": solvencia,
        "endeudamiento": endeudamiento,
        "end_diferido": end_diferido,
        "inmovilizacion": inmovilizacion,
        "financiamiento_propio_pct": round(financiamiento_propio, 1),
        # Ratios financieros
        "liquidez_corriente": liquidez_corriente,
        "liquidez_acida": liquidez_acida,
        "capital_trabajo": capital_trabajo,
        "rotacion_bc_dias": round(rotacion_bc, 0),
        "rotacion_cxv_dias": round(rotacion_cxv, 0),
        "rotacion_prov_dias": round(rotacion_prov, 0),
        # Ratios económicos
        "margen_bruto_pct": round(margen_bruto, 1),
        "margen_bruto_ant_pct": round(margen_bruto_ant, 1),
        "margen_operativo_pct": round(margen_operativo, 1),
        "margen_operativo_ant_pct": round(margen_operativo_ant, 1),
        "margen_neto_pct": round(margen_neto, 1),
        "margen_neto_ant_pct": round(margen_neto_ant, 1),
        "rent_activo_pct": round(rent_activo, 1),
        "rent_pn_pct": round(rent_pn, 1),
        "ebitda": round(ebitda, 0),
        "ebitda_sobre_ventas_pct": round(ebitda_sobre_ventas, 1),
        # Variaciones
        "var_ac": var_ac, "var_at": var_at, "var_pt": var_pt, "var_pn": var_pn,
        "var_pc": var_pc, "var_vtas": var_vtas, "var_rb": var_rb,
        "var_rop": var_rop, "var_gn": var_gn, "var_lc": var_lc,
        "var_bc": var_bc, "var_cxv": var_cxv, "var_bu": var_bu,
        "var_dc": var_dc, "var_db": var_db,
        "var_gcom": var_gcom, "var_gadm": var_gadm,
        "var_mb": var_mb, "var_mo": var_mo,
        "estructura_financiamiento": estructura,
        # Promedio mensual ventas
        "promedio_mensual_ventas": round(b.get("ventas_netas", 0) / 12, 0),
        # RECPAM sobre ventas
        "recpam_sobre_ventas_pct": round(safe_div(abs(recpam), b.get("ventas_netas",0)) * 100, 1),
        # Gasto financiero sobre ventas
        "gfin_sobre_ventas_pct": round(safe_div(abs(gfin), b.get("ventas_netas",0)) * 100, 1),
        "gcom_sobre_ventas_pct": round(safe_div(gcom, b.get("ventas_netas",0)) * 100, 1),
        "gadm_sobre_ventas_pct": round(safe_div(gadm, b.get("ventas_netas",0)) * 100, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PASO 3: Generar texto con Claude API
# ─────────────────────────────────────────────────────────────────────────────
def llamar_api(prompt, max_tokens=3000):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Falta la variable de entorno ANTHROPIC_API_KEY")

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
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


def generar_texto_informe(datos_completos):
    b  = datos_completos["balance"]
    n  = datos_completos["nosis"]
    ix = datos_completos["indices"]

    prompt = f"""Sos un analista de crédito del Banco de la Nación Argentina. 
Generá el texto de las tres secciones de un informe BCE (Balance) en base a los datos numéricos que te proveo.

DATOS DEL BALANCE:
{json.dumps(b, ensure_ascii=False, indent=2)}

DATOS DE NOSIS:
{json.dumps(n, ensure_ascii=False, indent=2)}

ÍNDICES CALCULADOS:
{json.dumps(ix, ensure_ascii=False, indent=2)}

INSTRUCCIONES GENERALES:
- Estilo formal, técnico, tercera persona, párrafos corridos sin subtítulos internos
- Mencioná cifras en miles de pesos con el signo $ y punto como separador de miles (ej: $1.234.567)
- Expresá porcentajes con un decimal (ej: 18.8%)
- Usá los índices calculados exactamente como se proveen, no los recalcules
- Cuando una variación no tiene dato (null), no la menciones
- Al mencionar una mejora/empeoramiento, usá frases como "aumentó en un X%", "disminuyó en un X%"
- Estructura: cada sección debe ser UN párrafo largo y continuo (no sub-párrafos separados)

CRITERIOS DE CALIFICACIÓN BNA:
- Patrimonial: BUENA (solvencia >1.5), REGULAR (1.1-1.5), COMPROMETIDA (<1.1)
- Financiera: BUENA (liquidez corriente >1.5), REGULAR (1.0-1.5), COMPROMETIDA (<1.0)
- Económica: BUENA (margen neto >10%), REGULAR (3-10%), AJUSTADA (0-3%), INSUFICIENTE (<0)

Devolvé ÚNICAMENTE este JSON sin texto adicional ni backticks:
{{
  "patrimonial_calificacion": "BUENA|REGULAR|COMPROMETIDA",
  "patrimonial_texto": "párrafo completo...",
  "financiera_calificacion": "BUENA|REGULAR|COMPROMETIDA",
  "financiera_texto": "párrafo completo...",
  "economica_calificacion": "BUENA|REGULAR|AJUSTADA|INSUFICIENTE",
  "economica_texto": "párrafo completo..."
}}

CONTENIDO MÍNIMO REQUERIDO POR SECCIÓN:

PATRIMONIAL: índice de solvencia (valor y descripción), endeudamiento total (valor), porcentaje financiado con recursos propios, variación del activo corriente con sus principales componentes, variación de bienes de uso, variación del pasivo corriente con sus principales componentes, conclusión sobre si mejoró/empeoró la estructura de financiamiento, cobertura de activos fijos con PN, datos de NOSIS (SRT, empleados, endeudamiento BCRA actual vs cierre de ejercicio con variación real deflactada).

FINANCIERA: liquidez corriente (valor e interpretación), liquidez ácida (valor e interpretación y dependencia de bienes de cambio), Score NOSIS y endeudamiento BCRA con situación, compromisos mensuales y su % sobre ventas promedio, cheques rechazados y deuda previsional, variación horizontal de liquidez respecto ejercicio anterior.

ECONÓMICA: variación de ventas, margen bruto (actual vs anterior), variación del resultado bruto, promedio mensual de ventas del ejercicio, gastos de comercialización (% sobre ventas y variación), gastos de administración (% sobre ventas y variación), gastos financieros (% sobre ventas), EBITDA (monto y % sobre ventas), RECPAM (% sobre ventas), variación del resultado operativo, resultado neto del ejercicio (monto y margen actual vs anterior), rentabilidades (sobre ventas, activo, PN).
"""

    return llamar_api(prompt, max_tokens=3000)


# ─────────────────────────────────────────────────────────────────────────────
# PASO 4: Generar el .docx
# ─────────────────────────────────────────────────────────────────────────────
def generar_docx(datos, textos, ruta_output):
    b = datos["balance"]
    n = datos["nosis"]

    razon_social = b.get("razon_social", "")
    cuit         = b.get("cuit", "").replace("-", "")
    if len(cuit) == 11:
        cuit = f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}"
    else:
        cuit = b.get("cuit", "")
    domicilio    = b.get("domicilio", "")
    actividad    = b.get("actividad", "")
    fecha_cierre = b.get("fecha_cierre", "")
    nro_ejercicio = b.get("nro_ejercicio", "")
    consejo      = b.get("consejo_protocolizante", "")
    auditor      = b.get("nombre_auditor", "")

    # Datos de NOSIS para encabezado
    socios = n.get("socios", [])
    socios_str = "\n".join(
        f"- {s.get('nombre','')} - CUIT: - ({round(s.get('porcentaje',0)*100) if isinstance(s.get('porcentaje'),float) else s.get('porcentaje','')}%)"
        for s in socios
    ) if socios else ""

    pat_cal = textos.get("patrimonial_calificacion", "BUENA")
    fin_cal = textos.get("financiera_calificacion", "BUENA")
    eco_cal = textos.get("economica_calificacion", "REGULAR")
    pat_txt = textos.get("patrimonial_texto", "")
    fin_txt = textos.get("financiera_texto", "")
    eco_txt = textos.get("economica_texto", "")

    def esc(s):
        return str(s).replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${").replace("\n", "\\n")

    js = f"""
const {{ Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
         AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign }} = require('docx');
const fs = require('fs');

const FUENTE = "Arial";
const SZ = 20; // 10pt

function txt(text, opts = {{}}) {{
  return new TextRun({{ text: String(text), font: FUENTE, size: opts.size || SZ,
    bold: opts.bold||false, italics: opts.italics||false, ...opts }});
}}
function par(children, opts = {{}}) {{
  return new Paragraph({{ children: Array.isArray(children)?children:[children],
    alignment: opts.align || AlignmentType.JUSTIFIED,
    spacing: {{ before: opts.before||0, after: opts.after||60, line: 240 }},
    indent: opts.indent||undefined }});
}}
function titulo(t, cal) {{
  return new Paragraph({{ children: [
    new TextRun({{ text: t + " (", font: FUENTE, size: SZ, bold: true }}),
    new TextRun({{ text: cal, font: FUENTE, size: SZ, bold: true }}),
    new TextRun({{ text: ")", font: FUENTE, size: SZ, bold: true }}),
  ], spacing: {{ before: 120, after: 60 }} }});
}}
function parrafos(texto) {{
  return texto.split('\\n').map(l=>l.trim()).filter(l=>l).map(l=>par(txt(l)));
}}

const borderNone = {{ style: BorderStyle.NONE, size: 0, color: "FFFFFF" }};
const bNone = {{ top:borderNone, bottom:borderNone, left:borderNone, right:borderNone }};
const COLOR = "D9D9D9";

const tablaHeader = new Table({{
  width: {{ size: 9360, type: WidthType.DXA }},
  columnWidths: [3500, 5860],
  borders: {{
    top:    {{ style: BorderStyle.SINGLE, size:4, color:"000000" }},
    bottom: {{ style: BorderStyle.SINGLE, size:4, color:"000000" }},
    left:   borderNone, right: borderNone,
    insideH: borderNone,
    insideV: {{ style: BorderStyle.SINGLE, size:4, color:"000000" }},
  }},
  rows: [new TableRow({{ children: [
    new TableCell({{
      width: {{ size:3500, type:WidthType.DXA }},
      shading: {{ fill:COLOR, type:ShadingType.CLEAR }},
      margins: {{ top:60, bottom:60, left:120, right:120 }},
      verticalAlign: VerticalAlign.CENTER,
      borders: bNone,
      children: [
        par(txt("CASA N° – CENTRO COMERCIAL SL", {{ size:18, bold:true }}), {{ align: AlignmentType.LEFT }}),
        par(txt("ZONAL SAN LUIS", {{ size:18, bold:true }}), {{ align: AlignmentType.LEFT }}),
      ]
    }}),
    new TableCell({{
      width: {{ size:5860, type:WidthType.DXA }},
      shading: {{ fill:COLOR, type:ShadingType.CLEAR }},
      margins: {{ top:60, bottom:60, left:120, right:120 }},
      verticalAlign: VerticalAlign.CENTER,
      borders: bNone,
      children: [
        par(txt("CONCLUSIONES QUE SURGEN DEL ESTUDIO", {{ size:18, bold:true }}), {{ align: AlignmentType.CENTER }}),
        par(txt("{esc(razon_social)}", {{ size:22, bold:true }}), {{ align: AlignmentType.CENTER }}),
        par(txt("{esc(cuit)}", {{ size:18 }}), {{ align: AlignmentType.CENTER }}),
      ]
    }})
  ]}})]
}});

const intro = `De los Estados Contables de la firma {esc(razon_social)}, C.U.I.T. {esc(cuit)} con domicilio legal en {esc(domicilio)}. ACTIVIDAD ECONÓMICA: {esc(actividad)}.`;
const consid = `La presente información se confecciona en base a las cifras en miles obtenidas de los Estados contables correspondientes al ejercicio cerrado el {esc(fecha_cierre)} N° {esc(str(nro_ejercicio))}, auditados por Contador Público y protocolizados por el {esc(consejo)} y demás información complementaria provista por la firma. Estimación realizada en miles.`;
const sociosLineas = `{esc(socios_str)}`.split('\\n').filter(l=>l.trim());
const pat = `{esc(pat_txt)}`;
const fin = `{esc(fin_txt)}`;
const eco = `{esc(eco_txt)}`;

const children = [
  tablaHeader,
  par(txt(""), {{ after:40 }}),
  par(txt(intro)),
  par(txt(""), {{ after:20 }}),
  par(txt("CONSIDERACIONES PREVIAS", {{ bold:true }})),
  par(txt(consid)),
  par(txt(""), {{ after:10 }}),
  par(txt("{esc(razon_social)} está compuesta por:")),
  ...sociosLineas.map(l => par(txt(l), {{ indent:{{ left:360 }} }})),
  par(txt(""), {{ after:20 }}),
  titulo("SITUACIÓN PATRIMONIAL", "{esc(pat_cal)}"),
  ...parrafos(pat),
  par(txt(""), {{ after:20 }}),
  titulo("SITUACIÓN FINANCIERA", "{esc(fin_cal)}"),
  ...parrafos(fin),
  par(txt(""), {{ after:20 }}),
  titulo("SITUACIÓN ECONÓMICA", "{esc(eco_cal)}"),
  ...parrafos(eco),
];

const doc = new Document({{
  sections: [{{
    properties: {{ page: {{
      size: {{ width:12240, height:15840 }},
      margin: {{ top:720, right:720, bottom:720, left:720 }}
    }} }},
    children
  }}]
}});

Packer.toBuffer(doc).then(buf => {{
  fs.writeFileSync("{ruta_output}", buf);
  console.log("OK:{ruta_output}");
}}).catch(err => {{ console.error("ERROR:"+err.message); process.exit(1); }});
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False, encoding='utf-8') as f:
        f.write(js)
        tmp = f.name

    try:
        r = subprocess.run(
            ['node', tmp],
            capture_output=True, text=True,
            env={**os.environ, 'NODE_PATH': '/home/claude/.npm-global/lib/node_modules'}
        )
        if r.returncode != 0 or 'ERROR:' in r.stdout:
            raise RuntimeError(f"Node.js error:\n{r.stdout}\n{r.stderr}")
    finally:
        os.unlink(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print("Uso: python3 generar_informe.py <balance.pdf> <nosis.pdf> [<output.docx>]")
        print("Requiere: variable de entorno ANTHROPIC_API_KEY")
        sys.exit(1)

    ruta_balance = sys.argv[1]
    ruta_nosis   = sys.argv[2]
    ruta_output  = sys.argv[3] if len(sys.argv) > 3 else \
                   str(Path(ruta_balance).with_suffix('')) + "_INFORME_BCE.docx"

    print(f"📂 Extrayendo datos de PDFs...")
    datos = extraer_datos_pdf(ruta_balance, ruta_nosis)

    print(f"✅ Balance: {datos['balance'].get('razon_social')} — Ejercicio N° {datos['balance'].get('nro_ejercicio')}")
    print(f"✅ NOSIS:   Score {datos['nosis'].get('score')} | Endeudamiento ${datos['nosis'].get('endeudamiento_sf_actual',0):,.0f}K")

    print(f"🔢 Calculando índices...")
    datos["indices"] = calcular_indices(datos["balance"])

    print(f"🤖 Generando texto con Claude API...")
    textos = generar_texto_informe(datos)

    print(f"📝 Generando Word: {ruta_output}")
    generar_docx(datos, textos, ruta_output)

    print(f"✅ Informe generado: {ruta_output}")
    return ruta_output

if __name__ == "__main__":
    main()
