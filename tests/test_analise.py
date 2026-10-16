from pathlib import Path

import pytest

from rotasegura import Cenario, Edificio, calcular_plano, estimar_evacuacao, resiliencia, validar
from rotasegura.analise import FLUXO_ESPECIFICO

EXEMPLOS = Path(__file__).parents[1] / "exemplos"


def sala_unica(pessoas=130, largura=1.0, distancia=12.0):
    return Edificio.de_dict({
        "nome": "Sala", "andares": [{"id": "T"}],
        "nos": [{"id": "sala", "andar": "T", "tipo": "sala", "x": 0, "y": 0, "ocupacao": pessoas},
                {"id": "porta", "andar": "T", "tipo": "saida", "x": distancia, "y": 0}],
        "conexoes": [{"de": "sala", "para": "porta", "largura": largura}],
    })


def test_tempo_hidraulico_com_fila():
    est = estimar_evacuacao(calcular_plano(sala_unica()), pre_movimento_s=0)
    chegada = 12 / 1.2
    escoamento = 130 / (FLUXO_ESPECIFICO * 1.0)
    assert est.tempo_total_s == pytest.approx(chegada + escoamento)
    assert est.por_saida[0].fila_s == pytest.approx(escoamento)


def test_porta_mais_larga_reduz_tempo():
    estreita = estimar_evacuacao(calcular_plano(sala_unica(largura=0.9))).tempo_total_s
    larga = estimar_evacuacao(calcular_plano(sala_unica(largura=2.4))).tempo_total_s
    assert larga < estreita


def test_pessoas_sem_rota_sao_contadas():
    ed = Edificio.de_yaml(EXEMPLOS / "universidade.yaml")
    fogo = {"cT1", "cT2", "cT3", "cT4", "saida_aud"}
    est = estimar_evacuacao(calcular_plano(ed, Cenario(bloqueados=fogo)))
    assert est.pessoas_sem_rota > 0


@pytest.mark.parametrize("arquivo", sorted(EXEMPLOS.glob("*.yaml")), ids=lambda p: p.stem)
def test_exemplos_passam_na_validacao(arquivo):
    rel = validar(Edificio.de_yaml(arquivo))
    assert rel.ok, [p.mensagem for p in rel.erros]


def test_validacao_detecta_percurso_longo():
    rel = validar(sala_unica(distancia=80))
    assert not rel.ok
    assert "excede" in rel.erros[0].mensagem


def test_validacao_alerta_saida_unica():
    rel = validar(sala_unica())
    assert any("uma saída" in p.mensagem for p in rel.problemas)


def test_resiliencia_ordena_pelo_pior_caso():
    impactos = resiliencia(Edificio.de_yaml(EXEMPLOS / "aeroporto.yaml"))
    assert len(impactos) == 4
    pior = impactos[0]
    assert all(pior.variacao_s >= i.variacao_s for i in impactos if i.pessoas_isoladas == 0)
