import os
import json
import logging
from termcolor import colored
from dotenv import load_dotenv
from langchain_community.embeddings import GPT4AllEmbeddings
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from dataclasses import dataclass
from typing import Dict, List, Tuple, Union, Optional, Callable, ClassVar
from langchain.chains.llm import LLMChain
from pydantic import BaseModel, ValidationError
from src.chains import get_analyzer_chain
from src.graph import create_graph, compile_workflow
from src.states import (
    Analisis,
    Candidato,
    State
)
from src.utils import (
                        get_current_spanish_date_iso, 
                        setup_logging,
                        get_id,
                        get_arg_parser
                        )
from src.exceptions import NoOpenAIToken

# Load environment variables from .env file
load_dotenv()

# Set environment variables
os.environ['LANGCHAIN_TRACING_V2'] = 'true'
os.environ['LANGCHAIN_ENDPOINT'] = 'https://api.smith.langchain.com'
os.environ['LANGCHAIN_API_KEY'] = os.getenv('LANGCHAIN_API_KEY')
#os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
os.environ['LLAMA_CLOUD_API_KEY'] = os.getenv('LLAMA_CLOUD_API_KEY')
os.environ['HF_TOKEN'] = os.getenv('HUG_API_KEY')

# Logging configuration
logger = logging.getLogger(__name__)

@dataclass()
class CvAnalyzer:
    chain: LLMChain
    def invoke(self, candidato: Candidato) -> dict:
        return self.chain.invoke(input={"cv": candidato.cv, "oferta": candidato.oferta})
    
@dataclass()
class Pipeline:
    data_path: Optional[str] = None
    data: Optional[dict] = None
    
    def __post_init__(self):
        if self.data is not None and self.data_path is not None:
            logger.warning("Definidas dos configuraciones [archivo json y dict] -> da prioridad a dict config")
        if self.config is None and self.data_path is not None:
            self.data = self.get_config()
            logger.info(f"Definida configuracion mediante archivo JSON en {self.data_path}")
        if self.data is None and self.data_path is None:
            logger.exception("No se ha proporcionado ninguna configuración para la generación usando Pipeline")
            raise AttributeError("No se ha proporcionado ninguna configuración para la generación usando Pipeline")
        
        self.chain = get_analyzer_chain()  # Get objeto base chain para la tarea de análisis de CVs
        self.cv = self.data.get("cv", None)
        self.oferta = self.data.get("oferta", None)
        if self.cv is not None and self.oferta is not None:
            self.candidato = self.get_candidato() # Get obj Candidato
            self.analyzer_chain = self.get_analyzer()  # Get objeto base chain 'customizado' para tarea análisis de CVs [incluye atrb el cv y oferta específico]
            logger.debug(f"Cv Candidato -> {self.candidato.cv}")
            logger.debug(f"Oferta de Empleo para candidato-> {self.candidato.oferta}")
        else:
            logger.exception("No se ha proporcionado ningún CV ni oferta de empleo para el análisis")
            raise ValueError("No se ha proporcionado ningún CV ni oferta de empleo para el análisis")
        
    def get_config(self) -> dict:
        if not os.path.exists(self.data_path):
            logger.exception(f"Archivo de datos json no encontrado en {self.data_path}")
            raise FileNotFoundError(f"Archivo de configuración no encontrado en {self.data_path}")
        with open(self.data_path, encoding='utf-8') as file:
            data = json.load(file)
        return data
        
    def get_analyzer(self) -> CvAnalyzer:
        return CvAnalyzer(chain=self.chain)
    
    def get_candidato(self) -> Candidato:
        return Candidato(id=get_id(), cv=self.cv, oferta=self.oferta)

    def get_analisis(self) -> Analisis:
        """Run Pipeline -> Invoca langchain chain -> genera objeto Analisis con respuesta del modelo"""
        logger.info(f"Análisis del candidato : \n {self.candidato}")
        self._raw_response = self.analyzer_chain.invoke(candidato=self.candidato)  # Invoca a la chain que parsea la respuesta del modelo a python dict
        logger.info(f"Análisis del modelo : \n {self._raw_response}")
    
        # Manejo de una respuesta del modelo en un formato no correcto [no alineado con pydantic BaseModel]
        try:
            self.analisis = Analisis(**self._raw_response,id=self.candidato.id , status="OK")  # Instancia de Pydantic Analisis BaseModel object
            return self.analisis
        except ValidationError as e:
            logger.exception(f'{e} : Formato de respuesta del modelo incorrecta')
            return Analisis(puntuacion=0, experiencias=list(),id=self.candidato.id, descripcion="", status="ERROR")
        
@dataclass()
class ConfigGraph:
    config_path: Optional[str] = None
    data_path: Optional[str] = None
    
    def __post_init__(self):
        if self.config_path is None:
            logger.exception("No se ha proporcionado ninguna configuración para la generación usando Agents")
            raise AttributeError("No se ha proporcionado ninguna configuración para la generación usando Agents")
        if self.data_path is None:
            logger.exception("No se han proporcionado datos para analizar para la generación usando Agents")
            raise AttributeError("No se han proporcionado datos para analizar para la generación usando Agents")
        if self.config_path is not None:
            self.config = self.get_config()
            logger.info(f"Definida configuracion mediante archivo JSON en {self.config_path}")
        if self.config_path is not None:
            self.data = self.get_data()
            logger.info(f"Definidos los datos mediante archivo JSON en {self.data_path}")
            
        self.cv = self.data.get("cv", None)
        self.oferta = self.data.get("oferta", None)
        self.iteraciones = self.config.get("iteraciones", 10)
        self.thread_id = self.config.get("thread_id", "4")
        self.verbose = self.config.get("verbose", 0)
        
        if self.cv is not None and self.oferta is not None:
            self.candidato = self.get_candidato() # Get obj Candidato
            logger.debug(f"Cv Candidato -> {self.candidato.cv}")
            logger.debug(f"Oferta de Empleo para candidato-> {self.candidato.oferta}")
        else:
            logger.exception("No se ha proporcionado ningún CV ni oferta de empleo para el análisis")
            raise ValueError("No se ha proporcionado ningún CV ni oferta de empleo para el análisis")
        
    def get_config(self) -> dict:
        if not os.path.exists(self.config_path):
            logger.exception(f"Archivo de configuración no encontrado en {self.config_path}")
            raise FileNotFoundError(f"Archivo de configuración no encontrado en {self.config_path}")
        with open(self.config_path, encoding='utf-8') as file:
            config = json.load(file)
        return config
    
    def get_data(self) -> dict:
        if not os.path.exists(self.data_path):
            logger.exception(f"Archivo de configuración no encontrado en {self.data_path}")
            raise FileNotFoundError(f"Archivo de configuración no encontrado en {self.data_path}")
        with open(self.data_path, encoding='utf-8') as file:
            data = json.load(file)
        return data
    
    def get_candidato(self) -> Candidato:
        return Candidato(id=get_id(), cv=self.cv, oferta=self.oferta)
        
        

def main() -> None:
    setup_logging()
    
    parser = get_arg_parser()
    args = parser.parse_args()
    CONFIG_PATH = args.config_path
    OPENAI_API_KEY = args.token
    MODE = args.mode
    DATA_PATH = args.data_path
    
    if OPENAI_API_KEY is not None:
        os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY
    else:
        raise NoOpenAIToken("No OpenAI API token provided")

    if MODE == 'graph':
        logger.info("Creating graph and compiling workflow...")
        config = ConfigGraph(config_path=CONFIG_PATH, data_path=DATA_PATH)
        graph = create_graph()
        workflow = compile_workflow(graph)
        logger.info("Graph and workflow created.")
        
        candidato = {"candidato": config.candidato}
        thread = {"configurable": {"thread_id": config.thread_id}}
        iteraciones = {"recursion_limit": config.iteraciones}
        
        for event in workflow.stream(
            candidato, iteraciones
            ):
            if config.verbose == 1:
                print(colored(f"\nState Dictionary: {event}" ,  'cyan'))
            else:
                print("\n")

        
    if MODE == 'pipeline':
        pipeline = Pipeline(data_path=DATA_PATH)
        analisis = pipeline.get_analisis()
        print(colored(f'Candidato analizado : \n {pipeline.candidato}', 'cyan', attrs=["bold"]))
        print(colored(f'Respuesta del modelo : \n {analisis}', 'yellow', attrs=["bold"]))

if __name__ == '__main__':
    main()
    # terminal command : python app.py --data_path ./config/data.json --token <tu_token> --mode "graph" --config_path ./config/generation.json
