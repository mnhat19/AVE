from __future__ import annotations

from typing import Optional


class AveError(Exception):
    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause

    def __str__(self) -> str:
        cause = self.cause or self.__cause__
        if cause:
            return f"{self.message} (cause: {cause})"
        return self.message


class ConfigError(AveError):
    pass


class IngestionError(AveError):
    pass


class RuleValidationError(AveError):
    def __init__(
        self,
        message: str,
        rule_id: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.rule_id = rule_id


class PipelineError(AveError):
    def __init__(
        self,
        message: str,
        layer: Optional[int] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.layer = layer


class LLMError(AveError):
    pass


class LLMUnavailableError(LLMError):
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.provider = provider


class LLMResponseError(LLMError):
    def __init__(
        self,
        message: str,
        raw_response: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.raw_response = raw_response


class StorageError(AveError):
    pass


class TrailError(AveError):
    pass
