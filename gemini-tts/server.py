from flask import Flask, request, jsonify, Response
from google.cloud import texttospeech_v1beta1 as texttospeech
from google.oauth2 import service_account
import hashlib
import re

app = Flask(__name__)

# Autenticación
credentials = service_account.Credentials.from_service_account_file(
    '/app/gemini-tts.json'
)
client = texttospeech.TextToSpeechClient(credentials=credentials)

# Cache
audio_cache = {}

print("✅ Servidor de Gemini TTS iniciado", flush=True)

@app.route('/synthesize', methods=['POST'])
def synthesize():
    """
    Genera audio usando Gemini TTS SIN prompts (más estable).
    """
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        print(f"🎤 Generando audio: {text[:50]}...", flush=True)
        
        # Sanitizar texto (evitar errores de contenido)
        text = sanitizar_texto(text)
        
        # Hash para cache
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Verificar cache
        if text_hash in audio_cache:
            print(f"📦 Cache", flush=True)
            return Response(
                audio_cache[text_hash],
                mimetype='audio/mpeg',
                headers={'Content-Type': 'audio/mpeg'}
            )
        
        # ✅ SIN PROMPT - Voz natural de Gemini
        synthesis_input = texttospeech.SynthesisInput(
            text=text  # ⬅️ SOLO el texto, SIN prompt
        )
        
        # Configurar voz
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-ES",
            name="Achernar",  
            model_name="gemini-2.5-flash-tts"
        )
        
        # Audio config
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            sample_rate_hertz=24000,
            speaking_rate=1.05,  # ⬆️ Ligeramente más rápido
            pitch=0.0
        )
        
        # Sintetizar
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        audio_data = response.audio_content
        
        # Cache
        audio_cache[text_hash] = audio_data
        
        print(f"✅ {len(audio_data)} bytes", flush=True)
        
        return Response(
            audio_data,
            mimetype='audio/mpeg',
            headers={'Content-Type': 'audio/mpeg'}
        )
        
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


def sanitizar_texto(text):
    """
    Limpia el texto para evitar errores de 'contenido sensible'.
    """
    # Convertir URLs a texto legible
    text = re.sub(r'https?://[^\s]+', 'ver portal del empleado', text)
    
    # Limpiar caracteres especiales que puedan causar problemas
    text = text.replace('RRHH', 'recursos humanos')
    
    # Eliminar saltos de línea múltiples
    text = re.sub(r'\n+', ' ', text)
    
    # Eliminar espacios extras
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok", 
        "service": "gemini-tts",
        "model": "gemini-2.5-flash-tts",
        "voice": "Achernar"
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)