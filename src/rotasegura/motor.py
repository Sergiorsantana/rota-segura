"""Motor de rotas: Dijkstra multi-origem partindo de todas as saídas ao mesmo tempo.

Rodar o Dijkstra a partir das saídas (e não de cada sala) resolve o edifício
inteiro em uma passada: cada nó recebe o tempo até a saída mais próxima e o
próximo passo da rota. É o mesmo princípio de um "campo de fluxo".
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum

from .modelo import Conexao, Edificio

# Velocidades de referência (m/s), simplificadas a partir do SFPE Handbook.
VELOCIDADE = {
    "horizontal": 1.2,
    "porta_corta_fogo": 1.2,
    "rampa": 1.0,
    "escada": 0.6,
}


class Perfil(str, Enum):
    PADRAO = "padrao"
    MOBILIDADE_REDUZIDA = "mobilidade_reduzida"


@dataclass
class Cenario:
    """Condições do incêndio: nós tomados pelo fogo e nós com fumaça."""

    bloqueados: set[str] = field(default_factory=set)
    fumaca: set[str] = field(default_factory=set)
    penalidade_fumaca: float = 3.0
    propagar_fumaca: bool = True

    def nos_com_fumaca(self, edificio: Edificio) -> set[str]:
        """Fumaça explícita mais, se ativado, os vizinhos diretos do fogo."""
        com_fumaca = set(self.fumaca)
        if self.propagar_fumaca:
            for nid in self.bloqueados:
                for viz, _ in edificio.vizinhos(nid):
                    com_fumaca.add(viz)
        return com_fumaca - self.bloqueados


@dataclass
class Rota:
    origem: str
    caminho: list[str]
    tempo_s: float
    distancia_m: float
    destino: str
    passa_por_fumaca: bool

    @property
    def alcancavel(self) -> bool:
        return bool(self.caminho)


@dataclass
class Plano:
    """Resultado completo para um edifício sob um cenário e um perfil."""

    edificio: Edificio
    cenario: Cenario
    perfil: Perfil
    tempo: dict[str, float]
    proximo: dict[str, str | None]
    destino: dict[str, str]

    def rota(self, origem: str) -> Rota:
        if origem not in self.edificio.nos:
            raise KeyError(f"Nó inexistente: {origem}")
        if origem not in self.tempo:
            return Rota(origem, [], float("inf"), float("inf"), "", False)

        fumaca = self.cenario.nos_com_fumaca(self.edificio)
        caminho = [origem]
        distancia = 0.0
        atual = origem
        while self.proximo[atual] is not None:
            seguinte = self.proximo[atual]
            distancia += _conexao_entre(self.edificio, atual, seguinte).distancia
            caminho.append(seguinte)
            atual = seguinte
        return Rota(origem=origem, caminho=caminho, tempo_s=self.tempo[origem],
                    distancia_m=distancia, destino=self.destino[origem],
                    passa_por_fumaca=any(n in fumaca for n in caminho))

    def nos_sem_rota(self) -> list[str]:
        return [nid for nid, no in self.edificio.nos.items()
                if nid not in self.tempo and nid not in self.cenario.bloqueados
                and no.tipo != "elevador"]


def _conexao_entre(edificio: Edificio, a: str, b: str) -> Conexao:
    for viz, c in edificio.vizinhos(a):
        if viz == b:
            return c
    raise KeyError(f"Sem conexão entre {a} e {b}")


def _custo(c: Conexao, destino_no: str, fumaca: set[str], penalidade: float) -> float:
    tempo = c.distancia / VELOCIDADE[c.tipo]
    if destino_no in fumaca:
        tempo *= penalidade
    return tempo


def calcular_plano(edificio: Edificio, cenario: Cenario | None = None,
                   perfil: Perfil = Perfil.PADRAO) -> Plano:
    cenario = cenario or Cenario()
    perfil = Perfil(perfil)
    desconhecidos = (cenario.bloqueados | cenario.fumaca) - edificio.nos.keys()
    if desconhecidos:
        raise KeyError(f"Nós inexistentes no cenário: {sorted(desconhecidos)}")

    fumaca = cenario.nos_com_fumaca(edificio)
    alvos = [n.id for n in edificio.saidas]
    if perfil is Perfil.MOBILIDADE_REDUZIDA:
        alvos += [n.id for n in edificio.areas_refugio]
    alvos = [a for a in alvos if a not in cenario.bloqueados]

    tempo: dict[str, float] = dict.fromkeys(alvos, 0.0)
    proximo: dict[str, str | None] = dict.fromkeys(alvos)
    destino: dict[str, str] = {a: a for a in alvos}
    fila = [(0.0, a) for a in alvos]
    heapq.heapify(fila)

    while fila:
        t, atual = heapq.heappop(fila)
        if t > tempo[atual]:
            continue
        for viz, c in edificio.vizinhos(atual):
            no_viz = edificio.nos[viz]
            if viz in cenario.bloqueados or no_viz.tipo == "elevador":
                continue
            if perfil is Perfil.MOBILIDADE_REDUZIDA and not c.acessivel:
                continue
            # A pessoa anda de `viz` para `atual`: o custo pesa o nó de chegada.
            novo = t + _custo(c, atual, fumaca, cenario.penalidade_fumaca)
            if novo < tempo.get(viz, float("inf")):
                tempo[viz] = novo
                proximo[viz] = atual
                destino[viz] = destino[atual]
                heapq.heappush(fila, (novo, viz))

    return Plano(edificio=edificio, cenario=cenario, perfil=perfil,
                 tempo=tempo, proximo=proximo, destino=destino)
