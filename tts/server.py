from flask import Flask, request, send_file
from TTS.api import TTS
import tempfile
import os

app = Flask(__name__)

# Inicializar modelo
print("Cargando modelo TTS...")
tts = TTS(model_name="tts_models/es/css10/vits", progress_bar=False, gpu=False)
print("Modelo cargado!")

@app.route('/api/tts', methods=['GET'])
def text_to_speech():
    text = request.args.get('text', '')
    
    if not text:
        return {"error": "No text provided"}, 400
    
    # Generar audio temporal
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_file.close()
    
    try:
        # Generar audio
        tts.tts_to_file(text=text, file_path=temp_file.name)
        
        # Enviar archivo
        return send_file(temp_file.name, mimetype='audio/wav')
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}, 500
    finally:
        # Limpiar después de enviar
        try:
            os.unlink(temp_file.name)
        except:
            pass

@app.route('/health', methods=['GET'])
def health():
    return {"status": "healthy"}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)