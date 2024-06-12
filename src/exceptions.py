# Custom Exceptions

class NoOpenAIToken(Exception):
    """Excepcion para manejo de openAI token"""
    def __init__(self, message:str="No OpenAI API token provided"):
        super().__init__(message)
        
        
class JsonlFormatError(Exception):
    """Excepcion para manejo de jsonl vacio o erroneo"""
    def __init__(self, message:str="No se han proporcionado candidatos en el archivo jsonl con el correcto fomato [cv : '...', oferta : '...] "):
        super().__init__(message)
