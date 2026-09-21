"""Модуль middleware для авторизации и сессий БД"""
from .auth import AccessMiddleware

__all__ = ["AccessMiddleware"]
