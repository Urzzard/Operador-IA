from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os
import tempfile
import base64
from twilio.twiml.voice_response import VoiceResponse, Gather
from call_manager import CallManager
from conversation_manager import ConversationManager
import os
from dotenv import load_dotenv

load_dotenv()

call_manager = CallManager()
conversation_manager = ConversationManager()

STATIC_DIR = '/app/frontend'

app = Flask(__name__, static_folder=STATIC_DIR)
CORS(app)

import sys
sys.stdout.flush()
sys.stderr.flush()

import functools
print = functools.partial(print, flush=True)


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
            # Iniciar conversación
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


# @app.route("/twilio-webhook", methods=["POST"])
# def twilio_webhook():
#     """Webhook que maneja la llamada en tiempo real"""
#     print("=" * 50, flush=True)
#     print("WEBHOOK EJECUTADO", flush=True)
#     print("=" * 50, flush=True)
    
#     response = VoiceResponse()
    
#     # Obtener datos de la llamada
#     call_sid = request.form.get('CallSid')
#     to_number = request.form.get('To')
#     from_number = request.form.get('From')
    
#     print(f"📞 CallSid: {call_sid}", flush=True)
#     print(f"📞 To: {to_number}", flush=True)
#     print(f"📞 From: {from_number}", flush=True)
#     print(f"📞 Datos completos: {dict(request.form)}", flush=True)
    
#     # PRUEBA SIMPLE: Solo decir un mensaje
#     response.say("Hola, esta es una prueba. Si escuchas esto, el webhook funciona correctamente.", language='es-ES')
#     response.pause(length=2)
#     response.say("Ahora voy a colgar.", language='es-ES')
#     response.hangup()
    
#     twiml_str = str(response)
#     print(f"📤 TwiML generado:", flush=True)
#     print(twiml_str, flush=True)
#     print("=" * 50, flush=True)
    
#     return twiml_str, 200, {'Content-Type': 'text/xml'}

@app.route("/twilio-webhook", methods=["POST"])
def twilio_webhook():
    """Webhook que maneja la llamada en tiempo real"""
    print("=" * 50, flush=True)
    print("🔵 WEBHOOK INICIAL EJECUTADO", flush=True)
    print("=" * 50, flush=True)
    
    response = VoiceResponse()
    
    # Obtener datos de la llamada
    call_sid = request.form.get('CallSid')
    to_number = request.form.get('To')
    from_number = request.form.get('From')
    
    print(f"📞 CallSid: {call_sid}", flush=True)
    print(f"📞 To: {to_number}", flush=True)
    print(f"📞 From: {from_number}", flush=True)
    
    # Obtener o crear conversación
    conv = conversation_manager.obtener_conversacion(call_sid)
    
    if not conv:
        print("🆕 Primera vez - iniciando conversación", flush=True)
        # Primera vez - buscar empleado
        empleado = call_manager.obtener_empleado_por_telefono(to_number)
        
        if not empleado:
            print(f"❌ No se encontró empleado con número: {to_number}", flush=True)
            # Usar el primer empleado de la lista para testing
            empleados = call_manager.cargar_empleados()
            if empleados:
                empleado = empleados[0]
                print(f"✅ Usando empleado de prueba: {empleado['nombre']}", flush=True)
                conversation_manager.iniciar_conversacion(call_sid, empleado)
            else:
                response.say("Lo siento, no encontré tu registro. Por favor contacta con RRHH.", language='es-ES')
                response.hangup()
                return str(response), 200, {'Content-Type': 'text/xml'}
        else:
            print(f"✅ Empleado encontrado: {empleado['nombre']}", flush=True)
            conversation_manager.iniciar_conversacion(call_sid, empleado)
        
        conv = conversation_manager.obtener_conversacion(call_sid)
        mensaje = conversation_manager.obtener_mensaje_inicial(conv['empleado'])
        
        print(f"💬 Mensaje inicial: {mensaje}", flush=True)
        
        # Usar Gather para escuchar respuesta
        gather = Gather(
            input='speech',
            language='es-ES',
            timeout=10,  # Aumentado a 10 segundos
            speech_timeout='auto',
            action='/twilio-process-speech',
            method='POST'
        )
        gather.say(mensaje, language='es-ES')
        response.append(gather)
        
        # Si no responde después del timeout
        response.say("No escuché respuesta. ¿Sigues ahí?", language='es-ES')
        response.redirect('/twilio-webhook')
        
    else:
        print("⚠️ Conversación ya existe, redirigiendo...", flush=True)
        response.redirect('/twilio-process-speech')
    
    twiml_str = str(response)
    print(f"📤 TwiML generado:", flush=True)
    print(twiml_str, flush=True)
    print("=" * 50, flush=True)
    
    return twiml_str, 200, {'Content-Type': 'text/xml'}


@app.route("/twilio-process-speech", methods=["POST"])
def twilio_process_speech():
    """Procesa la respuesta del usuario"""
    print("=" * 50, flush=True)
    print("🟢 PROCESS SPEECH EJECUTADO", flush=True)
    print("=" * 50, flush=True)
    
    response = VoiceResponse()
    
    call_sid = request.form.get('CallSid')
    speech_result = request.form.get('SpeechResult', '')
    
    print(f"🎤 CallSid: {call_sid}", flush=True)
    print(f"🎤 Usuario dijo: '{speech_result}'", flush=True)
    print(f"🎤 Datos completos: {dict(request.form)}", flush=True)
    
    # Obtener conversación
    conv = conversation_manager.obtener_conversacion(call_sid)
    
    if not conv:
        print("❌ No se encontró conversación", flush=True)
        response.say("Ha ocurrido un error. Por favor contacta con RRHH.", language='es-ES')
        response.hangup()
        return str(response), 200, {'Content-Type': 'text/xml'}
    
    # Procesar respuesta
    respuesta_bot = conversation_manager.procesar_respuesta(call_sid, speech_result)
    
    print(f"🤖 Bot responde: {respuesta_bot}", flush=True)
    print(f"🤖 Etapa actual: {conv['etapa']}", flush=True)
    
    # Verificar si debemos continuar o terminar
    if conv['etapa'] == 'despedida':
        print("👋 Despedida - colgando", flush=True)
        response.say(respuesta_bot, language='es-ES')
        response.hangup()
    else:
        print("➡️ Continuando conversación", flush=True)
        # Continuar conversación
        gather = Gather(
            input='speech',
            language='es-ES',
            timeout=10,
            speech_timeout='auto',
            action='/twilio-process-speech',
            method='POST'
        )
        gather.say(respuesta_bot, language='es-ES')
        response.append(gather)
        
        # Si no responde
        response.say("¿Sigues ahí? ¿Hay algo más en lo que pueda ayudarte?", language='es-ES')
        gather2 = Gather(
            input='speech',
            language='es-ES',
            timeout=10,
            speech_timeout='auto',
            action='/twilio-process-speech',
            method='POST'
        )
        gather2.say("Si no necesitas nada más, puedes colgar.", language='es-ES')
        response.append(gather2)
        response.hangup()
    
    twiml_str = str(response)
    print(f"📤 TwiML generado:", flush=True)
    print(twiml_str, flush=True)
    print("=" * 50, flush=True)
    
    return twiml_str, 200, {'Content-Type': 'text/xml'}


@app.route("/call-status", methods=["POST"])
def call_status():
    """Recibe notificaciones de estado de llamada"""
    call_sid = request.form.get('CallSid')
    call_status = request.form.get('CallStatus')
    duration = request.form.get('CallDuration', '0')
    
    print(f"📊 Llamada {call_sid}: {call_status} (duración: {duration}s)")
    
    # Aquí podrías guardar esto en una BD
    
    return '', 200


@app.route("/listar-empleados", methods=["GET"])
def listar_empleados():
    """Lista todos los empleados disponibles"""
    empleados = call_manager.cargar_empleados()
    return jsonify({"empleados": empleados})


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)