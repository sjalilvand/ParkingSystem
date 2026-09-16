class AppException(Exception):
    status_code = 400
    code = "APP_ERROR"
    message = "خطای نامشخص رخ داد"

    def __init__(self, message: str | None = None, details: dict | None = None):
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppException):
    status_code = 404
    code = "NOT_FOUND"
    message = "موردی یافت نشد"


class UnauthorizedError(AppException):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "احراز هویت ناموفق بود"


class ForbiddenError(AppException):
    status_code = 403
    code = "FORBIDDEN"
    message = "دسترسی مجاز نیست"


class ConflictError(AppException):
    status_code = 409
    code = "CONFLICT"
    message = "تضاد در داده‌ها"