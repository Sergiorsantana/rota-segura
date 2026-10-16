from pathlib import Path

import pytest

from rotasegura import Cenario, Edificio, ErroModelo, Perfil, calcular_plano

EXEMPLOS = Path(__file__).parents[1] / "exemplos"


def corredor_simples():
    """A -- B -- C com saídas nas duas pontas."""
    return Edificio.de_dict({
        "nome": "Teste", "andares": [{"id": "T"}],
        "nos": [
            {"id": "s1", "andar": "T", "tipo": "saida", "x": 0, "y": 0},
            {"id": "a", "andar": "T", "tipo": "corredor", "x": 10, "y": 0},
            {"id": "b", "andar": "T", "tipo": "sala", "x": 20, "y": 0, "ocupacao": 10},
            {"id": "c", "andar": "T", "tipo": "corredor", "x": 50, "y": 0},
            {"id": "s2", "andar": "T", "tipo": "saida", "x": 60, "y": 0},
        ],
        "conexoes": [
            {"de": "s1", "para": "a"}, {"de": "a", "para": "b"},
            {"de": "b", "para": "c"}, {"de": "c", "para": "s2"},
        ],
    })


def test_escolhe_saida_mais_proxima():
    rota = calcular_plano(corredor_simples()).rota("b")
    assert rota.caminho == ["b", "a", "s1"]
    assert rota.distancia_m == pytest.approx(20)
    assert rota.tempo_s == pytest.approx(20 / 1.2)


def test_fogo_desvia_para_outra_saida():
    plano = calcular_plano(corredor_simples(), Cenario(bloqueados={"a"}))
    assert plano.rota("b").caminho == ["b", "c", "s2"]


def test_fumaca_penaliza_mas_nao_bloqueia():
    plano = calcular_plano(corredor_simples(), Cenario(fumaca={"c"}, penalidade_fumaca=10))
    assert plano.rota("b").destino == "s1"
    rota_c = plano.rota("c")
    assert rota_c.alcancavel and rota_c.passa_por_fumaca


def test_sem_rota_quando_tudo_bloqueado():
    plano = calcular_plano(corredor_simples(), Cenario(bloqueados={"a", "c"}))
    assert not plano.rota("b").alcancavel
    assert "b" in plano.nos_sem_rota()


def test_cenario_com_no_inexistente():
    with pytest.raises(KeyError):
        calcular_plano(corredor_simples(), Cenario(bloqueados={"xyz"}))


def test_mobilidade_reduzida_nao_usa_escada_e_vai_para_refugio():
    ed = Edificio.de_yaml(EXEMPLOS / "universidade.yaml")
    padrao = calcular_plano(ed).rota("s201")
    pcd = calcular_plano(ed, perfil=Perfil.MOBILIDADE_REDUZIDA).rota("s201")
    assert padrao.destino.startswith("saida")
    assert pcd.destino == "refugio_1"
    assert not any(n.startswith("esc") for n in pcd.caminho)


def test_rampa_permite_cadeirante_sair_do_hospital():
    ed = Edificio.de_yaml(EXEMPLOS / "hospital.yaml")
    plano = calcular_plano(ed, Cenario(bloqueados={"h13"}), Perfil.MOBILIDADE_REDUZIDA)
    rota = plano.rota("enf_a")
    assert "rampa_1" in rota.caminho and rota.destino == "entrada"


def test_elevador_nunca_entra_na_rota():
    ed = Edificio.de_yaml(EXEMPLOS / "universidade.yaml")
    plano = calcular_plano(ed)
    for no in ed.nos:
        assert not any(n.startswith("elev") for n in plano.rota(no).caminho[1:])


@pytest.mark.parametrize("arquivo", sorted(EXEMPLOS.glob("*.yaml")), ids=lambda p: p.stem)
def test_exemplos_tem_rota_para_todos(arquivo):
    plano = calcular_plano(Edificio.de_yaml(arquivo))
    assert plano.nos_sem_rota() == []


@pytest.mark.parametrize("alteracao, trecho", [
    (lambda d: d["nos"].append(dict(d["nos"][0])), "duplicado"),
    (lambda d: d["nos"][0].update(tipo="banheiro"), "Tipo de nó"),
    (lambda d: d["conexoes"].append({"de": "a", "para": "zz"}), "inexistente"),
    (lambda d: d["conexoes"][0].update(largura=0), "Largura"),
    (lambda d: d.pop("andares"), "obrigatório"),
])
def test_erros_de_modelo(alteracao, trecho):
    dados = {
        "nome": "X", "andares": [{"id": "T"}],
        "nos": [{"id": "a", "andar": "T", "tipo": "sala", "x": 0, "y": 0},
                {"id": "s", "andar": "T", "tipo": "saida", "x": 1, "y": 0}],
        "conexoes": [{"de": "a", "para": "s"}],
    }
    alteracao(dados)
    with pytest.raises(ErroModelo, match=trecho):
        Edificio.de_dict(dados)
