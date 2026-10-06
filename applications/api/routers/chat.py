from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    provider: str # "groq" or "gemini"
    prompt: str

@router.post("")
def chat_with_ai(request: ChatRequest):
    if request.provider == "groq":
        if Groq is None:
            raise HTTPException(status_code=500, detail="Groq SDK not installed")
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY not set")
        
        client = Groq(api_key=api_key)
        try:
            completion = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": request.prompt}]
            )
            return {"response": completion.choices[0].message.content}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    elif request.provider == "gemini":
        if genai is None:
            raise HTTPException(status_code=500, detail="google-generativeai SDK not installed")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set")
            
        genai.configure(api_key=api_key)
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(request.prompt)
            return {"response": response.text}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="Unknown provider. Use 'groq' or 'gemini'.")
