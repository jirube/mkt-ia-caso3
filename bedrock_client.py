import boto3
import json
import base64
import os
from botocore.exceptions import ClientError

# Configuración segura: Lee las claves del entorno del servidor (Render)
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
)

def generate_image(prompt, style_preset="photographic"):
    """
    Genera imagen usando Stable Diffusion XL.
    """
    body = json.dumps({
        "text_prompts": [{"text": prompt}],
        "cfg_scale": 10,
        "steps": 30,
        "style_preset": style_preset
    })
    
    try:
        response = bedrock_runtime.invoke_model(
            body=body,
            modelId="stability.stable-diffusion-xl-v1",
            accept="application/json",
            contentType="application/json"
        )
        response_body = json.loads(response.get("body").read())
        base64_image = response_body.get("artifacts")[0].get("base64")
        return base64_image
    except ClientError as e:
        print(f"Error generando imagen: {e}")
        return None

def edit_text_content(original_text, instruction):
    """
    Edita texto usando Claude 3 (o v2).
    """
    prompt_config = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": f"Actúa como un editor experto. Texto original: '{original_text}'. Instrucción: {instruction}. Devuelve solo el resultado editado."
            }
        ]
    }

    body = json.dumps(prompt_config)

    try:
        # Nota: Asegúrate de tener acceso a este modelo en Bedrock o cambia a 'anthropic.claude-v2'
        response = bedrock_runtime.invoke_model(
            body=body,
            modelId="anthropic.claude-3-sonnet-20240229-v1:0", 
            accept="application/json",
            contentType="application/json"
        )
        response_body = json.loads(response.get("body").read())
        return response_body.get("content")[0].get("text")
    except ClientError as e:
        print(f"Error editando texto: {e}")
        return f"Error de conexión con AWS: {str(e)}"
