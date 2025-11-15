import pandas as pd
from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

class CallManager:
    def __init__(self):
        self.client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        self.twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
        self.empleados = self.cargar_empleados()
    
    def cargar_empleados(self):
        """Carga la lista de empleados desde CSV"""
        try:
            df = pd.read_csv('/app/data/empleados.csv')
            df['telefono'] = df['telefono'].astype(str).str.strip()
            return df.to_dict('records')
        except Exception as e:
            print(f"Error cargando empleados: {e}")
            return []
    
    def obtener_empleado_por_telefono(self, telefono):
        """Busca un empleado por su número de teléfono"""
        for emp in self.empleados:
            if emp['telefono'] == telefono:
                return emp
        return None
    
    def iniciar_llamada(self, empleado):
        """Inicia una llamada a un empleado"""
        try:
            # URL del webhook que manejará la conversación
            webhook_url = f"{os.getenv('WEBHOOK_BASE_URL')}/twilio-webhook"
            
            call = self.client.calls.create(
                to=empleado['telefono'],
                from_=self.twilio_number,
                url=webhook_url,
                status_callback=f"{os.getenv('WEBHOOK_BASE_URL')}/call-status",
                status_callback_event=['initiated', 'ringing', 'answered', 'completed']
            )
            
            print(f"✅ Llamada iniciada a {empleado['nombre']}: {call.sid}")
            return call.sid
        
        except Exception as e:
            print(f"❌ Error al iniciar llamada: {e}")
            return None