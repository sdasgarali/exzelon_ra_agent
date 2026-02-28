"""Custom application exceptions with structured error codes."""
from fastapi import HTTPException


class AppException(HTTPException):
    """Base application exception with error code support."""

    def __init__(self, status_code: int, detail: str, error_code: str = "UNKNOWN_ERROR"):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str | int):
        super().__init__(
            status_code=404,
            detail=f"{resource} not found: {identifier}",
            error_code="NOT_FOUND"
        )


class ValidationError(AppException):
    """Validation error."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=400,
            detail=detail,
            error_code="VALIDATION_ERROR"
        )


class DuplicateError(AppException):
    """Duplicate resource error."""

    def __init__(self, resource: str, field: str, value: str):
        super().__init__(
            status_code=400,
            detail=f"{resource} with {field} '{value}' already exists",
            error_code="DUPLICATE"
        )


class PermissionError(AppException):
    """Permission denied."""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=403,
            detail=detail,
            error_code="PERMISSION_DENIED"
        )


class BulkOperationError(AppException):
    """Error during bulk operation."""

    def __init__(self, operation: str, detail: str):
        super().__init__(
            status_code=500,
            detail=f"Bulk {operation} failed: {detail}",
            error_code="BULK_OPERATION_ERROR"
        )
