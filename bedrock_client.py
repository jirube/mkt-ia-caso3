import boto3
import json
import base64
import os
import time
import random
from botocore.exceptions import ClientError
from botocore.config import Config

# Configuración de Boto3
my_config = Config(
    region_name='us-east-1',
    retries = {
        'max_attempts': 2, # Bajamos los intentos internos para controlar nosotros la espera
        'mode': 'standard'
    }
)

bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    config=my_config
)

def invoke_with_retry(model_id, body):
    """
    Intenta llamar al modelo con esperas LARGAS para cuentas limitadas.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                body=body,
                modelId=model_id,
                accept="application/json",
                contentType="application/json"
            )
            return response
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            # Si es Throttling, esperamos MUCHO más tiempo
            if error_code == 'ThrottlingException':
                if attempt < max_retries - 1:
                    # Fórmula nueva: Espera 10s, luego 15s, luego 20s
                    wait_time = 10 + (attempt * 5) 
                    print(f"⏳ AWS nos pide esperar ({model_id}). Durmiendo {wait_time} segundos...")
                    time.sleep(wait_time)
                    continue
            
            print(f"❌ Error fatal en AWS ({model_id}): {e}")
            return None
    return None

def generate_image(prompt, style_preset="photographic"):
    """
    Genera imagen usando Amazon Titan Image Generator G1 V2.
    """
    final_prompt = f"{prompt}. Artistic style: {style_preset}, high quality, detailed."

    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": final_prompt
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 1024,
            "width": 1024,
            "cfgScale": 8.0,
            "seed": random.randint(0, 1000)
        }
    })
    
    response = invoke_with_retry("amazon.titan-image-generator-v2:0", body)
    
    if response:
        try:
            response_body = json.loads(response.get("body").read())
            base64_image = response_body.get("images")[0]
            return base64_image
        except Exception as e:
            print(f"Error procesando imagen: {e}")
            return None
    return None

def edit_text_content(original_text, instruction):
    """
    Edita texto usando AMAZON TITAN TEXT EXPRESS v1.
    """
    prompt_input = f"User: Actúa como un editor experto. Texto original: '{original_text}'. Tarea: {instruction}. Devuelve SOLO el texto mejorado.\nBot:"

    body = json.dumps({
        "inputText": prompt_input,
        "textGenerationConfig": {
            "maxTokenCount": 1024,
            "stopSequences": [],
            "temperature": 0.7,
            "topP": 0.9
        }
    })

    response = invoke_with_retry("amazon.titan-text-express-v1", body)

    if response:
        try:
            response_body = json.loads(response.get("body").read())
            return response_body.get('results')[0].get('outputText').strip()
        except Exception as e:
            print(f"Error procesando texto: {e}")
            return "Error al leer respuesta de Titan."
    
    return "El servidor de AWS está saturado. Intenta de nuevo en unos segundos."
