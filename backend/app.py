from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from flask_sock import Sock
import requests
import os
import tempfile
import base64
import json
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from call_manager import CallManager
from conversation_manager import ConversationManager
import os
from dotenv import load_dotenv
import sys
import functools
import uuid
import io
import threading
import queue
import wave
import struct
import time

load_dotenv()

call_manager = CallManager()
conversation_manager = ConversationManager()

twilio_client = Client(
    os.getenv('TWILIO_ACCOUNT_SID'),
    os.getenv('TWILIO_AUTH_TOKEN')
)

STATIC_DIR = '/app/frontend'

app = Flask(__name__, static_folder=STATIC_DIR)
CORS(app)
sock = Sock(app)

sys.stdout.flush()
sys.stderr.flush()

print = functools.partial(print, flush=True)

# ============================================
# CONFIGURACIÓN DE AUDIO
# ============================================
SAMPLE_RATE = 8000  # Twilio usa 8kHz
CHUNK_SIZE = 160  # 20ms de audio a 8kHz
SILENCE_THRESHOLD = 700  # Umbral de silencio
SILENCE_DURATION = 1.8  # Segundos de silencio para considerar que terminó de hablar


class AudioBuffer:
    """Buffer de audio con detección de actividad de voz (VAD)"""
    def __init__(self):
        self.buffer = []
        self.silent_chunks = 0
        self.is_speaking = False
        
    def add_chunk(self, audio_bytes):
        """Agrega un chunk de audio y detecta actividad"""
        self.buffer.append(audio_bytes)
        
        # Detectar si hay voz (VAD simple)
        rms = self._calculate_rms(audio_bytes)
        
        if rms > SILENCE_THRESHOLD:
            self.is_speaking = True
            self.silent_chunks = 0
        else:
            if self.is_speaking:
                self.silent_chunks += 1
                
        return self.is_speaking
    
    def is_finished_speaking(self):
        """Detecta si la persona terminó de hablar"""
        silence_chunks_needed = int((SILENCE_DURATION * SAMPLE_RATE) / CHUNK_SIZE)
        return self.silent_chunks >= silence_chunks_needed
    
    def get_audio(self):
        """Obtiene todo el audio del buffer como WAV"""
        if not self.buffer:
            return None
            
        # Combinar todos los chunks
        audio_data = b''.join(self.buffer)
        
        # Crear WAV en memoria
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_data)
        
        wav_buffer.seek(0)
        return wav_buffer.getvalue()
    
    def clear(self):
        """Limpia el buffer"""
        self.buffer = []
        self.silent_chunks = 0
        self.is_speaking = False
    
    @staticmethod
    def _calculate_rms(audio_bytes):
        """Calcula RMS (volumen) del audio"""
        if len(audio_bytes) < 2:
            return 0
        try:
            samples = struct.unpack(f'{len(audio_bytes)//2}h', audio_bytes)
            sum_squares = sum(sample**2 for sample in samples)
            rms = (sum_squares / len(samples)) ** 0.5
            return rms
        except:
            return 0
        
def colgar_llamada(call_sid):
    """Finaliza una llamada de Twilio"""
    try:
        twilio_client.calls(call_sid).update(status='completed')
        print(f"📞 Llamada {call_sid} FINALIZADA", flush=True)
        return True
    except Exception as e:
        print(f"❌ Error colgando llamada: {e}", flush=True)
        return False


# ============================================
# RUTAS ESTÁTICAS
# ============================================

@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)


# ============================================
# ENDPOINTS DE LLAMADA
# ============================================

@app.route("/iniciar-llamada/<int:empleado_id>", methods=["POST"])
def iniciar_llamada(empleado_id):
    """Inicia una llamada a un empleado específico"""
    try:
        empleados = call_manager.cargar_empleados()
        
        if empleado_id >= len(empleados):
            return jsonify({"error": "Empleado no encontrado"}), 404
        
        empleado = empleados[empleado_id]
        call_sid = call_manager.iniciar_llamada(empleado)
        
        if call_sid:
            conversation_manager.iniciar_conversacion(call_sid, empleado)
            return jsonify({
                "success": True,
                "call_sid": call_sid,
                "empleado": empleado['nombre']
            })
        else:
            return jsonify({"error": "No se pudo iniciar la llamada"}), 500
            
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/twilio-webhook", methods=["POST"])
def twilio_webhook():
    """Webhook inicial de Twilio - Inicia Media Stream"""
    print("="*50)
    print("🔵 WEBHOOK INICIAL EJECUTADO")
    print("="*50)
    
    call_sid = request.form.get('CallSid')
    to_number = request.form.get('To')
    from_number = request.form.get('From')
    
    print(f"📞 CallSid: {call_sid}")
    print(f"📞 To: {to_number}")
    print(f"📞 From: {from_number}")
    
    response = VoiceResponse()
    
    # Conectar al WebSocket para streaming
    websocket_url = os.getenv('WEBHOOK_BASE_URL').replace('http', 'ws') + '/media'
    
    from twilio.twiml.voice_response import Connect, Stream
    connect = Connect()
    stream = connect.stream(url=websocket_url)
    stream.parameter(name='callSid', value=call_sid)
    stream.parameter(name='toNumber', value=to_number)
    
    response.append(connect)
    
    print(f"📤 TwiML generado:")
    print(str(response))
    print("="*50)
    
    return str(response), 200, {'Content-Type': 'text/xml'}


@app.route("/call-status", methods=["POST"])
def call_status():
    """Recibe notificaciones de estado de llamada"""
    call_sid = request.form.get('CallSid')
    call_status = request.form.get('CallStatus')
    duration = request.form.get('CallDuration', '0')
    
    print(f"📊 Llamada {call_sid}: {call_status} (duración: {duration}s)")
    
    return '', 200


# ============================================
# WEBSOCKET - STREAMING EN TIEMPO REAL
# ============================================

@sock.route('/media')
def media(ws):
    """
    WebSocket para streaming de audio bidireccional.
    Implementa conversación en tiempo real.
    """
    print("="*50)
    print("🟢 WEBSOCKET CONECTADO")
    print("="*50)
    
    call_sid = None
    stream_sid = None
    audio_buffer = AudioBuffer()
    empleado = None
    
    try:
        while True:
            message = ws.receive()
            
            if message is None:
                print("⚫ WebSocket cerrado")
                break
            
            data = json.loads(message)
            event = data.get('event')
            
            # ============================================
            # EVENTO: START
            # ============================================
            if event == "start":
                call_sid = data['start']['callSid']
                stream_sid = data['start']['streamSid']
                
                custom_params = data['start'].get('customParameters', {})
                to_number = custom_params.get('toNumber')
                
                print(f"🚀 Stream iniciado - CallSid: {call_sid}")
                print(f"📞 Número: {to_number}")
                
                # Obtener empleado
                empleado = call_manager.obtener_empleado_por_telefono(to_number)
                if not empleado:
                    empleado = call_manager.cargar_empleados()[0]
                
                # Iniciar conversación
                conversation_manager.iniciar_conversacion(call_sid, empleado)
                
                # Mensaje inicial
                mensaje_inicial = conversation_manager.obtener_mensaje_inicial(empleado)
                
                # Enviar mensaje inicial en streaming
                enviar_respuesta_streaming(ws, stream_sid, call_sid, mensaje_inicial)
            
            # ============================================
            # EVENTO: MEDIA (Audio entrante)
            # ============================================
            elif event == "media":
                payload = data['media']['payload']
                
                # Decodificar audio (viene en base64, formato mulaw)
                audio_bytes = base64.b64decode(payload)
                
                # Convertir mulaw a PCM
                audio_pcm = mulaw_to_pcm(audio_bytes)
                
                # Agregar al buffer
                audio_buffer.add_chunk(audio_pcm)
                
                # Detectar si terminó de hablar
                if audio_buffer.is_finished_speaking():
                    print("🎤 Usuario terminó de hablar, procesando...")
                    
                    # Obtener audio completo
                    wav_audio = audio_buffer.get_audio()
                    
                    if wav_audio:
                        # Procesar en thread separado para no bloquear
                        threading.Thread(
                            target=procesar_audio_usuario,
                            args=(ws, stream_sid, call_sid, wav_audio, empleado),
                            daemon=True
                        ).start()
                    
                    # Limpiar buffer
                    audio_buffer.clear()
            
            # ============================================
            # EVENTO: MARK (confirmación de reproducción)
            # ============================================
            elif event == "mark":
                mark_name = data['mark']['name']
                print(f"✔️ Mark recibido: {mark_name}")
            
            # ============================================
            # EVENTO: STOP
            # ============================================
            elif event == "stop":
                print(f"🔴 Stream detenido - CallSid: {call_sid}")
                break
    
    except Exception as e:
        print(f"❌ Error en WebSocket: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"🏁 WebSocket cerrado - CallSid: {call_sid}")


def procesar_audio_usuario(ws, stream_sid, call_sid, wav_audio, empleado):
    """
    Procesa el audio del usuario:
    1. Transcribe con Whisper
    2. Genera respuesta con LLM
    3. Envía audio de vuelta
    """
    try:
        # ============================================
        # 1. TRANSCRIPCIÓN (Whisper)
        # ============================================
        print("📝 Transcribiendo audio...")
        
        texto_usuario = transcribir_audio(wav_audio)
        
        if not texto_usuario or len(texto_usuario.strip()) < 2:
            print("⚠️ No se detectó texto válido")
            return
        
        print(f"🎤 Usuario dijo: '{texto_usuario}'")
        
        # ============================================
        # 2. GENERAR RESPUESTA (LLM)
        # ============================================
        print("🧠 Generando respuesta del LLM...")
        
        respuesta_bot = conversation_manager.procesar_respuesta(call_sid, texto_usuario)
        
        print(f"🤖 Bot responde: {respuesta_bot}")
        
        # ============================================
        # 3. ENVIAR RESPUESTA EN STREAMING
        # ============================================
        tiempo_inicio_audio = time.time()
        enviar_respuesta_streaming(ws, stream_sid, call_sid, respuesta_bot)
        tiempo_audio = time.time() - tiempo_inicio_audio

        if conversation_manager.conversaciones[call_sid]["etapa"] == "despedida":
            tiempo_espera = max(3, tiempo_audio + 1)
            print("👋 Despedida detectada, finalizando llamada en {tiempo_espera:.1f}...", flush=True)
            
            # Esperar a que termine el audio de despedida
            
            time.sleep(tiempo_espera)
            
            # Colgar la llamada
            colgar_llamada(call_sid)
        
    except Exception as e:
        print(f"❌ Error procesando audio: {e}")
        import traceback
        traceback.print_exc()


def enviar_respuesta_streaming(ws, stream_sid, call_sid, texto):
    """
    Convierte texto a audio y lo envía en streaming a Twilio.
    Divide textos largos en chunks para reducir latencia.
    """
    try:
        print(f"🎤 Generando TTS para: '{texto[:50]}...'")
        
        # ============================================
        # DIVIDIR TEXTO LARGO EN FRASES
        # ============================================
        import re
        
        # Dividir por puntos, pero mantener frases completas
        frases = re.split(r'(?<=[.!?])\s+', texto)
        
        # Si una frase es muy larga (>150 caracteres), dividirla por comas
        chunks = []
        for frase in frases:
            if len(frase) > 150:
                sub_frases = re.split(r'(?<=,)\s+', frase)
                chunks.extend(sub_frases)
            else:
                chunks.append(frase)
        
        print(f"📊 Dividido en {len(chunks)} chunks")
        
        # ============================================
        # GENERAR Y ENVIAR CADA CHUNK
        # ============================================
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
                
            print(f"🎤 Chunk {i+1}/{len(chunks)}: '{chunk[:40]}...'")
            
            # Generar audio para este chunk
            try:
                response = requests.post(
                    "http://gemini-tts:5003/synthesize",
                    json={"text": chunk},
                    timeout=10  # Timeout más corto para chunks pequeños
                )
                
                if response.status_code != 200:
                    print(f"❌ Error en Gemini TTS chunk {i+1}: {response.status_code}")
                    continue
                
                # Obtener audio (MP3)
                audio_mp3 = response.content
                
                # Convertir a mulaw
                audio_mulaw = mp3_to_mulaw(audio_mp3)
                
                # Enviar en chunks a Twilio
                chunk_size = 160  # 20ms de audio
                
                for j in range(0, len(audio_mulaw), chunk_size):
                    audio_chunk = audio_mulaw[j:j + chunk_size]
                    
                    payload = base64.b64encode(audio_chunk).decode('utf-8')
                    
                    message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": payload
                        }
                    }
                    
                    ws.send(json.dumps(message))
                
                print(f"✅ Chunk {i+1} enviado")
                
            except requests.Timeout:
                print(f"⏱️ Timeout en chunk {i+1}, saltando...")
                continue
        
        # Marca de finalización
        mark_message = {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {
                "name": f"finished_{call_sid}"
            }
        }
        ws.send(json.dumps(mark_message))
        
        print("✅ Audio completo enviado")
        
    except Exception as e:
        print(f"❌ Error enviando audio: {e}")
        import traceback
        traceback.print_exc()


# ============================================
# FUNCIONES DE CONVERSIÓN DE AUDIO
# ============================================

def mulaw_to_pcm(mulaw_bytes):
    """Convierte audio mulaw a PCM 16-bit"""
    try:
        import audioop
        return audioop.ulaw2lin(mulaw_bytes, 2)
    except Exception as e:
        print(f"Error en mulaw_to_pcm: {e}")
        return mulaw_bytes


def mp3_to_mulaw(mp3_bytes):
    """Convierte MP3 a mulaw para Twilio"""
    try:
        # Guardar MP3 temporal
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_mp3:
            temp_mp3.write(mp3_bytes)
            temp_mp3_path = temp_mp3.name
        
        # Convertir con ffmpeg
        temp_wav_path = temp_mp3_path.replace('.mp3', '.wav')
        temp_mulaw_path = temp_mp3_path.replace('.mp3', '.mulaw')
        
        import subprocess
        
        # MP3 → WAV (8kHz, mono)
        subprocess.run([
            'ffmpeg', '-i', temp_mp3_path,
            '-ar', '8000',
            '-ac', '1',
            '-y',
            temp_wav_path
        ], check=True, capture_output=True)
        
        # WAV → MULAW
        subprocess.run([
            'ffmpeg', '-i', temp_wav_path,
            '-ar', '8000',
            '-ac', '1',
            '-f', 'mulaw',
            '-y',
            temp_mulaw_path
        ], check=True, capture_output=True)
        
        # Leer mulaw
        with open(temp_mulaw_path, 'rb') as f:
            mulaw_data = f.read()
        
        # Limpiar archivos temporales
        os.unlink(temp_mp3_path)
        os.unlink(temp_wav_path)
        os.unlink(temp_mulaw_path)
        
        return mulaw_data
        
    except Exception as e:
        print(f"❌ Error en mp3_to_mulaw: {e}")
        import traceback
        traceback.print_exc()
        return b''


def transcribir_audio(wav_bytes):
    """Transcribe audio usando Whisper"""
    try:
        # Guardar WAV temporal
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            temp_wav.write(wav_bytes)
            temp_wav_path = temp_wav.name
        
        # Enviar a Whisper
        with open(temp_wav_path, 'rb') as f:
            files = {
                'audio_file': ('audio.wav', f, 'audio/wav')
            }
            
            params = {
                'task': 'transcribe',
                'language': 'es',
                'output': 'json'
            }
            
            response = requests.post(
                "http://whisper:9000/asr",
                files=files,
                params=params,
                timeout=30
            )
        
        # Limpiar
        os.unlink(temp_wav_path)
        
        if response.status_code == 200:
            transcription = response.json()
            texto = transcription.get("text", "").strip()

            import re

            caracteres_validos = re.compile(r'^[a-záéíóúñ\s\d.,;:¿?¡!\-\'\"]+$', re.IGNORECASE)

            if not caracteres_validos.match(texto):
                print(f"⚠️ Transcripción con caracteres inválidos: '{texto[:50]}...'")
                print("⚠️ Descartando (posible alucinación de Whisper)")
                return ""

            return texto
        else:
            print(f"❌ Error de Whisper: {response.status_code}")
            return ""
            
    except Exception as e:
        print(f"❌ Error en transcripción: {e}")
        return ""


# ============================================
# ENDPOINTS LEGACY (para compatibilidad)
# ============================================

@app.route("/chat", methods=["POST"])
def chat():
    """Endpoint legacy para chatbot web"""
    data = request.get_json()
    messages_history = data.get("messages", [])
    
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
        
        respuesta_json = response.json()
        respuesta_texto = respuesta_json.get("message", {}).get("content", "")
        
        return jsonify({"respuesta": respuesta_texto})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/listar-empleados", methods=["GET"])
def listar_empleados():
    """Lista todos los empleados"""
    empleados = call_manager.cargar_empleados()
    return jsonify({"empleados": empleados})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)