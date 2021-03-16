class CaseSearchException(Exception):
    pass


class CaseSearchNotEnabledException(CaseSearchException):
    pass


class TooManyRelatedCasesException(CaseSearchException):
    pass


class UnsupportedQueryException(CaseSearchException):
    pass
