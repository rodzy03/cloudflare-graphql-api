
import logging

class HttpErrorLogManager:
    """
    Manages logging for HTTP 400- and 500-series error responses.
    """

    def __init__(self, file_400: str, file_500: str):
        self.response_logger_500 = self._create_logger('response_logger_500', file_500)
        self.response_logger_400 = self._create_logger('response_logger_400', file_400)

    def _create_logger(self, name: str, file: str) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(logging.ERROR)
        handler = logging.FileHandler(file)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def log_error(self, status_code: int, message: str):
        if 400 <= status_code < 500:
            self.response_logger_400.error(message)
        elif 500 <= status_code < 600:
            self.response_logger_500.error(message)

    @staticmethod
    def create(file_400: str = 'error_400.log', file_500: str = 'error_500.log'):
        return HttpErrorLogManager(file_400, file_500)
