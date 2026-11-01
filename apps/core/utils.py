"""
Utility functions for common operations across the system.
"""

import secrets
import string
from datetime import datetime, timedelta
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
import cloudinary
import cloudinary.uploader


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a secure random token.
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))


def upload_file_to_cloudinary(file_obj, folder: str = 'k-conference', public_id: str = None):
    """
    Upload a file to Cloudinary.

    Args:
        file_obj: Django UploadedFile object
        folder: Folder path in Cloudinary
        public_id: Optional explicit public ID

    Returns:
        dict: Upload response with public_id, url, width, height.

    Raises:
        ValueError: If the upload fails.
    """
    cloudinary.config(**settings.CLOUDINARY_CONFIG)

    upload_kwargs = {'folder': folder, 'resource_type': 'auto'}
    if public_id:
        upload_kwargs['public_id'] = public_id

    result = cloudinary.uploader.upload(file_obj, **upload_kwargs)

    url = result.get('secure_url') or result.get('url')
    if not url:
        raise ValueError("Cloudinary returned no URL for the uploaded file.")

    return {
        'public_id': result.get('public_id'),
        'url': url,
        'width': result.get('width'),
        'height': result.get('height'),
        'size': result.get('bytes'),
    }


def delete_file_from_cloudinary(public_id: str) -> bool:
    """
    Delete a file from Cloudinary.
    """
    try:
        cloudinary.uploader.destroy(public_id)
        return True
    except Exception:
        return False


def send_email_template(
    subject: str,
    template_name: str,
    context: dict,
    recipient_list: list,
    from_email: str = None,
) -> bool:
    """
    Send an email using a template.
    Uses the configured email service provider.
    
    Args:
        subject: Email subject
        template_name: Name of the template file (e.g., 'emails/verification.html')
        context: Context variables for template rendering
        recipient_list: List of recipient email addresses
        from_email: Sender email (uses DEFAULT_FROM_EMAIL if not provided)
    
    Returns:
        bool: True if email sent successfully
    """
    from apps.core.email_service import email_service
    return email_service.send_template(subject, template_name, context, recipient_list, from_email)


def is_deadline_passed(deadline: datetime) -> bool:
    """
    Check if a deadline has passed.
    """
    return timezone.now() > deadline


def get_time_until_deadline(deadline: datetime) -> timedelta:
    """
    Get the time remaining until a deadline.
    """
    return deadline - timezone.now()


def paginate_queryset(queryset, page: int = 1, page_size: int = 20):
    """
    Paginate a queryset.
    
    Returns:
        tuple: (items, total_count, has_next, has_previous)
    """
    total = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    
    items = queryset[start:end]
    has_next = end < total
    has_previous = page > 1
    
    return items, total, has_next, has_previous
