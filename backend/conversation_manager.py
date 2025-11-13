class ConversationManager:
    def __init__(self):
        # Almacena el estado de cada conversación por call_sid
        self.conversaciones = {}
        
        # Información de la empresa
        self.info_empresa = {
            "horarios": "Lunes a Viernes de 9am a 6pm, con descanso de 1pm a 2pm",
            "ubicacion": "Jirón Horacio Cachay Díaz 393, La Victoria",
            "portal": "https://peru.salesland.net:8088/salesland-autoservicios-web",
            "onboarding": "Debes acercarte a la oficina en tu fecha de inicio, en el horario correspondiente. Preséntate en recepción y serás asistido por nuestro personal de RRHH o tu Jefe de Área."
        }
    
    def iniciar_conversacion(self, call_sid, empleado):
        """Inicia una nueva conversación"""
        self.conversaciones[call_sid] = {
            "empleado": empleado,
            "etapa": "verificacion",  # verificacion, bienvenida, preguntas, despedida
            "identificado": False,
            "historial": []
        }
    
    def obtener_conversacion(self, call_sid):
        """Obtiene el estado actual de la conversación"""
        return self.conversaciones.get(call_sid)
    
    def agregar_mensaje(self, call_sid, rol, contenido):
        """Agrega un mensaje al historial"""
        if call_sid in self.conversaciones:
            self.conversaciones[call_sid]["historial"].append({
                "role": rol,
                "content": contenido
            })
    
    def generar_prompt_sistema(self, empleado):
        """Genera el prompt del sistema para el LLM"""
        return f"""Eres un asistente virtual de RRHH de SALESLAND, una empresa peruana.

Tu rol es contactar telefónicamente a nuevos empleados para:
1. VERIFICAR su identidad (nombre y DNI)
2. Darles la BIENVENIDA con entusiasmo
3. Responder PREGUNTAS sobre su incorporación

INFORMACIÓN DEL EMPLEADO:
- Nombre: {empleado['nombre']}
- DNI: {empleado['dni']}
- Puesto: {empleado['puesto']}
- Fecha de inicio: {empleado['fecha_inicio']}

INFORMACIÓN DE LA EMPRESA:
- Horarios: {self.info_empresa['horarios']}
- Ubicación: {self.info_empresa['ubicacion']}
- Portal del empleado: {self.info_empresa['portal']}
- Proceso de incorporación: {self.info_empresa['onboarding']}

INSTRUCCIONES:
1. Primero verifica la identidad: "¿Eres [Nombre]?" o "¿Podrías confirmar tu nombre y DNI?"
2. Si responde SÍ y confirma datos → Dar bienvenida efusiva y mencionar su puesto y fecha de inicio
3. Si responde NO → Disculparte amablemente y despedirte
4. Después de la bienvenida, preguntar si tiene dudas
5. Responder preguntas SOLO con la información proporcionada arriba
6. Si no sabes algo, dirígelo al portal o a presentarse en la oficina
7. Mantén un tono AMABLE, PROFESIONAL y ENTUSIASTA
8. Sé BREVE (respuestas de 2-4 oraciones máximo)

NO INVENTES información que no tengas. Si no sabes, deriva al portal o a RRHH."""

    def procesar_respuesta(self, call_sid, texto_usuario):
        """Procesa la respuesta del usuario y genera la siguiente respuesta"""
        conv = self.obtener_conversacion(call_sid)
        if not conv:
            return "Lo siento, ha ocurrido un error. Por favor, contacta con RRHH."
        
        etapa = conv["etapa"]
        empleado = conv["empleado"]
        
        # Agregar respuesta del usuario al historial
        self.agregar_mensaje(call_sid, "user", texto_usuario)
        
        # Determinar qué hacer según la etapa
        if etapa == "verificacion":
            return self.manejar_verificacion(call_sid, texto_usuario, empleado)
        elif etapa == "bienvenida":
            return self.dar_bienvenida(call_sid, empleado)
        elif etapa == "preguntas":
            return self.responder_pregunta(call_sid, texto_usuario, empleado)
        else:
            return self.despedirse(call_sid)
    
    def manejar_verificacion(self, call_sid, respuesta, empleado):
        """Maneja la verificación de identidad"""
        respuesta_lower = respuesta.lower()
        
        # Detectar confirmación
        if any(word in respuesta_lower for word in ["sí", "si", "yes", "correcto", "soy yo", empleado['nombre'].lower()]):
            self.conversaciones[call_sid]["identificado"] = True
            self.conversaciones[call_sid]["etapa"] = "bienvenida"
            return self.dar_bienvenida(call_sid, empleado)
        
        # Detectar negación
        elif any(word in respuesta_lower for word in ["no", "equivocado", "error", "incorrecto"]):
            self.conversaciones[call_sid]["etapa"] = "despedida"
            return "Lamento la confusión. Disculpa las molestias. Que tengas un buen día."
        
        # Respuesta ambigua - preguntar de nuevo
        else:
            return f"Hola, te saluda el asistente inteligente de la empresa SALESLAND, ¿podrías confirmar si tu nombre es {empleado['nombre']} y tu DNI es el {empleado['dni']}?"
    
    def dar_bienvenida(self, call_sid, empleado):
        """Da la bienvenida al empleado"""
        self.conversaciones[call_sid]["etapa"] = "preguntas"
        
        bienvenida = f"""¡Bienvenido a nuestra gran familia SALESLAND! Estamos muy felices de contar contigo como {empleado['puesto']}. 
Juntos lograremos todas tus metas. Tu fecha de inicio es el {empleado['fecha_inicio']}. 
¿Hay algo en lo que pueda ayudarte sobre tu incorporación?"""
        
        self.agregar_mensaje(call_sid, "assistant", bienvenida)
        return bienvenida
    
    def responder_pregunta(self, call_sid, pregunta, empleado):
        """Responde preguntas usando el LLM (placeholder por ahora)"""
        # Aquí integraremos Ollama después
        # Por ahora, respuestas simples
        
        pregunta_lower = pregunta.lower()
        
        if "horario" in pregunta_lower:
            respuesta = f"El horario es {self.info_empresa['horarios']}. ¿Algo más en lo que pueda ayudarte?"
        elif "ubicacion" in pregunta_lower or "dirección" in pregunta_lower or "direccion" in pregunta_lower:
            respuesta = f"La oficina está en {self.info_empresa['ubicacion']}. ¿Necesitas algo más?"
        elif "primer día" in pregunta_lower or "inicio" in pregunta_lower or "comenzar" in pregunta_lower:
            respuesta = f"{self.info_empresa['onboarding']} ¿Tienes otra pregunta?"
        elif "portal" in pregunta_lower or "sistema" in pregunta_lower:
            respuesta = f"El portal del empleado está en {self.info_empresa['portal']}. ¿Algo más?"
        elif "no" in pregunta_lower or "nada" in pregunta_lower or "todo" in pregunta_lower:
            self.conversaciones[call_sid]["etapa"] = "despedida"
            respuesta = "Perfecto. Fue un placer hablar contigo. ¡Te esperamos en tu primer día! Hasta pronto."
        else:
            respuesta = "Para información más detallada, te sugiero revisar el portal del empleado o consultar con RRHH en tu primer día. ¿Hay algo más en lo que pueda ayudarte?"
        
        self.agregar_mensaje(call_sid, "assistant", respuesta)
        return respuesta
    
    def despedirse(self, call_sid):
        """Despedida final"""
        return "Fue un gusto hablar contigo. ¡Hasta pronto!"
    
    def obtener_mensaje_inicial(self, empleado):
        """Mensaje inicial de verificación"""
        return f"Hola, habla desde SALESLAND. ¿Eres {empleado['nombre']}?"