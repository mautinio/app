"""Доменные ошибки. Ничего не знают про HTTP — коды ответа назначает слой API."""


class DomainError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    pass


class Conflict(DomainError):
    pass


class InvalidOperation(DomainError):
    pass
