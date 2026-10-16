"""API REST com FastAPI. Rode com: uvicorn rotasegura.api:app --reload"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import analise, render
from .modelo import Edificio, ErroModelo
from .motor import Cenario, Perfil, calcular_plano

PASTA = Path(os.environ.get("ROTASEGURA_EDIFICIOS", Path(__file__).parents[2] / "exemplos"))

app = FastAPI(title="Rota Segura", version="0.1.0",
              description="Cálculo de rotas de fuga e tempo de evacuação em edifícios.")


class CenarioIn(BaseModel):
    fogo: list[str] = Field(default_factory=list)
    fumaca: list[str] = Field(default_factory=list)
    perfil: Perfil = Perfil.PADRAO
    pre_movimento_s: float = 60.0


class PlanoIn(CenarioIn):
    edificio: dict[str, Any] = Field(description="Edifício no mesmo formato do YAML")


def _carregar(nome: str) -> Edificio:
    caminho = (PASTA / f"{nome}.yaml").resolve()
    if caminho.parent != PASTA.resolve() or not caminho.exists():
        raise HTTPException(404, f"Edifício '{nome}' não encontrado")
    return Edificio.de_yaml(caminho)


def _calcular(ed: Edificio, fogo, fumaca, perfil):
    try:
        return calcular_plano(ed, Cenario(bloqueados=set(fogo), fumaca=set(fumaca)), perfil)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc


def _resposta(plano, pre_movimento_s: float) -> dict[str, Any]:
    est = analise.estimar_evacuacao(plano, pre_movimento_s)
    rotas = {}
    for nid, no in plano.edificio.nos.items():
        if no.ocupacao:
            r = plano.rota(nid)
            rotas[nid] = {"caminho": r.caminho, "destino": r.destino or None,
                          "distancia_m": round(r.distancia_m, 1) if r.alcancavel else None,
                          "tempo_s": round(r.tempo_s, 1) if r.alcancavel else None,
                          "passa_por_fumaca": r.passa_por_fumaca}
    return {
        "edificio": plano.edificio.nome,
        "perfil": plano.perfil.value,
        "tempo_total_s": None if not est.por_saida else round(est.tempo_total_s, 1),
        "pessoas_sem_rota": est.pessoas_sem_rota,
        "gargalo": est.gargalo.saida if est.gargalo else None,
        "saidas": [{"saida": r.saida, "pessoas": r.pessoas, "fila_s": round(r.fila_s, 1),
                    "tempo_final_s": round(r.tempo_final_s, 1)} for r in est.por_saida],
        "rotas": rotas,
    }


@app.get("/edificios")
def listar() -> list[dict[str, Any]]:
    itens = []
    for arq in sorted(PASTA.glob("*.yaml")):
        ed = Edificio.de_yaml(arq)
        itens.append({"id": arq.stem, "nome": ed.nome, "tipo": ed.tipo,
                      "andares": len(ed.andares), "ocupacao": ed.ocupacao_total})
    return itens


@app.get("/edificios/{nome}/rota")
def rota(nome: str, origem: str, fogo: list[str] = Query(default=[]),
         perfil: Perfil = Perfil.PADRAO) -> dict[str, Any]:
    plano = _calcular(_carregar(nome), fogo, [], perfil)
    if origem not in plano.edificio.nos:
        raise HTTPException(404, f"Nó '{origem}' não existe")
    r = plano.rota(origem)
    return {"origem": origem, "caminho": r.caminho, "destino": r.destino or None,
            "alcancavel": r.alcancavel,
            "distancia_m": round(r.distancia_m, 1) if r.alcancavel else None,
            "tempo_s": round(r.tempo_s, 1) if r.alcancavel else None}


@app.post("/edificios/{nome}/plano")
def plano_salvo(nome: str, cenario: CenarioIn) -> dict[str, Any]:
    plano = _calcular(_carregar(nome), cenario.fogo, cenario.fumaca, cenario.perfil)
    return _resposta(plano, cenario.pre_movimento_s)


@app.get("/edificios/{nome}/mapa.png")
def mapa(nome: str, fogo: list[str] = Query(default=[]), origem: str | None = None,
         perfil: Perfil = Perfil.PADRAO) -> Response:
    plano = _calcular(_carregar(nome), fogo, [], perfil)
    return Response(render.png_em_bytes(plano, destaque=origem), media_type="image/png")


@app.get("/edificios/{nome}/validacao")
def validacao(nome: str) -> dict[str, Any]:
    rel = analise.validar(_carregar(nome))
    return {"ok": rel.ok, "problemas": [p.__dict__ for p in rel.problemas]}


@app.post("/plano")
def plano_avulso(dados: PlanoIn) -> dict[str, Any]:
    """Calcula o plano para um edifício enviado no corpo da requisição."""
    try:
        ed = Edificio.de_dict(dados.edificio)
    except ErroModelo as exc:
        raise HTTPException(422, str(exc)) from exc
    plano = _calcular(ed, dados.fogo, dados.fumaca, dados.perfil)
    return _resposta(plano, dados.pre_movimento_s)
