"""
Submission service layer.
All business logic lives here — not in views or serializers.
"""
import logging
from django.utils import timezone
from django.db import transaction

from apps.submissions.models import Submission, SubmissionAuthor, SubmissionFile, SubmissionVersion
from apps.audit.models import AuditLogManager
from apps.core.utils import upload_file_to_cloudinary

logger = logging.getLogger(__name__)


class SubmissionService:

    @staticmethod
    @transaction.atomic
    def create_submission(user, validated_data, file=None):
        """
        Create a new submission.
        - Validates conference is open for submissions.
        - Enforces submission deadline (unless allow_late_submissions is set).
        - Creates primary author record from submitting user.
        - Handles optional file upload.
        """
        conference = validated_data['conference']
        authors_data = validated_data.pop('authors', [])
        file_type = validated_data.pop('file_type', 'paper')

        # Conference must be open
        if not conference.is_open_for_submissions():
            raise PermissionError("This conference is not currently open for submissions.")

        # Deadline check — ConferenceDeadline takes precedence over flat field
        effective_deadline = conference.get_effective_submission_deadline()
        if effective_deadline and timezone.now() > effective_deadline:
            if not conference.allow_late_submissions:
                raise PermissionError(
                    "The submission deadline has passed. Late submissions are not allowed."
                )

        submission = Submission.objects.create(submitted_by=user, **validated_data)

        # Increment track submission counter
        if submission.track:
            from django.db.models import F
            from apps.conferences.models import ConferenceTrack
            ConferenceTrack.objects.filter(pk=submission.track_id).update(
                current_submissions=F('current_submissions') + 1
            )

        # Primary author — always the submitting user
        affiliation = ''
        if hasattr(user, 'affiliation'):
            affiliation = user.affiliation.institution or ''

        SubmissionAuthor.objects.create(
            submission=submission,
            user=user,
            name=user.get_full_name() or user.email,
            email=user.email,
            affiliation=affiliation,
            order=0,
            is_primary=True,
            is_corresponding=True,
        )

        # Co-authors
        from apps.accounts.models import User as UserModel
        for idx, author_data in enumerate(authors_data, start=1):
            matched_user = UserModel.objects.filter(email=author_data['email']).first()
            SubmissionAuthor.objects.get_or_create(
                submission=submission,
                email=author_data['email'],
                defaults={**author_data, 'order': idx, 'user': matched_user},
            )

        if file:
            SubmissionService._upload_file(submission, file, user, file_type=file_type, version=1)

        AuditLogManager.log(
            action='submission.created',
            actor=user,
            obj=submission,
            new_values={
                'title': submission.title,
                'conference': conference.short_name,
                'track': submission.track.name if submission.track else None,
                'status': submission.status,
            }
        )

        return submission

    @staticmethod
    @transaction.atomic
    def update_submission(user, submission, validated_data, file=None):
        """
        Update a submission.
        - Blocks edits on locked or terminal submissions.
        - Replaces file (marks old version as not current).
        """
        if not submission.is_editable:
            raise PermissionError(
                "This submission is locked and cannot be edited. Contact the organiser."
            )

        conference = submission.conference
        effective_deadline = conference.get_effective_submission_deadline()
        if (
            effective_deadline
            and timezone.now() > effective_deadline
            and not conference.allow_late_submissions
        ):
            submission.lock()
            raise PermissionError(
                "The submission deadline has passed. Edits are no longer allowed. "
                "Contact the organiser for an override."
            )

        old_values = {
            'title': submission.title,
            'abstract': submission.abstract,
            'keywords': submission.keywords,
        }

        file_type = validated_data.pop('file_type', 'paper')

        for attr, value in validated_data.items():
            setattr(submission, attr, value)
        submission.save()

        if file:
            new_version = submission.files.filter(file_type=file_type).count() + 1
            submission.files.filter(file_type=file_type, is_current=True).update(is_current=False)
            SubmissionService._upload_file(submission, file, user, file_type=file_type, version=new_version)

        AuditLogManager.log(
            action='submission.updated',
            actor=user,
            obj=submission,
            old_values=old_values,
            new_values={'title': submission.title, 'abstract': submission.abstract[:100]},
        )

        return submission

    @staticmethod
    @transaction.atomic
    def submit_submission(user, submission):
        """
        Move submission from draft → submitted.
        Validates a paper file exists and deadline is not passed.
        """
        if submission.status != 'draft':
            raise ValueError(f"Cannot submit: current status is '{submission.status}'.")

        conference = submission.conference
        effective_deadline = conference.get_effective_submission_deadline()
        if effective_deadline and timezone.now() > effective_deadline:
            if not conference.allow_late_submissions:
                raise PermissionError("The submission deadline has passed.")

        if not submission.files.filter(is_current=True, file_type='paper').exists():
            raise ValueError("A full paper file must be uploaded before submitting.")

        submission.status = 'submitted'
        submission.submitted_at = timezone.now()
        submission.save(update_fields=['status', 'submitted_at'])

        AuditLogManager.log(
            action='submission.submitted',
            actor=user,
            obj=submission,
            new_values={'status': 'submitted', 'submitted_at': str(submission.submitted_at)},
        )

        # Send dedicated submission confirmation email
        try:
            from apps.core.utils import send_email_template
            send_email_template(
                subject=f'Submission Received: {submission.title}',
                template_name='emails/submission_confirmation.html',
                context={
                    'recipient': user,
                    'conference_title': conference.title,
                    'submission_title': submission.title,
                    'submission_id': str(submission.id),
                    'track_name': submission.track.name if submission.track else None,
                    'version_number': submission.version_number,
                    'submitted_at': submission.submitted_at.strftime('%d %b %Y, %H:%M UTC'),
                },
                recipient_list=[user.email],
            )
        except Exception:
            logger.warning('Failed to send submission confirmation email for %s', submission.id)

        return submission

    @staticmethod
    @transaction.atomic
    def withdraw_submission(user, submission):
        """Withdraw a submission. Not allowed on terminal statuses."""
        if submission.is_terminal:
            raise ValueError(
                f"Cannot withdraw: submission is already '{submission.status}'."
            )

        old_status = submission.status
        submission.status = 'withdrawn'
        submission.save(update_fields=['status'])

        # Decrement track counter (only if it was an active submission)
        if submission.track and old_status not in ('withdrawn', 'rejected', 'accepted'):
            from django.db.models import F
            from apps.conferences.models import ConferenceTrack
            ConferenceTrack.objects.filter(
                pk=submission.track_id, current_submissions__gt=0
            ).update(current_submissions=F('current_submissions') - 1)

        AuditLogManager.log(
            action='submission.withdrawn',
            actor=user,
            obj=submission,
            old_values={'status': old_status},
            new_values={'status': 'withdrawn'},
        )

        return submission

    @staticmethod
    @transaction.atomic
    def organiser_override(organiser, submission, validated_data, reason, file=None):
        """
        Organiser-only override of a locked submission.
        Snapshots the current state as a version, applies changes, increments version number.
        Mandatory reason is logged to the audit trail.
        """
        if not reason or not reason.strip():
            raise ValueError("A reason is required for organiser override.")

        # Snapshot current state
        SubmissionVersion.objects.create(
            submission=submission,
            version_number=submission.version_number,
            title=submission.title,
            abstract=submission.abstract,
            keywords=submission.keywords,
            changed_by=organiser,
            change_reason=reason,
        )

        file_type = validated_data.pop('file_type', 'paper')  # not a Submission field

        for attr, value in validated_data.items():
            setattr(submission, attr, value)

        submission.version_number += 1
        submission.deadline_override = True
        submission.deadline_override_reason = reason
        submission.deadline_override_by = organiser
        submission.deadline_override_at = timezone.now()
        submission.save()

        if file:
            new_version = submission.files.filter(file_type=file_type).count() + 1
            submission.files.filter(file_type=file_type, is_current=True).update(is_current=False)
            SubmissionService._upload_file(submission, file, organiser, file_type=file_type, version=new_version)

        AuditLogManager.log(
            action='submission.override',
            actor=organiser,
            obj=submission,
            new_values={
                'title': submission.title,
                'version_number': submission.version_number,
            },
            reason=reason,
        )

        return submission

    @staticmethod
    def _upload_file(submission, file, user, file_type='paper', version=1):
        """Upload a file to Cloudinary and create a SubmissionFile record."""
        try:
            result = upload_file_to_cloudinary(
                file,
                folder=f"submissions/{submission.conference.short_name}/{submission.id}"
                ,
                public_id=f"{file_type}_v{version}_{file.name}",
            )
            SubmissionFile.objects.create(
                submission=submission,
                uploaded_by=user,
                file_type=file_type,
                file_url=result['url'],
                public_id=result.get('public_id', ''),
                original_filename=file.name,
                file_size=file.size,
                mime_type=getattr(file, 'content_type', ''),
                version_number=version,
                is_current=True,
            )
        except Exception as e:
            logger.error(f"File upload failed for submission {submission.id}: {e}")
            raise ValueError(f"File upload failed: {e}")
