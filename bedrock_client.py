import os
import google.generativeai as genai
import requests
import base64
import random
import time

# Configuración de Google Gemini
GOOGLE_KEY = os.environ.get('GOOGLE_API_KEY')
if GOOGLE_KEY:
    genai.configure(api_key=GOOGLE_KEY)

def generate_image(prompt, style_preset="photographic"):
    """
    Genera imagen usando la API abierta de Pollinations.ai
    """
    try:
        final_prompt = f"{prompt}, {style_preset} style, highly detailed, 8k resolution"
        encoded_prompt = requests.utils.quote(final_prompt)
        
        # URL de la API
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={random.randint(0, 1000)}&nologo=true"
        print(f"🎨 Generando imagen en: {url}")
        
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        else:
            print(f"Error en API Imagen: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error generando imagen: {e}")
        return None

def edit_text_content(original_text, instruction):
    """
    Edita texto usando GOOGLE GEMINI 2.5 FLASH.
    """
    if not GOOGLE_KEY:
        return "Error: Falta la variable GOOGLE_API_KEY en Render."

    try:
        # CORRECCIÓN: Usamos el modelo exacto que salió en tu lista
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"Actúa como un editor experto. Texto original: '{original_text}'. Instrucción: {instruction}. Devuelve SOLO el resultado editado."
        
        response = model.generate_content(prompt)
        
        return response.text.strip()
        
    except Exception as e:
        print(f"Error Gemini: {e}")
        return f"Error Google AI: {str(e)}"
