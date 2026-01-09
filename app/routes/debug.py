from flask import Blueprint, jsonify, current_app
import os

bp = Blueprint('debug', __name__, url_prefix='/api/debug')

@bp.route('/files', methods=['GET'])
def list_files():
    try:
        # Check static uploads
        base_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'recordings')
        
        if not os.path.exists(base_dir):
            return jsonify({
                "error": "Recordings directory does not exist",
                "base_dir": base_dir,
                "exists": False
            })
            
        structure = {}
        for root, dirs, files in os.walk(base_dir):
            rel_path = os.path.relpath(root, base_dir)
            file_list = []
            for f in files:
                file_path = os.path.join(root, f)
                size = os.path.getsize(file_path)
                file_list.append(f"{f} ({size} bytes)")
            structure[rel_path] = file_list
            
        return jsonify({
            "base_dir": base_dir,
            "exists": True,
            "structure": structure
        })
    except Exception as e:
        return jsonify({"error": str(e)})
