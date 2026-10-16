"""Interface de linha de comando: `rotasegura <comando> edificio.yaml [opções]`."""

from __future__ import annotations

import argparse
import sys

from . import analise, render
from .modelo import Edificio, ErroModelo
from .motor import Cenario, Perfil, calcular_plano


def _lista(valor: str | None) -> set[str]:
    return {v.strip() for v in valor.split(",") if v.strip()} if valor else set()


def _fmt_tempo(segundos: float) -> str:
    if segundos == float("inf"):
        return "sem rota"
    m, s = divmod(round(segundos), 60)
    return f"{m}min{s:02d}s" if m else f"{s}s"


def _plano(args):
    ed = Edificio.de_yaml(args.arquivo)
    cenario = Cenario(bloqueados=_lista(args.fogo), fumaca=_lista(args.fumaca))
    return ed, calcular_plano(ed, cenario, Perfil(args.perfil))


def cmd_rota(args) -> int:
    _, plano = _plano(args)
    rota = plano.rota(args.origem)
    if not rota.alcancavel:
        print(f"ATENÇÃO: {args.origem} não tem rota de fuga neste cenário.")
        return 2
    print(" -> ".join(rota.caminho))
    print(f"Destino: {rota.destino} | {rota.distancia_m:.1f} m | {_fmt_tempo(rota.tempo_s)}")
    if rota.passa_por_fumaca:
        print("Aviso: a melhor rota disponível atravessa área com fumaça.")
    return 0


def cmd_evacuacao(args) -> int:
    ed, plano = _plano(args)
    est = analise.estimar_evacuacao(plano, pre_movimento_s=args.pre_movimento)
    print(f"{ed.nome} | {ed.ocupacao_total} ocupantes | pré-movimento {_fmt_tempo(est.pre_movimento_s)}")
    print(f"{'saída':<22}{'pessoas':>8}{'pess/s':>8}{'fila':>10}{'término':>10}")
    for r in est.por_saida:
        print(f"{r.saida:<22}{r.pessoas:>8}{r.capacidade_pps:>8.1f}"
              f"{_fmt_tempo(r.fila_s):>10}{_fmt_tempo(r.tempo_final_s):>10}")
    print(f"Tempo total estimado: {_fmt_tempo(est.tempo_total_s)}")
    if est.gargalo:
        print(f"Gargalo: {est.gargalo.saida}")
    if est.pessoas_sem_rota:
        print(f"ATENÇÃO: {est.pessoas_sem_rota} pessoas sem rota de fuga.")
        return 2
    return 0


def cmd_mapa(args) -> int:
    _, plano = _plano(args)
    caminho = render.salvar(plano, args.saida, destaque=args.origem)
    print(f"Mapa salvo em {caminho}")
    return 0


def cmd_validar(args) -> int:
    ed = Edificio.de_yaml(args.arquivo)
    rel = analise.validar(ed)
    for p in rel.problemas:
        print(f"[{p.nivel.upper()}] {p.mensagem}")
    print("Projeto aprovado nas verificações automáticas." if rel.ok else
          f"{len(rel.erros)} erro(s) encontrados.")
    return 0 if rel.ok else 1


def cmd_resiliencia(args) -> int:
    ed = Edificio.de_yaml(args.arquivo)
    for imp in analise.resiliencia(ed):
        linha = f"Sem {imp.saida:<20} tempo {_fmt_tempo(imp.tempo_total_s):>8} ({imp.variacao_s:+.0f}s)"
        if imp.pessoas_isoladas:
            linha += f" | {imp.pessoas_isoladas} pessoas isoladas: {', '.join(imp.nos_isolados)}"
        print(linha)
    return 0


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rotasegura", description="Mapeamento de rotas de fuga em edifícios.")
    sub = p.add_subparsers(dest="comando", required=True)

    def comum(sp, com_cenario=True):
        sp.add_argument("arquivo", help="arquivo YAML do edifício")
        if com_cenario:
            sp.add_argument("--fogo", help="nós tomados pelo fogo, separados por vírgula")
            sp.add_argument("--fumaca", help="nós com fumaça, separados por vírgula")
            sp.add_argument("--perfil", default="padrao", choices=[x.value for x in Perfil])

    sp = sub.add_parser("rota", help="melhor rota a partir de um ambiente")
    comum(sp)
    sp.add_argument("--origem", required=True)
    sp.set_defaults(func=cmd_rota)

    sp = sub.add_parser("evacuacao", help="estima o tempo de evacuação total")
    comum(sp)
    sp.add_argument("--pre-movimento", type=float, default=60.0, help="segundos (padrão 60)")
    sp.set_defaults(func=cmd_evacuacao)

    sp = sub.add_parser("mapa", help="gera PNG/SVG com as rotas")
    comum(sp)
    sp.add_argument("--saida", "-o", default="mapa.png")
    sp.add_argument("--origem", help="destaca a rota deste ambiente")
    sp.set_defaults(func=cmd_mapa)

    sp = sub.add_parser("validar", help="verifica problemas no projeto")
    comum(sp, com_cenario=False)
    sp.set_defaults(func=cmd_validar)

    sp = sub.add_parser("resiliencia", help="simula o bloqueio de cada saída")
    comum(sp, com_cenario=False)
    sp.set_defaults(func=cmd_resiliencia)
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ErroModelo, KeyError, FileNotFoundError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
