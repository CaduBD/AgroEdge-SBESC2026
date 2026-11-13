"""Adaptadores de mensagem. Cada um traduz o seu canal para o núcleo (`nucleo.servico`)."""


class ErroCanal(Exception):
    """Falha ao iniciar o canal, com mensagem pronta para quem roda o bot."""
