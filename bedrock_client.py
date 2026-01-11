import boto3
import json
import base64
import os
import time
import random
from botocore.exceptions import ClientError
from botocore.config import Config

# Configuración del cliente Bedrock con reintentos automáticos
my_config = Config(
    region_name='us-east-1',
    retries = {
        'max_attempts': 5,
        'mode': 'adaptive'
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
    Intenta llamar al modelo hasta 3 veces si AWS dice que esperemos.
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
            # Errores de velocidad (Throttling)
            if error_code == 'ThrottlingException':
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"⚠️ Throttling en {model_id}. Reintentando en {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    continue
            # Si el error es de Cuota Diaria, no sirve reintentar
            if "Too many tokens per day" in str(e):
                print("❌ Se alcanzó la cuota diaria de Claude.")
                raise e # Lanzamos el error para que se vea en el frontend
                
            print(f"❌ Error en AWS ({model_id}): {e}")
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
    
    # Usamos Titan v2 que es el estable actualmente
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
    Edita texto usando CLAUDE 3 HAIKU (Requisito del PDF).
    """
    prompt_config = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": f"Eres un experto en marketing. Texto: '{original_text}'. Tarea: {instruction}. Responde solo con el texto editado."
            }
        ]
    }

    body = json.dumps(prompt_config)

    # Usamos Claude 3 Haiku (El más rápido y ligero)
    try:
        response = invoke_with_retry("anthropic.claude-3-haiku-20240307-v1:0", body)
        
        if response:
            response_body = json.loads(response.get("body").read())
            return response_body.get("content")[0].get("text")
            
    except ClientError as e:
        if "Too many tokens per day" in str(e):
            return "⚠️ Error: Has superado la cuota diaria gratuita de Claude por hoy. Intenta mañana o usa otra cuenta."
        return f"Error AWS: {str(e)}"
    
    return "Error desconocido al contactar a Claude."
