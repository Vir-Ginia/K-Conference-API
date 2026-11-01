"""
Custom Exception Handler for DRF
Provides consistent error responses across the API.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns consistent error format.
    """
    response = exception_handler(exc, context)
    
    if response is None:
        # Log unhandled exceptions
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return Response(
            {
                'success': False,
                'error': 'Internal server error',
                'detail': 'An unexpected error occurred. Please try again later.',
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # Wrap response in consistent format
    if 'detail' in response.data:
        detail = response.data['detail']
    else:
        detail = response.data
    
    response.data = {
        'success': False,
        'error': exc.__class__.__name__,
        'detail': detail,
    }
    
    return response


class APIException(Exception):
    """Base exception for API errors."""
    
    def __init__(self, message, code=None, status_code=status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.code = code or self.__class__.__name__
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(APIException):
    """Validation error."""
    
    def __init__(self, message, code='validation_error'):
        super().__init__(message, code, status.HTTP_400_BAD_REQUEST)


class AuthenticationFailed(APIException):
    """Authentication failed."""
    
    def __init__(self, message='Authentication failed', code='authentication_failed'):
        super().__init__(message, code, status.HTTP_401_UNAUTHORIZED)


class PermissionDenied(APIException):
    """Permission denied."""
    
    def __init__(self, message='Permission denied', code='permission_denied'):
        super().__init__(message, code, status.HTTP_403_FORBIDDEN)


class NotFound(APIException):
    """Resource not found."""
    
    def __init__(self, message='Not found', code='not_found'):
        super().__init__(message, code, status.HTTP_404_NOT_FOUND)


class ConflictError(APIException):
    """Conflict error."""
    
    def __init__(self, message, code='conflict'):
        super().__init__(message, code, status.HTTP_409_CONFLICT)
