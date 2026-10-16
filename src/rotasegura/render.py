"""Gera o mapa de rotas de fuga (PNG/SVG) com matplotlib, um painel por andar."""

from __future__ import annotations

import io
import math
from itertools import pairwise
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .motor import Plano

CORES = {
    "sala": "#4b5563",
    "corredor": "#9ca3af",
    "escada": "#7c3aed",
    "elevador": "#d1d5db",
    "saida": "#15803d",
    "area_refugio": "#0369a1",
}
ROTULO_PERFIL = {"padrao": "perfil padrão", "mobilidade_reduzida": "mobilidade reduzida"}
MARCADOR = {"sala": "s", "corredor": "o", "escada": "^", "elevador": "x",
            "saida": "s", "area_refugio": "D"}


def desenhar(plano: Plano, destaque: str | None = None, titulo: str | None = None):
    ed = plano.edificio
    andares = sorted(ed.andares.values(), key=lambda a: a.elevacao, reverse=True)
    n = len(andares)
    xs = [no.x for no in ed.nos.values()]
    ys = [no.y for no in ed.nos.values()]
    proporcao = (max(ys) - min(ys) + 6) / (max(xs) - min(xs) + 6)
    # Plantas largas ficam empilhadas; plantas compactas lado a lado.
    colunas = 1 if proporcao < 0.6 else min(n, 2)
    linhas = math.ceil(n / colunas)
    largura = 13 if colunas == 1 else 8 * colunas
    altura_painel = max(3.2, min(7.0, (largura / colunas) * proporcao + 1.2))
    fig, eixos = plt.subplots(linhas, colunas, figsize=(largura, altura_painel * linhas + 0.9),
                              squeeze=False)

    fumaca = plano.cenario.nos_com_fumaca(ed)
    rota_destaque = set()
    if destaque:
        caminho = plano.rota(destaque).caminho
        rota_destaque = set(pairwise(caminho))

    for idx, andar in enumerate(andares):
        ax = eixos[idx // colunas][idx % colunas]
        ids = {no.id for no in ed.nos_do_andar(andar.id)}

        for c in ed.conexoes:
            if c.de in ids and c.para in ids:
                a, b = ed.nos[c.de], ed.nos[c.para]
                ax.plot([a.x, b.x], [a.y, b.y], color="#e5e7eb", lw=2 + 2 * c.largura, zorder=1,
                        solid_capstyle="round")

        for nid in ids:
            seguinte = plano.proximo.get(nid)
            if seguinte is None or seguinte not in ids:
                continue
            a, b = ed.nos[nid], ed.nos[seguinte]
            na_rota = (nid, seguinte) in rota_destaque
            ax.annotate("", xy=(b.x, b.y), xytext=(a.x, a.y), zorder=3,
                        arrowprops={"arrowstyle": "-|>", "lw": 3 if na_rota else 1.6,
                                    "color": "#2563eb" if na_rota else "#16a34a",
                                    "shrinkA": 7, "shrinkB": 7})

        for nid in ids:
            no = ed.nos[nid]
            if nid in fumaca:
                ax.scatter(no.x, no.y, s=900, color="#fb923c", alpha=0.35, zorder=2, lw=0)
            if nid in plano.cenario.bloqueados:
                ax.scatter(no.x, no.y, s=700, color="#dc2626", alpha=0.85, zorder=2, lw=0)
            ax.scatter(no.x, no.y, s=140 if no.tipo in ("saida", "area_refugio") else 70,
                       marker=MARCADOR[no.tipo], color=CORES[no.tipo], zorder=4)
            sufixo = f" ({no.ocupacao})" if no.ocupacao else ""
            if no.tipo == "escada":
                destinos = [v for v, _ in ed.vizinhos(nid) if v not in ids]
                if plano.proximo.get(nid) in destinos:
                    sufixo += " ↓"
            if no.tipo != "corredor" or no.nome:
                ax.annotate(no.rotulo + sufixo, (no.x, no.y), textcoords="offset points",
                            xytext=(0, 9), ha="center", fontsize=7.5, zorder=5)

        ax.set_title(andar.nome, fontsize=11, loc="left")
        ax.set_aspect("equal")
        ax.margins(0.06, 0.18)
        ax.set_xticks([])
        ax.set_yticks([])
        for lado in ax.spines.values():
            lado.set_visible(False)

    for idx in range(n, linhas * colunas):
        eixos[idx // colunas][idx % colunas].axis("off")

    legenda = [
        Line2D([], [], marker="s", ls="", color=CORES["saida"], label="Saída"),
        Line2D([], [], marker="D", ls="", color=CORES["area_refugio"], label="Área de refúgio"),
        Line2D([], [], marker="^", ls="", color=CORES["escada"], label="Escada"),
        Line2D([], [], color="#16a34a", lw=1.6, label="Sentido de fuga"),
        Line2D([], [], marker="o", ls="", color="#dc2626", ms=10, label="Foco de incêndio"),
        Line2D([], [], marker="o", ls="", color="#fb923c", alpha=0.5, ms=10, label="Fumaça"),
    ]
    if destaque:
        legenda.append(Line2D([], [], color="#2563eb", lw=3, label=f"Rota de {ed.nos[destaque].rotulo}"))
    fig.legend(handles=legenda, loc="lower center", ncol=len(legenda), frameon=False, fontsize=9)
    fig.suptitle(titulo or f"{ed.nome} · {ROTULO_PERFIL[plano.perfil.value]}", fontsize=13, x=0.02,
                 ha="left")
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    return fig


def salvar(plano: Plano, caminho: str | Path, destaque: str | None = None) -> Path:
    fig = desenhar(plano, destaque)
    caminho = Path(caminho)
    fig.savefig(caminho, dpi=130)
    plt.close(fig)
    return caminho


def png_em_bytes(plano: Plano, destaque: str | None = None) -> bytes:
    fig = desenhar(plano, destaque)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return buf.getvalue()
