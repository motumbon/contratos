import os
import io
import json
from datetime import datetime
from dateutil import parser as dateparser

from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
import pandas as pd
from rapidfuzz import process, fuzz

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'flask_session')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB upload limit
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
Session(app)

REQUIRED_SHEET_NAME = 'DDBB'
TARGET_REP_NAME = 'PABLO YEVENES'
REP_COLUMN_CANDIDATES = [
    'KAM / Repr', 'KAM', 'Repr', 'Representante', 'KAM/Repr', 'KAM-Rep', 'Vendedor', 'Ejecutivo'
]
COLUMN_TARGETS = {
    'linea': ['Linea', 'Línea', 'Linea Comercial', 'Line'],
    'nom_cliente': ['Nom_Cliente', 'Cliente', 'Nombre Cliente', 'Cliente Nombre'],
    'n_pedido': ['Nº de pedido', 'N° de pedido', 'N de pedido', 'Pedido', 'Nro Pedido', 'Nro de pedido'],
    'denominacion': ['Denominación', 'Producto', 'Descripción', 'Denominacion'],
    'inicio_validez': ['Inicio validez', 'Inicio de validez', 'Fecha Inicio', 'Desde'],
    'fin_validez': ['Fin de validez', 'Fin validez', 'Fecha Fin', 'Hasta', 'Vencimiento'],
}

DISPLAY_NAME = {
    'linea': 'Linea',
    'nom_cliente': 'Nom_Cliente',
    'n_pedido': 'Nº de pedido',
    'denominacion': 'Denominación',
    'inicio_validez': 'Inicio validez',
    'fin_validez': 'Fin de validez',
}


def fuzzy_find_best(name_candidates, options, score_cutoff=75):
    """Return the best matching option from options for any of the name_candidates."""
    best = None
    best_score = -1
    for cand in name_candidates:
        match = process.extractOne(cand, options, scorer=fuzz.WRatio, score_cutoff=score_cutoff)
        if match is not None:
            choice, score, _ = match
            if score > best_score:
                best = choice
                best_score = score
    return best, best_score


def standardize_columns(df: pd.DataFrame) -> dict:
    """Map existing df columns to our canonical keys using fuzzy matching."""
    mapping = {}
    cols = list(df.columns.astype(str))

    # Find rep column
    rep_col, rep_score = fuzzy_find_best(REP_COLUMN_CANDIDATES, cols, score_cutoff=65)
    mapping['rep'] = rep_col

    # Find target columns
    for key, candidates in COLUMN_TARGETS.items():
        col, score = fuzzy_find_best(candidates, cols, score_cutoff=60)
        mapping[key] = col

    return mapping


def parse_date(val):
    if pd.isna(val) or (isinstance(val, str) and val.strip() == ''):
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.to_pydatetime() if isinstance(val, pd.Timestamp) else val
    try:
        return dateparser.parse(str(val), dayfirst=True)
    except Exception:
        return None


def filter_df_for_rep(df: pd.DataFrame, rep_col: str, target_name: str) -> pd.DataFrame:
    if rep_col is None or rep_col not in df.columns:
        return df.iloc[0:0]

    # Fuzzy filter rows where rep similar to target name
    def is_target(x):
        if pd.isna(x):
            return False
        s = str(x)
        score = fuzz.WRatio(s, target_name)
        return score >= 80

    return df[df[rep_col].apply(is_target)]


def prepare_records(df: pd.DataFrame, mapping: dict):
    # Build a compact DataFrame with standardized columns
    cols = {
        'linea': mapping.get('linea'),
        'nom_cliente': mapping.get('nom_cliente'),
        'n_pedido': mapping.get('n_pedido'),
        'denominacion': mapping.get('denominacion'),
        'inicio_validez': mapping.get('inicio_validez'),
        'fin_validez': mapping.get('fin_validez'),
    }

    # Select available columns
    selected = {k: v for k, v in cols.items() if v in df.columns}
    if not selected:
        return []

    slim = df[list(selected.values())].copy()
    slim.columns = [k for k in selected.keys()]

    # Parse dates
    slim['inicio_validez'] = slim['inicio_validez'].apply(parse_date) if 'inicio_validez' in slim.columns else None
    slim['fin_validez'] = slim['fin_validez'].apply(parse_date) if 'fin_validez' in slim.columns else None

    # Drop rows missing essential contract id (n_pedido) or fin_validez
    if 'n_pedido' in slim.columns:
        slim = slim[~slim['n_pedido'].isna()]

    records = []
    for _, row in slim.iterrows():
        rec = {
            'Linea': row.get('linea', None),
            'Nom_Cliente': row.get('nom_cliente', None),
            'Nº de pedido': row.get('n_pedido', None),
            'Denominación': row.get('denominacion', None),
            'Inicio de validez': row.get('inicio_validez').strftime('%Y-%m-%d') if row.get('inicio_validez') else None,
            'Fin de validez': row.get('fin_validez').strftime('%Y-%m-%d') if row.get('fin_validez') else None,
        }
        records.append(rec)
    return records


def bucket_expirations(records):
    today = datetime.today().date()
    buckets = {
        'Vencidos': 0,
        '0-30 días': 0,
        '31-60 días': 0,
        '61-90 días': 0,
        '90+ días': 0,
    }
    soonest = []
    for r in records:
        fv = r.get('Fin de validez')
        if not fv:
            continue
        try:
            d = dateparser.parse(fv).date()
        except Exception:
            continue
        delta = (d - today).days
        if delta < 0:
            buckets['Vencidos'] += 1
        elif delta <= 30:
            buckets['0-30 días'] += 1
        elif delta <= 60:
            buckets['31-60 días'] += 1
        elif delta <= 90:
            buckets['61-90 días'] += 1
        else:
            buckets['90+ días'] += 1
        soonest.append((delta, r))

    soonest = [r for _, r in sorted(soonest, key=lambda x: x[0]) if r.get('Fin de validez')]
    return buckets, soonest[:20]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío'}), 400
    if not (file.filename.lower().endswith('.xlsx') or file.filename.lower().endswith('.xls')):
        return jsonify({'error': 'Formato inválido. Cargue un Excel (.xlsx/.xls)'}), 400

    try:
        in_mem_file = io.BytesIO(file.read())
        xl = pd.ExcelFile(in_mem_file)
        sheet_name = None
        # Exact match preferred
        if REQUIRED_SHEET_NAME in xl.sheet_names:
            sheet_name = REQUIRED_SHEET_NAME
        else:
            # Fuzzy match for sheet name similar to DDBB
            sheet_name, score = process.extractOne(REQUIRED_SHEET_NAME, xl.sheet_names, scorer=fuzz.WRatio)
            if score < 70:
                return jsonify({'error': f'No se encontró la hoja "{REQUIRED_SHEET_NAME}" en el Excel.'}), 400
        df = xl.parse(sheet_name)
        if df.empty:
            return jsonify({'error': 'La hoja seleccionada está vacía'}), 400

        # Standardize columns and filter by representative
        mapping = standardize_columns(df)
        rep_col = mapping.get('rep')
        df_rep = filter_df_for_rep(df, rep_col, TARGET_REP_NAME)

        if df_rep.empty:
            return jsonify({'error': f'No se encontraron registros para "{TARGET_REP_NAME}" o similar.'}), 404

        records = prepare_records(df_rep, mapping)
        if not records:
            return jsonify({'error': 'No se pudieron identificar las columnas requeridas.'}), 400

        # Save to session as JSON
        session['records'] = records
        session.modified = True

        # Build filter options
        lineas = sorted({r.get('Linea') for r in records if r.get('Linea')})
        clientes = sorted({r.get('Nom_Cliente') for r in records if r.get('Nom_Cliente')})
        productos = sorted({r.get('Denominación') for r in records if r.get('Denominación')})

        buckets, soonest = bucket_expirations(records)

        return jsonify({
            'message': 'Archivo procesado correctamente',
            'filters': {
                'lineas': lineas,
                'clientes': clientes,
                'productos': productos
            },
            'buckets': buckets,
            'soonest': soonest,
            'count': len(records),
        })
    except Exception as e:
        return jsonify({'error': f'Error procesando el archivo: {str(e)}'}), 500


@app.route('/data', methods=['GET'])
def get_data():
    records = session.get('records', [])
    if not records:
        return jsonify({'records': [], 'count': 0})

    # Apply filters
    linea = request.args.get('linea')
    cliente = request.args.get('cliente')
    producto = request.args.get('producto')

    filtered = records
    if linea:
        filtered = [r for r in filtered if (r.get('Linea') == linea)]
    if cliente:
        filtered = [r for r in filtered if (r.get('Nom_Cliente') == cliente)]
    if producto:
        filtered = [r for r in filtered if (r.get('Denominación') == producto)]

    buckets, soonest = bucket_expirations(filtered)

    return jsonify({'records': filtered, 'count': len(filtered), 'buckets': buckets, 'soonest': soonest})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
