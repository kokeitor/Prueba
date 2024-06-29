import logging
from termcolor import colored
from typing import Callable
from pydantic import ValidationError
from states import State, Analisis, Agent
from chains import get_chain
from utils import get_current_spanish_date_iso, get_id

# Logging configuration
logger = logging.getLogger(__name__)


def analyzer_agent(
    state: State,
    analyzer: Agent,
    re_analyzer: Agent,
    get_chain: Callable = get_chain
) -> State:
    logger.info(f"Estado previo [Analyzer-Agent] : \n {state}")
    
    candidato = state["candidato"]
    logger.info(f"Análisis del candidato : \n {candidato=}")
    
    # Comprobamos si es un re-análisis por alucinación o un análisis inicial
    if state["alucinacion_oferta"] and (state["alucinacion_oferta"] == 1.0 or state["alucinacion_oferta"] == 1):
        re_analyzer_chain = get_chain(
            get_model=re_analyzer.get_model,
            prompt_template=re_analyzer.prompt,
            temperature=re_analyzer.temperature
        )
        raw_response = re_analyzer_chain.invoke(input={
            "cv": candidato.cv,
            "oferta": candidato.oferta,
            "analisis_previo": state["analisis"][-1]
        })
        logger.warning(f"Re analizando el candidato : \n {candidato=}")
        logger.warning(f"Re análisis : \n {raw_response=}")
    elif state["alucinacion_cv"] and (state["alucinacion_cv"] == 1.0 or state["alucinacion_cv"] == 1):
        re_analyzer_chain = get_chain(
            get_model=re_analyzer.get_model,
            prompt_template=re_analyzer.prompt,
            temperature=re_analyzer.temperature
        )
        raw_response = re_analyzer_chain.invoke(input={
            "cv": candidato.cv,
            "oferta": candidato.oferta,
            "analisis_previo": state["analisis"][-1]
        })
        logger.warning(f"Re analizando el candidato por cv hallucination: \n {candidato=}")
        logger.warning(f"Re análisis : \n {raw_response=}")
    else:
        analyzer_chain = get_chain(
            get_model=analyzer.get_model,
            prompt_template=analyzer.prompt,
            temperature=analyzer.temperature
        )
        raw_response = analyzer_chain.invoke(input={
            "cv": candidato.cv,
            "oferta": candidato.oferta
        })
        logger.debug(f"Análisis normal: \n {raw_response=}")

    # Manejo de una respuesta del modelo en un formato no correcto [no alineado con pydantic BaseModel]
    try:
        analisis = Analisis(
            **raw_response,
            fecha=get_current_spanish_date_iso(),
            id=get_id(),
            candidato_id=candidato.id,
            status="OK"
        )  # Instancia de Pydantic Analisis BaseModel object
    except ValidationError as e:
        logger.exception(f'{e} : Formato de respuesta del modelo incorrecta')
        analisis = Analisis(
            puntuacion=0,
            experiencias=[{"error": "error"}],
            fecha=get_current_spanish_date_iso(),
            id=get_id(),
            candidato_id=candidato.id,
            descripcion="",
            status="ERROR"
        )
        
    if state["alucinacion_oferta"] and (state["alucinacion_oferta"] == 1.0 or state["alucinacion_oferta"] == 1):
        print(colored(f"\nRe Análisis del Agente-Analista 👩🏿‍💻\n\nOferta de Empleo : {candidato.oferta}\nNueva Puntuación del Candidato : {analisis.puntuacion}\nNuevas Experiencias extraídas : {analisis.experiencias}\nNueva Descripción : {analisis.descripcion}\nStatus análisis : {analisis.status}", 'light_blue'))
    else:
        print(colored(f"\nAgente-Analista 👩🏿‍💻\n\nOferta de Empleo : {candidato.oferta}\nPuntuación del Candidato : {analisis.puntuacion}\nExperiencias : {analisis.experiencias}\nDescripción : {analisis.descripcion}\nStatus análisis : {analisis.status}", 'light_blue', attrs=["bold"]))
    
    # Comprueba si es el primer análisis
    if state["analisis"]:
        state["analisis"].append(analisis)
    else:
        state["analisis"] = [analisis]
    logger.info(f"Estado tras Analyzer-Agent : \n {state}")

    return state


def reviewer_cv_agent(
    state: State,
    agent: Agent,
    get_chain: Callable = get_chain
) -> State:
    reviewer_chain = get_chain(
        get_model=agent.get_model,
        prompt_template=agent.prompt,
        temperature=agent.temperature
    )

    candidato = state["candidato"]
    analisis_previo = state["analisis"][-1]
    logger.info(f"Reviewer-Cv-Agent..")
    logger.debug(f"Revisión del candidato : \n {candidato}")
    logger.debug(f"Análisis previo : \n {analisis_previo}")
    
    alucinacion_cv = reviewer_chain.invoke(input={
        "cv": candidato.cv,
        "experiencias": analisis_previo.experiencias
    })
    
    # Manejo de una respuesta del modelo en un formato no correcto [no alineado con tipo Union[int,float] de clave "alucinacion"]
    if not isinstance(alucinacion_cv["puntuacion"], (int, float)):
        raise ValueError(f"El Hallucination-Agent está devolviendo una alucinación : {alucinacion_cv} no alineada con tipo de dato Union[int,float]")
    
    logger.info(f"Hallucination-CV-Agent response : \n {alucinacion_cv}")
    if alucinacion_cv["puntuacion"] == 1 or alucinacion_cv["puntuacion"] == 1.0:
        print(colored(f"\nAgente-Revisor-Cv 👩🏽\nAlucinación -> Si", 'light_red', attrs=["bold"]))
    elif alucinacion_cv["puntuacion"] == 0 or alucinacion_cv["puntuacion"] == 0.0:
        print(colored(f"\nAgente-Revisor-Cv 👩🏽\nAlucinación -> No", 'light_green', attrs=["bold"]))
    else:
        print(colored(f"\nAgente-Revisor-Cv 👩🏽\nAlucinación del Cv -> N/A", 'dark_grey', attrs=["bold"]))
    
    logger.info(f"Estado tras Reviewer-Cv-Agent : \n {alucinacion_cv['puntuacion']}")
    
    return {"alucinacion_cv": alucinacion_cv["puntuacion"]}


def reviewer_offer_agent(
    state: State,
    agent: Agent,
    get_chain: Callable = get_chain
) -> State:
    logger.info(f"Estado previo [Reviewer-Agent] : \n {state}")
    
    reviewer_chain = get_chain(
        get_model=agent.get_model,
        prompt_template=agent.prompt,
        temperature=agent.temperature
    )

    candidato = state["candidato"]
    analisis_previo = state["analisis"][-1]
    logger.info(f"Reviewer-Offer-Agent..")
    logger.debug(f"Revisión del candidato : \n {candidato}")
    logger.debug(f"Análisis previo : \n {analisis_previo}")
    
    alucinacion = reviewer_chain.invoke(input={
        "cv": candidato.cv,
        "oferta": candidato.oferta,
        "analisis": analisis_previo
    })
    
    # Manejo de una respuesta del modelo en un formato no correcto [no alineado con tipo Union[int,float] de clave "alucinacion"]
    if not isinstance(alucinacion["alucinacion"], (int, float)):
        raise ValueError(f"El Reviewer-Agent está devolviendo una alucinación : {alucinacion} no alineada con tipo de dato Union[int,float]")
    
    logger.info(f"Hallucination-Offer-Agent response  : \n {alucinacion}")
    if alucinacion["alucinacion"] == 1 or alucinacion["alucinacion"] == 1.0:
        print(colored(f"\nAgente-Revisor-Oferta 👩🏽‍⚖️\nAnálisis del Cv -> Incorrecto", 'light_red'))
    elif alucinacion["alucinacion"] == 0 or alucinacion["alucinacion"] == 0.0:
        print(colored(f"\nAgente-Revisor-Oferta 👩🏽‍⚖️\nAnálisis del Cv -> Correcto", 'light_green'))
    else:
        print(colored(f"\nAgente-Revisor-Oferta 👩🏽‍⚖️: \nAnálisis del Cv -> N/A", 'dark_grey'))
    
    logger.info(f"Estado tras Reviewer-Agent : \n {alucinacion['alucinacion']}")

    return {"alucinacion_oferta": alucinacion["alucinacion"]}


def final_report(state: State) -> State:
    analisis_final = state["analisis"][-1]
    candidato = state["candidato"]
    
    logger.info(f"Análisis final : \n {analisis_final}")
    print(colored(f"\nReporte final 📝\n\nFecha del análisis : {analisis_final.fecha}\n\n**CANDIDATO**\n{candidato.cv}\n\n**OFERTA**\n{candidato.oferta}\n\n**ANÁLISIS**\n- Puntuación : {analisis_final.puntuacion}\n- Experiencias : {analisis_final.experiencias}\n- Descripción : {analisis_final.descripcion}", 'light_yellow', attrs=["bold"]))

    return {"analisis_final": analisis_final}
