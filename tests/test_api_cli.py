from pathlib import Path

from fastapi.testclient import TestClient

from rotasegura.api import app
from rotasegura.cli import main

EXEMPLOS = Path(__file__).parents[1] / "exemplos"
cliente = TestClient(app)


def test_lista_edificios():
    ids = {e["id"] for e in cliente.get("/edificios").json()}
    assert {"universidade", "hospital", "aeroporto"} <= ids


def test_rota_com_fogo():
    r = cliente.get("/edificios/universidade/rota",
                    params={"origem": "s101", "fogo": ["cT2"]}).json()
    assert r["alcancavel"] and "cT2" not in r["caminho"]


def test_plano_completo():
    r = cliente.post("/edificios/hospital/plano", json={"fogo": ["hT2"]}).json()
    assert r["tempo_total_s"] > 0
    assert r["pessoas_sem_rota"] == 0
    assert "uti" in r["rotas"]


def test_mapa_png():
    r = cliente.get("/edificios/aeroporto/mapa.png", params={"fogo": "hall2"})
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


def test_erros_da_api():
    assert cliente.get("/edificios/nao_existe/rota", params={"origem": "x"}).status_code == 404
    assert cliente.get("/edificios/../pyproject/rota", params={"origem": "x"}).status_code == 404
    r = cliente.post("/edificios/hospital/plano", json={"fogo": ["inexistente"]})
    assert r.status_code == 422


def test_plano_avulso():
    edificio = {"nome": "Mini", "andares": [{"id": "T"}],
                "nos": [{"id": "a", "andar": "T", "tipo": "sala", "x": 0, "y": 0, "ocupacao": 5},
                        {"id": "s", "andar": "T", "tipo": "saida", "x": 6, "y": 0}],
                "conexoes": [{"de": "a", "para": "s"}]}
    r = cliente.post("/plano", json={"edificio": edificio}).json()
    assert r["rotas"]["a"]["caminho"] == ["a", "s"]
    assert cliente.post("/plano", json={"edificio": {"nome": "x"}}).status_code == 422


def test_cli(tmp_path, capsys):
    arq = str(EXEMPLOS / "universidade.yaml")
    assert main(["rota", arq, "--origem", "s201", "--fogo", "c13"]) == 0
    assert "->" in capsys.readouterr().out
    assert main(["evacuacao", arq]) == 0
    assert main(["validar", arq]) == 0
    assert main(["resiliencia", arq]) == 0
    destino = tmp_path / "m.png"
    assert main(["mapa", arq, "-o", str(destino)]) == 0 and destino.exists()
    assert main(["rota", arq, "--origem", "nao_existe"]) == 1
