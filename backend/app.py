from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os
import tempfile
import base64

STATIC_DIR = '/app/frontend'

app = Flask(__name__, static_folder=STATIC_DIR)
CORS(app)


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()

    if not data or "messages" not in data:
        return jsonify({"error": "No se proporcionó un historial de mensajes."}), 400

    messages_history = data["messages"]

    try:
        response = requests.post(
            "http://ollama:11434/api/chat",
            json={
                "model": "phi4-mini",
                "messages": messages_history,
                "stream": False
            },
            timeout=60
        )
        response.raise_for_status()

        respuesta_json = response.json()
        
        respuesta_texto = respuesta_json.get("message", {}).get("content", "No se recibió contenido del modelo.")
        
        return jsonify({"respuesta": respuesta_texto})

    except requests.exceptions.RequestException as e:
        print(f"Error de conexión con Ollama: {e}")
        return jsonify({"error": f"Error de comunicación con el modelo: {e}"}), 503
    except Exception as e:
        print(f"Error inesperado: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route("/transcribe", methods=["POST"])
def transcribe():
    if 'audio' not in request.files:
        return jsonify({"error": "No se encontró ningún archivo de audio"}), 400
    
    audio_file = request.files['audio']
    
    # Guardar temporalmente el archivo
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.webm')
    try:
        audio_file.save(temp_file.name)
        temp_file.close()
        
        # Abrir el archivo y enviarlo
        with open(temp_file.name, 'rb') as f:
            files = {
                'audio_file': ('audio.webm', f, 'audio/webm')
            }
            
            params = {
                'task': 'transcribe',
                'language': 'es',
                'output': 'json'
            }
            
            whisper_url = "http://whisper:9000/asr"
            print(f"Enviando solicitud a Whisper: {whisper_url}")
            
            whisper_response = requests.post(
                whisper_url, 
                files=files, 
                params=params,
                timeout=30
            )
            
            print(f"Respuesta de Whisper: Status {whisper_response.status_code}")
            print(f"Contenido: {whisper_response.text}")
            
            whisper_response.raise_for_status()
            
            transcription = whisper_response.json()
            text = transcription.get("text", "").strip()
            
            return jsonify({"text": text})
            
    except requests.exceptions.RequestException as e:
        print(f"Error de conexión con Whisper: {e}")
        return jsonify({"error": f"Error al transcribir: {str(e)}"}), 500
    except Exception as e:
        print(f"Error inesperado en /transcribe: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        # Limpiar archivo temporal
        try:
            os.unlink(temp_file.name)
        except:
            pass


@app.route("/tts", methods=["POST"])
def text_to_speech():
    data = request.get_json()
    
    if not data or "text" not in data:
        return jsonify({"error": "No se proporcionó texto"}), 400
    
    text = data["text"]
    
    try:
        # Coqui TTS usa la ruta /api/tts con método GET y parámetro text
        tts_url = "http://tts:5002/api/tts"
        
        print(f"Enviando solicitud a Coqui TTS: {tts_url}")
        print(f"Texto: {text}")
        
        response = requests.get(
            tts_url,
            params={"text": text},
            timeout=60  # Coqui puede tardar más en generar
        )
        
        print(f"Respuesta de TTS: Status {response.status_code}")
        
        response.raise_for_status()
        
        # El audio viene directamente en la respuesta
        import base64
        audio_base64 = base64.b64encode(response.content).decode('utf-8')
        
        return jsonify({"audio": audio_base64})
        
    except requests.exceptions.RequestException as e:
        print(f"Error de conexión con TTS: {e}")
        return jsonify({"error": f"Error al generar voz: {str(e)}"}), 500
    except Exception as e:
        print(f"Error inesperado en /tts: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)