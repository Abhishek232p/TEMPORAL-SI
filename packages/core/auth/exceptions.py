class AuthException(Exception):
    pass

class UnauthorizedException(AuthException):
    pass

class ForbiddenException(AuthException):
    pass
