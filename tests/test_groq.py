from langchain_groq import ChatGroq
from src.config import GROQ_API_KEY, MODEL_NAME

llm = ChatGroq(
    model=MODEL_NAME,
    api_key=GROQ_API_KEY,
    temperature=0
)

response = llm.invoke("Diz apenas: ligação ao Groq funcionando")

print(response.content)