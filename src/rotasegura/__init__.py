"""Rota Segura: mapeamento de rotas de fuga em edifícios."""

from .analise import estimar_evacuacao, resiliencia, validar
from .modelo import Edificio, ErroModelo
from .motor import Cenario, Perfil, calcular_plano

__all__ = [
           "Cenario",
           "Edificio",
           "ErroModelo",
           "Perfil",
           "calcular_plano",
           "estimar_evacuacao",
           "resiliencia",
           "validar",
]
__version__ = "0.1.0"
