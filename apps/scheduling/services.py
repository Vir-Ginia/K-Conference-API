"""Scheduling service layer."""
import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.scheduling.models import Session, SessionPresentation
from apps.audit.models import AuditLogManager

logger = logging.getLogger(__name__)


class SchedulingService:

    @staticmethod
    def _check_room_overlap(conference, room, start, end, exclude_pk=None):
        """Raise ValueError if another session occupies the same room at the same time."""
        if not room or not start or not end:
            return
        qs = Session.objects.filter(
            conference=conference,
            room=room,
            status__in=('draft', 'published'),
            start_time__lt=end,
            end_time__gt=start,
        )
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if qs.exists():
            raise ValueError(
                f"Room '{room}' is already booked for another session during that time slot."
            )

    @staticmethod
    @transaction.atomic
    def create_session(organiser, validated_data):
        """Create a session. Validates time range and conference ownership."""
        conference = validated_data['conference']
        start = validated_data.get('start_time')
        end = validated_data.get('end_time')

        if start and end and end <= start:
            raise ValueError("Session end time must be after start time.")

        SchedulingService._check_room_overlap(
            conference, validated_data.get('room', ''), start, end
        )

        session = Session.objects.create(**validated_data)

        AuditLogManager.log(
            action='schedule.session.created',
            actor=organiser,
            obj=session,
            new_values={
                'title': session.title,
                'conference': conference.short_name,
                'start_time': str(start),
                'session_type': session.session_type,
            }
        )
        return session

    @staticmethod
    @transaction.atomic
    def update_session(organiser, session, validated_data):
        start = validated_data.get('start_time', session.start_time)
        end = validated_data.get('end_time', session.end_time)

        if start and end and end <= start:
            raise ValueError("Session end time must be after start time.")

        room = validated_data.get('room', session.room)
        SchedulingService._check_room_overlap(
            session.conference, room, start, end, exclude_pk=session.pk
        )

        for attr, value in validated_data.items():
            setattr(session, attr, value)
        session.save()

        AuditLogManager.log(
            action='schedule.session.updated',
            actor=organiser,
            obj=session,
            new_values={'title': session.title, 'status': session.status},
        )
        return session

    @staticmethod
    @transaction.atomic
    def publish_session(organiser, session):
        """Publish a session — makes it visible in the public programme."""
        if session.status == 'published':
            raise ValueError("Session is already published.")
        if session.status == 'cancelled':
            raise ValueError("Cannot publish a cancelled session.")
        if not session.presentations.exists():
            raise ValueError("Cannot publish a session with no presentations assigned.")

        session.status = 'published'
        session.save(update_fields=['status'])

        AuditLogManager.log(
            action='schedule.session.published',
            actor=organiser,
            obj=session,
        )

        # Notify all assigned presenters
        from apps.communications.notification_service import notification_service
        for presentation in session.presentations.all():
            recipient = presentation.speaker_user
            if not recipient and presentation.submission:
                recipient = presentation.submission.submitted_by
            if recipient:
                # Build slot timing line
                if presentation.start_time and presentation.end_time:
                    slot = (
                        f'{presentation.start_time.strftime("%H:%M")}–'
                        f'{presentation.end_time.strftime("%H:%M")}'
                    )
                elif presentation.duration_minutes:
                    slot = f'{presentation.duration_minutes} minutes'
                else:
                    slot = 'time TBC'

                # Build location line
                location_parts = []
                if session.room:
                    location_parts.append(f'Room: {session.room}')
                if session.format in ('online', 'hybrid') and session.online_link:
                    location_parts.append(f'Online: {session.online_link}')
                location_line = ' | '.join(location_parts) if location_parts else 'Venue TBC'

                message = (
                    f'The programme has been published for {session.conference.title}.\n\n'
                    f'Your paper "{presentation.get_title()}" is scheduled as follows:\n'
                    f'  Session:  {session.title}\n'
                    f'  Date:     {session.start_time.strftime("%B %d, %Y")}\n'
                    f'  Session time: {session.start_time.strftime("%H:%M")}–{session.end_time.strftime("%H:%M")}\n'
                    f'  Your slot: {slot}\n'
                    f'  Order:    Presentation #{presentation.order}\n'
                    f'  {location_line}\n'
                    + (f'  Track:    {session.track.name}\n' if session.track else '')
                    + (f'  Chair:    {session.chair.get_full_name() or session.chair.email}\n' if session.chair else '')
                )

                notification_service.create_notification(
                    recipient=recipient,
                    notification_type='announcement',
                    title=f'Programme Published — Your Slot Confirmed: {session.title}',
                    message=message,
                    priority='high',
                    related_object=session,
                    send_email=True,
                )

        return session

    @staticmethod
    @transaction.atomic
    def assign_presentation(organiser, session, validated_data):
        """
        Assign a paper or speaker to a session slot.
        Validates that linked submissions are accepted.
        """
        submission = validated_data.get('submission')

        if submission:
            if submission.conference != session.conference:
                raise ValueError(
                    "Submission does not belong to this session's conference."
                )
            if submission.status != 'accepted':
                raise ValueError(
                    f"Only accepted papers can be scheduled. "
                    f"Submission status is '{submission.status}'."
                )
            # Prevent double-scheduling
            if SessionPresentation.objects.filter(
                submission=submission,
                session__conference=session.conference
            ).exists():
                raise ValueError(
                    "This submission is already scheduled in another session."
                )

        presentation = SessionPresentation.objects.create(
            session=session,
            **validated_data,
        )

        AuditLogManager.log(
            action='schedule.presentation.assigned',
            actor=organiser,
            obj=presentation,
            new_values={
                'session': session.title,
                'submission': str(submission.id) if submission else None,
                'speaker': presentation.speaker_name,
            }
        )

        # Notify the author / speaker that their paper has been scheduled
        from apps.communications.notification_service import notification_service
        recipient = presentation.speaker_user
        if not recipient and submission:
            recipient = submission.submitted_by
        if recipient:
            notification_service.create_notification(
                recipient=recipient,
                notification_type='announcement',
                title=f'Paper Scheduled: {session.title}',
                message=(
                    f'Your paper "{presentation.get_title()}" has been scheduled '
                    f'in the session "{session.title}" '
                    f'({session.start_time.strftime("%B %d, %Y at %H:%M")}). '
                    f'The session is currently being prepared and will be published shortly.'
                ),
                priority='medium',
                related_object=presentation,
                send_email=True,
            )

        return presentation

    @staticmethod
    @transaction.atomic
    def cancel_session(organiser, session, reason=''):
        """Cancel a session and notify all assigned presenters."""
        if session.status == 'cancelled':
            raise ValueError("Session is already cancelled.")

        session.status = 'cancelled'
        session.save(update_fields=['status'])

        AuditLogManager.log(
            action='schedule.session.cancelled',
            actor=organiser,
            obj=session,
            new_values={'title': session.title, 'reason': reason},
        )

        from apps.communications.notification_service import notification_service
        for presentation in session.presentations.all():
            recipient = presentation.speaker_user
            if not recipient and presentation.submission:
                recipient = presentation.submission.submitted_by
            if recipient:
                notification_service.create_notification(
                    recipient=recipient,
                    notification_type='announcement',
                    title=f'Session Cancelled: {session.title}',
                    message=(
                        f'The session "{session.title}" scheduled for '
                        f'{session.start_time.strftime("%B %d, %Y at %H:%M")} '
                        f'has been cancelled.'
                        + (f' Reason: {reason}' if reason else '')
                    ),
                    priority='high',
                    related_object=session,
                    send_email=True,
                )

        return session

    @staticmethod
    @transaction.atomic
    def update_presentation(organiser, presentation, validated_data):
        """Update presentation details (timing, confirmation, speaker info)."""
        for attr, value in validated_data.items():
            setattr(presentation, attr, value)
        presentation.save()

        AuditLogManager.log(
            action='schedule.presentation.updated',
            actor=organiser,
            obj=presentation,
            new_values={
                'is_confirmed': presentation.is_confirmed,
                'order': presentation.order,
            },
        )
        return presentation

    @staticmethod
    @transaction.atomic
    def remove_presentation(organiser, presentation):
        session_title = presentation.session.title
        AuditLogManager.log(
            action='schedule.presentation.removed',
            actor=organiser,
            obj=presentation,
            new_values={'session': session_title},
        )
        presentation.delete()
