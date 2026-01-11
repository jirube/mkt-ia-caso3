import boto3
import json
import base64
import os
from botocore.exceptions import ClientError

# Configuración del cliente Bedrock
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
)

def generate_image(prompt, style_preset="photographic"):
    """
    Genera imagen usando Amazon Titan Image Generator G1.
    """
    
    # Construimos el Prompt enriquecido
    final_prompt = f"{prompt}. Artistic style: {style_preset}, high quality, detailed."

    # Estructura JSON para Amazon Titan
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
            "seed": 0 
        }
    })
    
    try:
        response = bedrock_runtime.invoke_model(
            body=body,
            modelId="amazon.titan-image-generator-v1",
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())
        # Titan devuelve la imagen en base64 dentro de una lista 'images'
        base64_image = response_body.get("images")[0]
        return base64_image
        
    except ClientError as e:
        print(f"Error generando imagen (Titan): {e}")
        return None
    except Exception as e:
        print(f"Error desconocido: {e}")
        return None

def edit_text_content(original_text, instruction):
    """
    Edita texto usando Claude 3 Sonnet.
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
        return f"Error de conexión con AWS (Texto): {str(e)}"
