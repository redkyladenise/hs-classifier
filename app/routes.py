from flask import Blueprint, redirect, url_for, render_template, request, jsonify, current_app
from app.services import stub
from app.services import classifier

from flask import Response
import io

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('classifier.html')

@bp.route('/about')
def about():
    return render_template('about.html')

@bp.route('/guide')
def guide():
    return render_template('guide.html')

@bp.route('/download-template')
def download_template():
    """Serves a simple CSV template for batch upload."""
    csv_content = "description\nstainless steel kitchen sink 60x45 cm\nlaptop computer 15.6 inch\n2PCE OIL PUMP ASSY\n"
    
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=batch_template.csv"}
    )

# --- API ROUTES ---

@bp.route('/classify', methods=['POST'])
def classify_single():
    data = request.get_json() or {}
    text = data.get('description', '').strip()
    
    max_chars = current_app.config.get('MAX_CHARS', 500)
    
    if not text:
        return jsonify({"error": "Description cannot be empty."}), 400
    if len(text) > max_chars:
        return jsonify({"error": f"Description exceeds {max_chars} characters."}), 400
        
    if current_app.config.get('USE_STUB'):
        result = stub.classify(text)
    else:
        result = classifier.classify(text) 
        
    return jsonify(result)

@bp.route('/classify-batch', methods=['POST'])
def classify_batch():
    data = request.get_json() or {}
    descriptions = data.get('descriptions', [])
    
    max_rows = current_app.config.get('MAX_BATCH_ROWS', 200)
    max_chars = current_app.config.get('MAX_CHARS', 500)
    
    if not isinstance(descriptions, list):
        return jsonify({"error": "Invalid format. Expected a list of descriptions."}), 400
        
    if len(descriptions) > max_rows:
        return jsonify({"error": f"Too many rows. Maximum is {max_rows}."}), 400

    results = []
    for text in descriptions:
        text_str = str(text).strip() if text is not None else ""
        
        if not text_str:
            results.append({"status": "empty", "data": None})
        elif len(text_str) > max_chars:
            results.append({"status": "too_long", "data": None})
        else:
            if current_app.config.get('USE_STUB'):
                res = stub.classify(text_str)
            else:
                res = classifier.classify(text_str)
            results.append({"status": "ok", "data": res})
    return jsonify({"results": results})