"""
Django signals for Accounts app.
Auto-creates related models and logs important events.
"""

from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from apps.accounts.models import User, UserProfile, UserAffiliation, EmailVerificationToken, UserProfileImage
from apps.audit.models import AuditLogManager


@receiver(pre_delete, sender=UserProfileImage)
def delete_profile_image_from_cloudinary(_sender, instance, **_kwargs):
    """Delete the Cloudinary asset whenever a UserProfileImage record is removed."""
    if instance.public_id and instance.service == 'cloudinary':
        from apps.core.utils import delete_file_from_cloudinary
        delete_file_from_cloudinary(instance.public_id)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create a UserProfile when a User is created.
    """
    if created:
        # Create profile
        UserProfile.objects.get_or_create(user=instance)
        
        # Create affiliation
        UserAffiliation.objects.get_or_create(user=instance)
        
        # Log creation
        AuditLogManager.log(
            action='user.created',
            actor=instance,
            obj=instance,
            new_values={
                'email': instance.email,
                'first_name': instance.first_name,
                'last_name': instance.last_name,
                'roles': {
                    'author': instance.is_author,
                    'reviewer': instance.is_reviewer,
                    'organiser': instance.is_organiser,
                    'participant': instance.is_participant,
                }
            }
        )


@receiver(post_save, sender=User)
def update_user_audit(sender, instance, created, update_fields, **kwargs):
    """
    Log user updates (excluding creation which is handled separately).
    """
    if not created and update_fields:
        # Don't log internal fields
        skip_fields = {'last_login', 'updated_at'}
        logged_fields = [f for f in update_fields if f not in skip_fields]
        
        if logged_fields:
            AuditLogManager.log(
                action='user.updated',
                actor=instance,
                obj=instance,
                new_values={field: getattr(instance, field) for field in logged_fields}
            )
