"""Análises sobre o plano: tempo de evacuação, validação do projeto e resiliência."""

from __future__ import annotations

from dataclasses import dataclass, field

from .modelo import Edificio
from .motor import Cenario, Perfil, Plano, calcular_plano

# Fluxo específico em pessoas / (metro de largura · segundo). Valor de referência
# usado em modelos hidráulicos de evacuação (SFPE).
FLUXO_ESPECIFICO = 1.3
LARGURA_MINIMA_PORTA = 0.8  # metros


@dataclass
class ResultadoSaida:
    saida: str
    pessoas: int
    capacidade_pps: float
    chegada_ultimo_s: float
    tempo_final_s: float

    @property
    def fila_s(self) -> float:
        """Tempo extra causado pela fila na porta."""
        return max(0.0, self.tempo_final_s - self.chegada_ultimo_s)


@dataclass
class Estimativa:
    por_saida: list[ResultadoSaida]
    pessoas_sem_rota: int
    pre_movimento_s: float

    @property
    def tempo_total_s(self) -> float:
        if not self.por_saida:
            return float("inf")
        return max(r.tempo_final_s for r in self.por_saida)

    @property
    def gargalo(self) -> ResultadoSaida | None:
        return max(self.por_saida, key=lambda r: r.tempo_final_s, default=None)


def estimar_evacuacao(plano: Plano, pre_movimento_s: float = 60.0) -> Estimativa:
    """Modelo hidráulico simples: grupos chegam às saídas e formam fila.

    Cada saída escoa `FLUXO_ESPECIFICO x largura` pessoas por segundo. Os grupos
    são processados em ordem de chegada. O tempo de pré-movimento representa
    o intervalo entre o alarme e o início da caminhada.
    """
    ed = plano.edificio
    grupos: dict[str, list[tuple[float, int]]] = {}
    sem_rota = 0
    for no in ed.nos.values():
        if no.ocupacao == 0 or no.id in plano.cenario.bloqueados:
            continue
        if no.id not in plano.tempo:
            sem_rota += no.ocupacao
            continue
        chegada = pre_movimento_s + plano.tempo[no.id]
        grupos.setdefault(plano.destino[no.id], []).append((chegada, no.ocupacao))

    resultados = []
    for saida_id, lista in grupos.items():
        if ed.nos[saida_id].tipo != "saida":
            continue  # área de refúgio: a pessoa aguarda resgate, não há escoamento
        bloqueados = plano.cenario.bloqueados
        largura = sum(c.largura for viz, c in ed.vizinhos(saida_id) if viz not in bloqueados)
        capacidade = FLUXO_ESPECIFICO * largura
        relogio = 0.0
        for chegada, pessoas in sorted(lista):
            relogio = max(relogio, chegada) + pessoas / capacidade
        resultados.append(ResultadoSaida(
            saida=saida_id, pessoas=sum(p for _, p in lista), capacidade_pps=capacidade,
            chegada_ultimo_s=max(c for c, _ in lista), tempo_final_s=relogio))

    resultados.sort(key=lambda r: r.saida)
    return Estimativa(por_saida=resultados, pessoas_sem_rota=sem_rota,
                      pre_movimento_s=pre_movimento_s)


@dataclass
class Problema:
    nivel: str  # "erro" ou "alerta"
    mensagem: str


@dataclass
class Relatorio:
    problemas: list[Problema] = field(default_factory=list)

    @property
    def erros(self) -> list[Problema]:
        return [p for p in self.problemas if p.nivel == "erro"]

    @property
    def ok(self) -> bool:
        return not self.erros

    def add(self, nivel: str, mensagem: str) -> None:
        self.problemas.append(Problema(nivel, mensagem))


def validar(edificio: Edificio) -> Relatorio:
    rel = Relatorio()
    saidas = edificio.saidas
    if not saidas:
        rel.add("erro", "O edifício não tem nenhuma saída.")
        return rel
    if len(saidas) < 2:
        rel.add("alerta", "Só existe uma saída. Um único foco de incêndio pode bloquear a evacuação.")

    plano = calcular_plano(edificio)
    for nid in plano.nos_sem_rota():
        rel.add("erro", f"{nid} não tem caminho até nenhuma saída.")

    for no in edificio.nos.values():
        if no.ocupacao and no.id in plano.tempo:
            dist = plano.rota(no.id).distancia_m
            if dist > edificio.distancia_maxima:
                rel.add("erro", f"{no.id}: percurso de {dist:.1f} m excede o limite de "
                                f"{edificio.distancia_maxima:.0f} m.")

    for c in edificio.conexoes:
        if c.tipo != "escada" and c.largura < LARGURA_MINIMA_PORTA:
            rel.add("alerta", f"Passagem {c.de}-{c.para} com {c.largura:.2f} m, abaixo de "
                              f"{LARGURA_MINIMA_PORTA} m.")

    plano_pcd = calcular_plano(edificio, perfil=Perfil.MOBILIDADE_REDUZIDA)
    for no in edificio.nos.values():
        if no.ocupacao and no.id not in plano_pcd.tempo:
            rel.add("alerta", f"{no.id}: pessoa em cadeira de rodas não alcança saída nem "
                              f"área de refúgio.")
    return rel


@dataclass
class ImpactoBloqueio:
    saida: str
    nos_isolados: list[str]
    pessoas_isoladas: int
    tempo_total_s: float
    variacao_s: float


def resiliencia(edificio: Edificio) -> list[ImpactoBloqueio]:
    """Bloqueia cada saída, uma de cada vez, e mede o efeito na evacuação."""
    base = estimar_evacuacao(calcular_plano(edificio)).tempo_total_s
    impactos = []
    for saida in edificio.saidas:
        plano = calcular_plano(edificio, Cenario(bloqueados={saida.id}, propagar_fumaca=False))
        isolados = plano.nos_sem_rota()
        est = estimar_evacuacao(plano)
        impactos.append(ImpactoBloqueio(
            saida=saida.id, nos_isolados=isolados,
            pessoas_isoladas=sum(edificio.nos[n].ocupacao for n in isolados),
            tempo_total_s=est.tempo_total_s, variacao_s=est.tempo_total_s - base))
    impactos.sort(key=lambda i: (-i.pessoas_isoladas, -i.variacao_s))
    return impactos
