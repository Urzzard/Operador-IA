from flask import Flask, request, send_file, jsonify
from google.cloud import texttospeech
import os
import io
import hashlib

app = Flask(__name__)

# Configurar credenciales de Google Cloud
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/app/credentials/gemini-tts.json'

# Inicializar cliente de Google TTS
client = texttospeech.TextToSpeechClient()

# Cache para archivos generados
audio_cache = {}

print("✅ Servidor de Gemini TTS iniciado", flush=True)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "gemini-tts"})

@app.route('/synthesize', methods=['POST'])
def synthesize():
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        print(f"🎤 Generando audio para: {text[:50]}...", flush=True)
        
        # Generar hash del texto para cache
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Verificar si ya existe en cache
        if text_hash in audio_cache:
            print(f"📦 Usando audio cacheado", flush=True)
            return send_file(
                io.BytesIO(audio_cache[text_hash]),
                mimetype='audio/mp3',
                as_attachment=False,
                download_name='speech.mp3'
            )
        
        # Configurar el texto de entrada
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Configurar la voz (español latinoamericano, femenina, neural)
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-US",  # Español latinoamericano
            name="es-US-Neural2-A",  # Voz femenina neural de alta calidad
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
        )

        # Configurar el audio de salida
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,  # Velocidad normal
            pitch=0.0           # Tono normal
        )
        
        # Generar el audio
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        # Guardar en cache
        audio_cache[text_hash] = response.audio_content
        
        print(f"✅ Audio generado exitosamente ({len(response.audio_content)} bytes)", flush=True)
        
        # Devolver el audio
        return send_file(
            io.BytesIO(response.audio_content),
            mimetype='audio/mp3',
            as_attachment=False,
            download_name='speech.mp3'
        )
        
    except Exception as e:
        print(f"❌ Error generando audio: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)