"""Registration service layer."""
import secrets
import logging
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from apps.registrations.models import Registration
from apps.audit.models import AuditLogManager
from apps.communications.notification_service import notification_service

logger = logging.getLogger(__name__)


class RegistrationService:

    @staticmethod
    @transaction.atomic
    def register(user, conference, ticket_type='standard', notes=''):
        """
        Register a participant for a conference.
        - Checks registration is open.
        - Checks capacity: auto-approves if space available, otherwise waitlists.
        - Rejects duplicate registrations.
        """
        if not conference.is_open_for_registration():
            raise ValueError("Registration is not currently open for this conference.")

        if Registration.objects.filter(conference=conference, participant=user).exists():
            raise ValueError("You are already registered for this conference.")

        # Determine initial status based on capacity
        # < 50% full      → auto-approved
        # 50–99% full     → pending (organiser must approve)
        # at/over capacity → waitlisted
        capacity = conference.max_participants
        current_approved = Registration.objects.filter(
            conference=conference, status__in=('approved', 'checked_in')
        ).count()

        if capacity:
            if current_approved >= capacity:
                initial_status = 'waitlisted'
            elif current_approved >= capacity * 0.5:
                initial_status = 'pending'
            else:
                initial_status = 'approved'
        else:
            # No cap set — always auto-approve
            initial_status = 'approved'

        registration = Registration.objects.create(
            conference=conference,
            participant=user,
            status=initial_status,
            ticket_type=ticket_type,
            notes=notes,
            qr_code=secrets.token_urlsafe(32),
        )

        # Ensure the user is flagged as a participant on the platform
        if not user.is_participant:
            user.is_participant = True
            user.save(update_fields=['is_participant'])

        # Update conference participant count when auto-approved
        if initial_status == 'approved':
            from apps.conferences.models import Conference as ConferenceModel
            ConferenceModel.objects.filter(pk=conference.pk).update(
                current_participants=F('current_participants') + 1
            )

        # Notify organiser of new registration
        notification_service.create_notification(
            recipient=conference.organiser,
            notification_type='system',
            title=f'New Registration: {conference.title}',
            message=f'{user.email} has registered for "{conference.title}" ({registration.get_ticket_type_display()}).',
            priority='low',
            related_object=registration,
            send_email=False,
        )

        # Notify organiser with higher priority when manual approval is needed
        if initial_status == 'pending':
            notification_service.create_notification(
                recipient=conference.organiser,
                notification_type='system',
                title=f'Registration Pending Approval: {conference.title}',
                message=f'{user.email} has registered for "{conference.title}" and requires your approval.',
                priority='medium',
                related_object=registration,
                send_email=True,
            )

        # Notify participant
        if initial_status == 'waitlisted':
            msg = f'You are on the waitlist for "{conference.title}". You will be notified if a spot becomes available.'
            title = f'Registration Waitlisted: {conference.title}'
        elif initial_status == 'pending':
            msg = f'Your registration for "{conference.title}" has been received and is pending organiser approval.'
            title = f'Registration Received: {conference.title}'
        else:
            msg = (
                f'Your registration for "{conference.title}" has been approved.\n\n'
                f'Your check-in QR code: {registration.qr_code}\n'
                f'Present this at the venue on the day of the event.'
            )
            title = f'Registration Approved: {conference.title}'
        notification_service.create_notification(
            recipient=user,
            notification_type='system',
            title=title,
            message=msg,
            priority='medium',
            related_object=registration,
            send_email=True,
        )

        AuditLogManager.log(
            action='registration.created',
            actor=user,
            obj=registration,
            new_values={'conference': conference.short_name, 'status': initial_status},
        )
        return registration

    @staticmethod
    @transaction.atomic
    def approve(organiser, registration):
        """Approve a pending or waitlisted registration."""
        if registration.status == 'approved':
            raise ValueError("Registration is already approved.")
        if registration.status in ('cancelled', 'rejected'):
            raise ValueError(f"Cannot approve a {registration.status} registration.")

        # Check capacity again before approving
        conference = registration.conference
        if conference.max_participants:
            approved_count = Registration.objects.filter(
                conference=conference, status__in=('approved', 'checked_in')
            ).exclude(pk=registration.pk).count()
            if approved_count >= conference.max_participants:
                raise ValueError("Conference is at full capacity. Cannot approve.")

        registration.status = 'approved'
        registration.reviewed_by = organiser
        registration.reviewed_at = timezone.now()
        registration.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        # Update conference participant count atomically
        from apps.conferences.models import Conference as ConferenceModel
        ConferenceModel.objects.filter(pk=conference.pk).update(
            current_participants=F('current_participants') + 1
        )

        notification_service.create_notification(
            recipient=registration.participant,
            notification_type='system',
            title=f'Registration Approved: {conference.title}',
            message=(
                f'Your registration for "{conference.title}" has been approved. See you there!\n\n'
                f'Your check-in QR code: {registration.qr_code}\n'
                f'Present this at the venue on the day of the event.'
            ),
            priority='high',
            related_object=registration,
            send_email=True,
        )

        AuditLogManager.log(
            action='registration.approved',
            actor=organiser,
            obj=registration,
            new_values={'status': 'approved'},
        )
        return registration

    @staticmethod
    @transaction.atomic
    def reject(organiser, registration, reason=''):
        """Reject a registration."""
        if registration.status in ('cancelled', 'checked_in'):
            raise ValueError(f"Cannot reject a {registration.status} registration.")

        registration.status = 'rejected'
        registration.reviewed_by = organiser
        registration.reviewed_at = timezone.now()
        registration.rejection_reason = reason
        registration.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])

        notification_service.create_notification(
            recipient=registration.participant,
            notification_type='system',
            title=f'Registration Update: {registration.conference.title}',
            message=(
                f'Your registration for "{registration.conference.title}" was not approved.'
                + (f' Reason: {reason}' if reason else '')
            ),
            priority='high',
            related_object=registration,
            send_email=True,
        )

        AuditLogManager.log(
            action='registration.rejected',
            actor=organiser,
            obj=registration,
            new_values={'status': 'rejected'},
            reason=reason,
        )
        return registration

    @staticmethod
    @transaction.atomic
    def cancel(user, registration):
        """Participant cancels their own registration."""
        if registration.status in ('cancelled', 'checked_in'):
            raise ValueError(f"Cannot cancel a {registration.status} registration.")

        registration.status = 'cancelled'
        registration.save(update_fields=['status'])

        conference = registration.conference
        # Only decrement if this registration was counted (approved or checked_in before cancel)
        from apps.conferences.models import Conference as ConferenceModel
        ConferenceModel.objects.filter(
            pk=conference.pk, current_participants__gt=0
        ).update(current_participants=F('current_participants') - 1)

        # Promote first waitlisted person if capacity allows
        RegistrationService._promote_from_waitlist(conference)

        AuditLogManager.log(
            action='registration.cancelled',
            actor=user,
            obj=registration,
        )
        return registration

    @staticmethod
    @transaction.atomic
    def check_in(actor, registration):
        """
        Mark a participant as checked in.
        Actor can be organiser (manual) or the system (QR scan).
        """
        if registration.status != 'approved':
            raise ValueError(
                f"Only approved participants can check in. Status is '{registration.status}'."
            )

        registration.checked_in = True
        registration.checked_in_at = timezone.now()
        registration.checked_in_by = actor if actor != registration.participant else None
        registration.status = 'checked_in'
        registration.save(update_fields=['checked_in', 'checked_in_at', 'checked_in_by', 'status'])

        AuditLogManager.log(
            action='registration.checked_in',
            actor=actor,
            obj=registration,
            new_values={'checked_in_at': str(registration.checked_in_at)},
        )
        return registration

    @staticmethod
    def check_in_by_qr(actor, qr_token):
        """Check in a participant using their QR code token."""
        try:
            registration = Registration.objects.select_related(
                'conference', 'participant'
            ).get(qr_code=qr_token)
        except Registration.DoesNotExist:
            raise ValueError("Invalid QR code.")
        return RegistrationService.check_in(actor, registration)

    @staticmethod
    def bulk_update_status(organiser, registration_ids, target_status, reason=''):
        """
        Bulk approve or reject a list of registrations.
        Each registration is processed independently — one failure does not
        block the others. Returns a summary of updated/failed IDs.
        """
        # Scope to registrations the organiser owns
        if organiser.is_admin or organiser.is_superuser:
            qs = Registration.objects.filter(pk__in=registration_ids)
        else:
            qs = Registration.objects.filter(
                pk__in=registration_ids,
                conference__organiser=organiser,
            )
        qs = qs.select_related('conference', 'participant')

        found = {str(r.pk): r for r in qs}
        updated = []
        failed = []

        for rid in registration_ids:
            key = str(rid)
            if key not in found:
                failed.append({'id': key, 'error': 'Not found or access denied.'})
                continue
            registration = found[key]
            try:
                if target_status == 'approved':
                    RegistrationService.approve(organiser, registration)
                elif target_status == 'rejected':
                    RegistrationService.reject(organiser, registration, reason=reason)
                updated.append(key)
            except ValueError as e:
                failed.append({'id': key, 'error': str(e)})

        return {
            'updated_count': len(updated),
            'failed_count': len(failed),
            'updated': updated,
            'failed': failed,
        }

    @staticmethod
    def _promote_from_waitlist(conference):
        """Promote the next waitlisted registration if a spot opens up."""
        if conference.max_participants:
            approved = Registration.objects.filter(
                conference=conference, status__in=('approved', 'checked_in')
            ).count()
            if approved < conference.max_participants:
                next_waitlisted = Registration.objects.filter(
                    conference=conference, status='waitlisted'
                ).order_by('registered_at').first()
                if next_waitlisted:
                    next_waitlisted.status = 'approved'
                    next_waitlisted.save(update_fields=['status'])
                    from apps.conferences.models import Conference as ConferenceModel
                    ConferenceModel.objects.filter(pk=conference.pk).update(
                        current_participants=F('current_participants') + 1
                    )
                    notification_service.create_notification(
                        recipient=next_waitlisted.participant,
                        notification_type='system',
                        title=f'Spot Available: {conference.title}',
                        message=(
                            f'A spot has opened up and your registration for "{conference.title}" is now approved!\n\n'
                            f'Your check-in QR code: {next_waitlisted.qr_code}\n'
                            f'Present this at the venue on the day of the event.'
                        ),
                        priority='high',
                        related_object=next_waitlisted,
                        send_email=True,
                    )
