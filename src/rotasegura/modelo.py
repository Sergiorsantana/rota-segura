"""Modelo de dados do edifício: andares, nós (ambientes) e conexões (passagens)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TIPOS_NO = {"sala", "corredor", "escada", "elevador", "saida", "area_refugio"}
TIPOS_CONEXAO = {"horizontal", "escada", "rampa", "porta_corta_fogo"}


class ErroModelo(ValueError):
    """Erro de validação do arquivo de edifício."""


@dataclass(frozen=True)
class Andar:
    id: str
    nome: str
    elevacao: float = 0.0


@dataclass(frozen=True)
class No:
    id: str
    andar: str
    tipo: str
    x: float
    y: float
    nome: str = ""
    ocupacao: int = 0

    @property
    def rotulo(self) -> str:
        return self.nome or self.id

    @property
    def eh_saida(self) -> bool:
        return self.tipo == "saida"


@dataclass(frozen=True)
class Conexao:
    de: str
    para: str
    largura: float
    distancia: float
    tipo: str = "horizontal"

    @property
    def acessivel(self) -> bool:
        """Cadeirantes não usam escadas em situação de incêndio."""
        return self.tipo != "escada"


@dataclass
class Edificio:
    nome: str
    tipo: str
    andares: dict[str, Andar]
    nos: dict[str, No]
    conexoes: list[Conexao]
    distancia_maxima: float = 40.0
    descricao: str = ""
    _vizinhos: dict[str, list[Conexao]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._vizinhos = {nid: [] for nid in self.nos}
        for c in self.conexoes:
            self._vizinhos[c.de].append(c)
            self._vizinhos[c.para].append(c)

    def vizinhos(self, no_id: str) -> list[tuple[str, Conexao]]:
        saida = []
        for c in self._vizinhos[no_id]:
            outro = c.para if c.de == no_id else c.de
            saida.append((outro, c))
        return saida

    @property
    def saidas(self) -> list[No]:
        return [n for n in self.nos.values() if n.tipo == "saida"]

    @property
    def areas_refugio(self) -> list[No]:
        return [n for n in self.nos.values() if n.tipo == "area_refugio"]

    @property
    def ocupacao_total(self) -> int:
        return sum(n.ocupacao for n in self.nos.values())

    def nos_do_andar(self, andar_id: str) -> list[No]:
        return [n for n in self.nos.values() if n.andar == andar_id]

    # ------------------------------------------------------------------ carga
    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Edificio:
        try:
            andares = {
                a["id"]: Andar(id=str(a["id"]), nome=a.get("nome", str(a["id"])),
                               elevacao=float(a.get("elevacao", 0)))
                for a in dados["andares"]
            }
            nos: dict[str, No] = {}
            for n in dados["nos"]:
                no = No(id=str(n["id"]), andar=str(n["andar"]), tipo=n["tipo"],
                        x=float(n["x"]), y=float(n["y"]), nome=n.get("nome", ""),
                        ocupacao=int(n.get("ocupacao", 0)))
                if no.id in nos:
                    raise ErroModelo(f"Nó duplicado: {no.id}")
                if no.tipo not in TIPOS_NO:
                    raise ErroModelo(f"Tipo de nó inválido em {no.id}: {no.tipo}")
                if no.andar not in andares:
                    raise ErroModelo(f"Nó {no.id} aponta para andar inexistente: {no.andar}")
                if no.ocupacao < 0:
                    raise ErroModelo(f"Ocupação negativa em {no.id}")
                nos[no.id] = no

            conexoes = []
            for c in dados["conexoes"]:
                de, para = str(c["de"]), str(c["para"])
                for ref in (de, para):
                    if ref not in nos:
                        raise ErroModelo(f"Conexão referencia nó inexistente: {ref}")
                tipo = c.get("tipo", "horizontal")
                if tipo not in TIPOS_CONEXAO:
                    raise ErroModelo(f"Tipo de conexão inválido ({de}-{para}): {tipo}")
                largura = float(c.get("largura", 1.2))
                if largura <= 0:
                    raise ErroModelo(f"Largura deve ser positiva ({de}-{para})")
                distancia = c.get("distancia")
                if distancia is None:
                    a, b = nos[de], nos[para]
                    distancia = math.hypot(a.x - b.x, a.y - b.y)
                conexoes.append(Conexao(de=de, para=para, largura=largura,
                                        distancia=float(distancia), tipo=tipo))
        except KeyError as exc:
            raise ErroModelo(f"Campo obrigatório ausente: {exc}") from exc

        return cls(nome=dados["nome"], tipo=dados.get("tipo", "generico"),
                   andares=andares, nos=nos, conexoes=conexoes,
                   distancia_maxima=float(dados.get("distancia_maxima", 40.0)),
                   descricao=dados.get("descricao", ""))

    @classmethod
    def de_yaml(cls, caminho: str | Path) -> Edificio:
        with open(caminho, encoding="utf-8") as f:
            return cls.de_dict(yaml.safe_load(f))
