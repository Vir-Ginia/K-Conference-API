"""
Abstract Email Service
Allows switching between different email providers (Gmail, SendGrid, etc.)
without changing application code.
"""

from abc import ABC, abstractmethod
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    """
    Abstract base class for email providers.
    Implement this to add support for different email services.
    """
    
    @abstractmethod
    def send(self, subject: str, body: str, recipient_list: list, from_email: str = None) -> bool:
        """
        Send an email.
        
        Args:
            subject: Email subject
            body: Email body (HTML or plain text)
            recipient_list: List of recipient email addresses
            from_email: Sender email address
        
        Returns:
            bool: True if sent successfully
        """
        pass


class SMTPEmailProvider(EmailProvider):
    """
    Gmail/Standard SMTP email provider.
    Uses Django's built-in SMTP backend.
    """
    
    def send(self, subject: str, body: str, recipient_list: list, from_email: str = None) -> bool:
        """
        Send email via SMTP.
        """
        try:
            from_email = from_email or settings.DEFAULT_FROM_EMAIL
            send_mail(
                subject,
                body,
                from_email,
                recipient_list,
                html_message=body,
                fail_silently=False,
            )
            logger.info(f"Email sent to {recipient_list} via SMTP")
            return True
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")
            return False


class SendGridEmailProvider(EmailProvider):
    """
    SendGrid email provider.
    Requires: pip install sendgrid
    Set SENDGRID_API_KEY in environment variables.
    """
    
    def send(self, subject: str, body: str, recipient_list: list, from_email: str = None) -> bool:
        """
        Send email via SendGrid.
        """
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
            
            from_email = from_email or settings.DEFAULT_FROM_EMAIL
            
            for recipient in recipient_list:
                msg = Mail(
                    from_email=from_email,
                    to_emails=recipient,
                    subject=subject,
                    html_content=body,
                )
                
                sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
                sg.send(msg)
            
            logger.info(f"Email sent to {recipient_list} via SendGrid")
            return True
        except Exception as e:
            logger.error(f"Failed to send email via SendGrid: {e}")
            return False


class EmailService:
    """
    Email service factory that uses configured provider.
    Abstracts away provider implementation.
    """
    
    # Provider mapping
    PROVIDERS = {
        'smtp': SMTPEmailProvider,
        'sendgrid': SendGridEmailProvider,
    }
    
    _instance = None
    _provider = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Initialize provider based on settings
            provider_name = getattr(settings, 'EMAIL_PROVIDER', 'smtp').lower()
            provider_class = cls.PROVIDERS.get(provider_name, SMTPEmailProvider)
            cls._provider = provider_class()
        return cls._instance
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type):
        """
        Register a custom email provider.
        
        Example:
            EmailService.register_provider('custom', MyCustomEmailProvider)
        """
        cls.PROVIDERS[name.lower()] = provider_class
    
    def send(self, subject: str, body: str, recipient_list: list, from_email: str = None) -> bool:
        """
        Send an email using the configured provider.
        """
        return self._provider.send(subject, body, recipient_list, from_email)
    
    def send_template(
        self,
        subject: str,
        template_name: str,
        context: dict,
        recipient_list: list,
        from_email: str = None,
    ) -> bool:
        """
        Send an email using a Django template.
        
        Args:
            subject: Email subject
            template_name: Path to email template (e.g., 'emails/verify_email.html')
            context: Context variables for template rendering
            recipient_list: List of recipient email addresses
            from_email: Sender email (uses DEFAULT_FROM_EMAIL if not provided)
        
        Returns:
            bool: True if email sent successfully
        """
        try:
            html_message = render_to_string(template_name, context)
            return self.send(subject, html_message, recipient_list, from_email)
        except Exception as e:
            logger.error(f"Failed to send template email: {e}")
            return False
    
    def send_bulk(
        self,
        subject: str,
        body: str,
        recipient_list: list,
        from_email: str = None,
        fail_silently: bool = True,
    ) -> tuple:
        """
        Send emails in bulk.
        
        Args:
            subject: Email subject
            body: Email body
            recipient_list: List of recipients
            from_email: Sender email
            fail_silently: If True, continue sending even if some fail
        
        Returns:
            tuple: (successful_count, failed_list)
        """
        successful = 0
        failed = []
        
        for recipient in recipient_list:
            try:
                if self.send(subject, body, [recipient], from_email):
                    successful += 1
                else:
                    failed.append(recipient)
            except Exception as e:
                logger.error(f"Failed to send to {recipient}: {e}")
                if not fail_silently:
                    raise
                failed.append(recipient)
        
        return successful, failed


# Singleton instance
email_service = EmailService()
