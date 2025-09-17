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
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB upload limit
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
    'tipo_ctto': ['Tipo Ctto', 'Tipo Contrato', 'Tipo de Contrato', 'TipoCtto', 'Tipo_Ctto'],
}

# Valid contract types to include
VALID_CONTRACT_TYPES = [
    'Acuerdo Comercial',
    'Licitacion Publica', 
    'Licitacion Privada',
    'Cotizacion',
    'Cotizacion Masiva',
    'Trato Directo'
]

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
    
    print(f"DEBUG: Available columns: {cols}")

    # Find rep column
    rep_col, rep_score = fuzzy_find_best(REP_COLUMN_CANDIDATES, cols, score_cutoff=65)
    mapping['rep'] = rep_col
    print(f"DEBUG: Rep column mapping: '{rep_col}' (score: {rep_score})")

    # Find target columns
    for key, candidates in COLUMN_TARGETS.items():
        col, score = fuzzy_find_best(candidates, cols, score_cutoff=60)
        mapping[key] = col
        print(f"DEBUG: Column '{key}' mapped to '{col}' (score: {score})")

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


def clean_text(text):
    """Clean text for better matching: strip whitespace, normalize spaces, remove special chars"""
    if pd.isna(text):
        return ""
    s = str(text).strip()
    # Normalize multiple spaces to single space
    s = ' '.join(s.split())
    # Remove common invisible characters
    s = s.replace('\xa0', ' ').replace('\u200b', '').replace('\ufeff', '')
    return s.upper()

def filter_df_for_rep(df: pd.DataFrame, rep_col: str, target_name: str) -> pd.DataFrame:
    if rep_col is None or rep_col not in df.columns:
        return df.iloc[0:0]

    target_clean = clean_text(target_name)
    
    # Fuzzy filter rows where rep similar to target name
    def is_target(x):
        if pd.isna(x):
            return False
        s_clean = clean_text(x)
        
        # Try exact match first
        if target_clean in s_clean or s_clean in target_clean:
            return True
            
        # Then fuzzy match with lower threshold
        score = fuzz.WRatio(s_clean, target_clean)
        return score >= 70  # Reduced from 80 to 70

    matches = df[df[rep_col].apply(is_target)]
    
    # Debug info: log what we found
    print(f"DEBUG: Looking for '{target_name}' (cleaned: '{target_clean}') in column '{rep_col}'")
    
    if rep_col and rep_col in df.columns:
        # Show sample of all values in the rep column
        all_values = df[rep_col].dropna().head(10).tolist()
        print(f"DEBUG: Sample values in '{rep_col}' column: {all_values}")
        
        # Show cleaned versions
        cleaned_values = [clean_text(v) for v in all_values[:5]]
        print(f"DEBUG: Sample cleaned values: {cleaned_values}")
    
    print(f"DEBUG: Found {len(matches)} matches out of {len(df)} total rows")
    if len(matches) > 0:
        sample_values = matches[rep_col].head(3).tolist()
        print(f"DEBUG: Sample matching values: {sample_values}")
    else:
        print("DEBUG: No matches found - checking why...")
        if rep_col and rep_col in df.columns:
            # Test a few values manually
            test_values = df[rep_col].dropna().head(5)
            for i, val in enumerate(test_values):
                cleaned = clean_text(val)
                exact_match = target_clean in cleaned or cleaned in target_clean
                fuzzy_score = fuzz.WRatio(cleaned, target_clean)
                print(f"DEBUG: Value {i+1}: '{val}' -> cleaned: '{cleaned}' -> exact: {exact_match}, fuzzy: {fuzzy_score}")
    
    return matches


def filter_by_contract_type(df: pd.DataFrame, tipo_ctto_col: str) -> pd.DataFrame:
    """Filter DataFrame to include only valid contract types"""
    if tipo_ctto_col is None or tipo_ctto_col not in df.columns:
        print("DEBUG: No 'Tipo Ctto' column found, including all records")
        return df
    
    print(f"DEBUG: Filtering by contract type using column '{tipo_ctto_col}'")
    
    # Show sample values in the tipo_ctto column
    sample_values = df[tipo_ctto_col].dropna().unique()[:10]
    print(f"DEBUG: Sample contract types found: {list(sample_values)}")
    
    def is_valid_contract_type(tipo):
        if pd.isna(tipo):
            return False
        tipo_clean = clean_text(str(tipo))
        
        # Check if any valid type matches (fuzzy matching)
        for valid_type in VALID_CONTRACT_TYPES:
            valid_clean = clean_text(valid_type)
            # Exact match or high fuzzy match
            if valid_clean == tipo_clean or fuzz.WRatio(tipo_clean, valid_clean) >= 85:
                return True
        return False
    
    filtered_df = df[df[tipo_ctto_col].apply(is_valid_contract_type)]
    
    print(f"DEBUG: Contract type filter: {len(filtered_df)} records kept out of {len(df)} total")
    if len(filtered_df) > 0:
        kept_types = filtered_df[tipo_ctto_col].value_counts().head(10)
        print(f"DEBUG: Kept contract types: {dict(kept_types)}")
    
    return filtered_df


def prepare_records(df: pd.DataFrame, mapping: dict):
    # Build a compact DataFrame with standardized columns
    cols = {
        'linea': mapping.get('linea'),
        'nom_cliente': mapping.get('nom_cliente'),
        'n_pedido': mapping.get('n_pedido'),
        'denominacion': mapping.get('denominacion'),
        'inicio_validez': mapping.get('inicio_validez'),
        'fin_validez': mapping.get('fin_validez'),
        'tipo_ctto': mapping.get('tipo_ctto'),
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
            'Tipo Ctto': row.get('tipo_ctto', None),
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
    
    # Group records by pedido to avoid duplicates in soonest list
    pedido_groups = {}
    
    for r in records:
        fv = r.get('Fin de validez')
        if not fv:
            continue
        try:
            d = dateparser.parse(fv).date()
        except Exception:
            continue
        delta = (d - today).days
        
        # Count all records for buckets (including duplicates by denominación)
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
        
        # For soonest list, group by pedido to avoid repetition
        pedido = r.get('Nº de pedido')
        if pedido:
            # Keep the record with the earliest expiration date for each pedido
            if pedido not in pedido_groups or delta < pedido_groups[pedido][0]:
                pedido_groups[pedido] = (delta, r)

    # Convert grouped pedidos to soonest list
    soonest = [r for _, r in sorted(pedido_groups.values(), key=lambda x: x[0]) if r.get('Fin de validez')]
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
        # Debug: show available sheets
        print(f"DEBUG: Available sheets: {xl.sheet_names}")
        
        # Exact match preferred
        if REQUIRED_SHEET_NAME in xl.sheet_names:
            sheet_name = REQUIRED_SHEET_NAME
            print(f"DEBUG: Found exact sheet match: {sheet_name}")
        else:
            # Fuzzy match for sheet name similar to DDBB
            sheet_name, score = process.extractOne(REQUIRED_SHEET_NAME, xl.sheet_names, scorer=fuzz.WRatio)
            print(f"DEBUG: Fuzzy sheet match: {sheet_name} (score: {score})")
            if score < 70:
                return jsonify({'error': f'No se encontró la hoja "{REQUIRED_SHEET_NAME}" en el Excel. Hojas disponibles: {xl.sheet_names}'}), 400
        df = xl.parse(sheet_name)
        print(f"DEBUG: Loaded sheet '{sheet_name}' with {len(df)} rows and {len(df.columns)} columns")
        if df.empty:
            return jsonify({'error': 'La hoja seleccionada está vacía'}), 400

        # Standardize columns and apply filters
        mapping = standardize_columns(df)
        
        # Filter by contract type first
        tipo_ctto_col = mapping.get('tipo_ctto')
        df_filtered = filter_by_contract_type(df, tipo_ctto_col)
        
        if df_filtered.empty:
            return jsonify({'error': 'No se encontraron contratos con tipos válidos (Acuerdo Comercial, Licitación Pública, etc.).'}), 404
        
        # Then filter by representative
        rep_col = mapping.get('rep')
        df_rep = filter_df_for_rep(df_filtered, rep_col, TARGET_REP_NAME)

        if df_rep.empty:
            return jsonify({'error': f'No se encontraron registros para "{TARGET_REP_NAME}" o similar con tipos de contrato válidos.'}), 404

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


@app.errorhandler(413)
def handle_file_too_large(e):
    # 413 Payload Too Large
    return jsonify({'error': 'El archivo excede el tamaño máximo permitido (50MB).'}), 413


@app.route('/data', methods=['GET'])
def get_data():
    records = session.get('records', [])
    if not records:
        return jsonify({'records': [], 'count': 0})

    # Apply filters - now supporting multiple values
    lineas = request.args.getlist('linea')  # Get list of values
    clientes = request.args.getlist('cliente')
    productos = request.args.getlist('producto')
    date_range = request.args.get('date_range')  # New: filter by expiration range

    filtered = records
    
    # Filter by lineas (multiple selection)
    if lineas:
        filtered = [r for r in filtered if r.get('Linea') in lineas]
    
    # Filter by clientes (multiple selection)
    if clientes:
        filtered = [r for r in filtered if r.get('Nom_Cliente') in clientes]
    
    # Filter by productos (multiple selection)
    if productos:
        filtered = [r for r in filtered if r.get('Denominación') in productos]
    
    # Filter by date range (from chart click)
    if date_range:
        filtered = filter_by_date_range(filtered, date_range)

    buckets, soonest = bucket_expirations(filtered)

    return jsonify({'records': filtered, 'count': len(filtered), 'buckets': buckets, 'soonest': soonest})


def filter_by_date_range(records, date_range):
    """Filter records by expiration date range"""
    from datetime import datetime, date
    today = date.today()
    
    filtered = []
    for r in records:
        fv = r.get('Fin de validez')
        if not fv:
            continue
        try:
            d = dateparser.parse(fv).date()
            delta = (d - today).days
            
            if date_range == 'vencidos' and delta < 0:
                filtered.append(r)
            elif date_range == '0-30' and 0 <= delta <= 30:
                filtered.append(r)
            elif date_range == '31-60' and 31 <= delta <= 60:
                filtered.append(r)
            elif date_range == '61-90' and 61 <= delta <= 90:
                filtered.append(r)
            elif date_range == '90+' and delta > 90:
                filtered.append(r)
        except Exception:
            continue
    
    return filtered


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
