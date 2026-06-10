"""File Integrity Monitor — production entry (Render/Railway)"""
from app import app

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5004))
    print(f"File Integrity Monitor -> http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
