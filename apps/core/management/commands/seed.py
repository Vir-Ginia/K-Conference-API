"""
Comprehensive seeder for K-Conference system.
Creates realistic test data across all entities for thorough testing.
"""

import random
import uuid
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import User, UserProfile, UserAffiliation
from apps.conferences.models import (
    Conference, ConferenceTrack, ConferenceDeadline, ConferenceRole, ConferenceMedia
)
from apps.submissions.models import Submission, SubmissionAuthor, SubmissionFile
from apps.reviews.models import ReviewAssignment, ConflictOfInterest, Review, ReviewDecision
from apps.registrations.models import Registration
from apps.communications.models import Announcement, Notification
from apps.scheduling.models import Session
from apps.audit.models import AuditLogManager


class Command(BaseCommand):
    help = 'Seed the database with comprehensive test data for K-Conference'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            self.clear_data()

        self.stdout.write('Creating users...')
        users = self.create_users()

        self.stdout.write('Creating conferences...')
        conferences = self.create_conferences(users)

        self.stdout.write('Creating conference roles...')
        self.create_conference_roles(conferences, users)

        self.stdout.write('Creating tracks and deadlines...')
        self.create_tracks_and_deadlines(conferences, users)

        self.stdout.write('Creating submissions...')
        submissions = self.create_submissions(conferences, users)

        self.stdout.write('Creating review assignments...')
        self.create_review_assignments(submissions, users)

        self.stdout.write('Creating reviews...')
        self.create_reviews(submissions, users)

        self.stdout.write('Creating registrations...')
        self.create_registrations(conferences, users)

        self.stdout.write('Creating sessions...')
        self.create_sessions(conferences, users)

        self.stdout.write('Creating announcements...')
        self.create_announcements(conferences, users)

        self.stdout.write('Creating notifications...')
        self.create_notifications(users, conferences)

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully seeded database with {len(users)} users, '
                f'{len(conferences)} conferences, {len(submissions)} submissions, '
                'and related data!'
            )
        )

    def clear_data(self):
        """Clear all existing data."""
        # Clear in reverse dependency order
        Notification.objects.all().delete()
        Announcement.objects.all().delete()
        Session.objects.all().delete()
        Registration.objects.all().delete()
        ReviewDecision.objects.all().delete()
        Review.objects.all().delete()
        ConflictOfInterest.objects.all().delete()
        ReviewAssignment.objects.all().delete()
        SubmissionFile.objects.all().delete()
        SubmissionAuthor.objects.all().delete()
        Submission.objects.all().delete()
        ConferenceMedia.objects.all().delete()
        ConferenceDeadline.objects.all().delete()
        ConferenceRole.objects.all().delete()
        ConferenceTrack.objects.all().delete()
        Conference.objects.all().delete()
        UserAffiliation.objects.all().delete()
        UserProfile.objects.all().delete()
        User.objects.all().delete()

    def create_users(self):
        """Create users with different roles."""
        users_data = [
            # Admin users
            {'email': 'admin@mailinator.com', 'first_name': 'System', 'last_name': 'Admin', 'roles': ['admin'], 'is_staff': True, 'is_superuser': True},
            {'email': 'superadmin@mailinator.com', 'first_name': 'Super', 'last_name': 'Admin', 'roles': ['admin'], 'is_staff': True, 'is_superuser': True},

            # Organisers
            {'email': 'alice.organiser@mailinator.com', 'first_name': 'Alice', 'last_name': 'Johnson', 'roles': ['organiser']},
            {'email': 'bob.organiser@mailinator.com', 'first_name': 'Bob', 'last_name': 'Smith', 'roles': ['organiser']},
            {'email': 'carol.organiser@mailinator.com', 'first_name': 'Carol', 'last_name': 'Williams', 'roles': ['organiser']},

            # Reviewers
            {'email': 'david.reviewer@mailinator.com', 'first_name': 'David', 'last_name': 'Brown', 'roles': ['reviewer']},
            {'email': 'eve.reviewer@mailinator.com', 'first_name': 'Eve', 'last_name': 'Davis', 'roles': ['reviewer']},
            {'email': 'frank.reviewer@mailinator.com', 'first_name': 'Frank', 'last_name': 'Miller', 'roles': ['reviewer']},
            {'email': 'grace.reviewer@mailinator.com', 'first_name': 'Grace', 'last_name': 'Wilson', 'roles': ['reviewer']},
            {'email': 'henry.reviewer@mailinator.com', 'first_name': 'Henry', 'last_name': 'Moore', 'roles': ['reviewer']},

            # Authors
            {'email': 'ivy.author@mailinator.com', 'first_name': 'Ivy', 'last_name': 'Taylor', 'roles': ['author']},
            {'email': 'jack.author@mailinator.com', 'first_name': 'Jack', 'last_name': 'Anderson', 'roles': ['author']},
            {'email': 'kate.author@mailinator.com', 'first_name': 'Kate', 'last_name': 'Thomas', 'roles': ['author']},
            {'email': 'liam.author@mailinator.com', 'first_name': 'Liam', 'last_name': 'Jackson', 'roles': ['author']},
            {'email': 'mia.author@mailinator.com', 'first_name': 'Mia', 'last_name': 'White', 'roles': ['author']},
            {'email': 'noah.author@mailinator.com', 'first_name': 'Noah', 'last_name': 'Harris', 'roles': ['author']},
            {'email': 'olivia.author@mailinator.com', 'first_name': 'Olivia', 'last_name': 'Martin', 'roles': ['author']},
            {'email': 'peter.author@mailinator.com', 'first_name': 'Peter', 'last_name': 'Thompson', 'roles': ['author']},

            # Participants
            {'email': 'quinn.participant@mailinator.com', 'first_name': 'Quinn', 'last_name': 'Garcia', 'roles': ['participant']},
            {'email': 'rachel.participant@mailinator.com', 'first_name': 'Rachel', 'last_name': 'Martinez', 'roles': ['participant']},
            {'email': 'sam.participant@mailinator.com', 'first_name': 'Sam', 'last_name': 'Robinson', 'roles': ['participant']},
            {'email': 'tina.participant@mailinator.com', 'first_name': 'Tina', 'last_name': 'Clark', 'roles': ['participant']},
            {'email': 'ursula.participant@mailinator.com', 'first_name': 'Ursula', 'last_name': 'Rodriguez', 'roles': ['participant']},

            # Multi-role users
            {'email': 'victor.multi@mailinator.com', 'first_name': 'Victor', 'last_name': 'Lee', 'roles': ['author', 'reviewer']},
            {'email': 'wendy.multi@mailinator.com', 'first_name': 'Wendy', 'last_name': 'Walker', 'roles': ['organiser', 'reviewer']},
            {'email': 'xavier.multi@mailinator.com', 'first_name': 'Xavier', 'last_name': 'Hall', 'roles': ['author', 'participant']},
        ]

        users = []
        institutions = [
            'University of Technology', 'Research Institute', 'Tech Corp', 'Innovation Labs',
            'Global University', 'Science Academy', 'Digital Solutions Inc', 'Future Systems'
        ]

        for user_data in users_data:
            user = User.objects.create_user(
                email=user_data['email'],
                password='Password123%',
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                is_active=True,
                email_verified=True,
                email_verified_at=timezone.now(),
                is_staff=user_data.get('is_staff', False),
                is_superuser=user_data.get('is_superuser', False),
            )

            # Set roles
            for role in user_data['roles']:
                setattr(user, f'is_{role}', True)
            user.save()

            # Profile is auto-created by signal; update it
            UserProfile.objects.filter(user=user).update(
                prefer_email_notifications=True,
                language='en',
            )

            # Create affiliation for most users (skip admin)
            if not user.is_admin:
                UserAffiliation.objects.filter(user=user).update(
                    institution=random.choice(institutions),
                    department=random.choice(['Computer Science', 'Engineering', 'Research', 'Development']),
                    position=random.choice(['Professor', 'Researcher', 'Student', 'Engineer', 'Manager']),
                    country=random.choice(['USA', 'UK', 'Canada', 'Australia', 'Germany'])
                )

            users.append(user)

        return users

    def create_conferences(self, users):
        """Create conferences with different statuses."""
        organisers = [u for u in users if u.is_organiser]

        conferences_data = [
            {
                'title': 'International Conference on Artificial Intelligence 2024',
                'short_name': 'ICAI2024',
                'description': 'Leading conference on AI research and applications',
                'status': 'open',
                'conference_type': 'hybrid',
                'start_date': timezone.now() + timedelta(days=30),
                'end_date': timezone.now() + timedelta(days=32),
                'venue_name': 'Convention Center',
                'city': 'San Francisco',
                'country': 'USA',
                'max_participants': 500,
                'submission_deadline': timezone.now() + timedelta(days=14),
                'review_deadline': timezone.now() + timedelta(days=21),
                'registration_deadline': timezone.now() + timedelta(days=25),
            },
            {
                'title': 'European Conference on Computer Vision',
                'short_name': 'ECCV2024',
                'description': 'Premier conference for computer vision research',
                'status': 'review',
                'conference_type': 'in_person',
                'start_date': timezone.now() + timedelta(days=60),
                'end_date': timezone.now() + timedelta(days=63),
                'venue_name': 'Technical University',
                'city': 'Berlin',
                'country': 'Germany',
                'max_participants': 800,
                'submission_deadline': timezone.now() - timedelta(days=7),
                'review_deadline': timezone.now() + timedelta(days=7),
                'registration_deadline': timezone.now() + timedelta(days=45),
            },
            {
                'title': 'Pacific Conference on Data Science',
                'short_name': 'PCDS2024',
                'description': 'Exploring the frontiers of data science',
                'status': 'closed',
                'conference_type': 'online',
                'start_date': timezone.now() - timedelta(days=10),
                'end_date': timezone.now() - timedelta(days=8),
                'online_link': 'https://zoom.us/conference/pcds2024',
                'max_participants': 300,
                'submission_deadline': timezone.now() - timedelta(days=30),
                'review_deadline': timezone.now() - timedelta(days=20),
                'registration_deadline': timezone.now() - timedelta(days=15),
            },
            {
                'title': 'Global Summit on Machine Learning',
                'short_name': 'GSML2024',
                'description': 'Annual summit bringing together ML researchers worldwide',
                'status': 'draft',
                'conference_type': 'hybrid',
                'start_date': timezone.now() + timedelta(days=90),
                'end_date': timezone.now() + timedelta(days=92),
                'venue_name': 'International Conference Center',
                'city': 'Tokyo',
                'country': 'Japan',
                'max_participants': 1000,
            },
        ]

        conferences = []
        for conf_data in conferences_data:
            conference = Conference.objects.create(
                organiser=random.choice(organisers),
                **conf_data
            )
            conferences.append(conference)

        return conferences

    def create_conference_roles(self, conferences, users):
        """Create conference-specific roles."""
        for conference in conferences:
            # Add organiser role
            ConferenceRole.objects.create(
                conference=conference,
                user=conference.organiser,
                role='organiser'
            )

            # Add some reviewers
            reviewers = [u for u in users if u.is_reviewer][:3]
            for reviewer in reviewers:
                ConferenceRole.objects.create(
                    conference=conference,
                    user=reviewer,
                    role='reviewer'
                )

            # Add some participants
            participants = [u for u in users if u.is_participant][:5]
            for participant in participants:
                ConferenceRole.objects.create(
                    conference=conference,
                    user=participant,
                    role='participant'
                )

    def create_tracks_and_deadlines(self, conferences, users):
        """Create tracks and deadlines for conferences."""
        track_names = [
            'Machine Learning', 'Computer Vision', 'Natural Language Processing',
            'Robotics', 'Data Mining', 'Cybersecurity', 'Software Engineering'
        ]

        for conference in conferences:
            # Create tracks
            for i, track_name in enumerate(track_names[:4]):  # 4 tracks per conference
                ConferenceTrack.objects.create(
                    conference=conference,
                    name=f"{track_name} Track",
                    short_name=f"T{i+1}",
                    description=f"Research papers in {track_name.lower()}",
                    chair=random.choice([u for u in users if u.is_reviewer]),
                    max_submissions=50
                )

            # Create deadlines
            ConferenceDeadline.objects.create(
                conference=conference,
                deadline_type='submission_open',
                title='Submission Opens',
                deadline_date=conference.submission_deadline - timedelta(days=30) if conference.submission_deadline else timezone.now() - timedelta(days=10)
            )

            if conference.submission_deadline:
                ConferenceDeadline.objects.create(
                    conference=conference,
                    deadline_type='submission_close',
                    title='Submission Deadline',
                    deadline_date=conference.submission_deadline
                )

            if conference.review_deadline:
                ConferenceDeadline.objects.create(
                    conference=conference,
                    deadline_type='review_end',
                    title='Review Period Ends',
                    deadline_date=conference.review_deadline
                )

    def create_submissions(self, conferences, users):
        """Create submissions for conferences."""
        authors = [u for u in users if u.is_author]
        submissions = []

        paper_titles = [
            'Deep Learning Approaches for Image Classification',
            'Natural Language Processing in Healthcare',
            'Computer Vision for Autonomous Vehicles',
            'Machine Learning in Cybersecurity',
            'Data Mining Techniques for Big Data',
            'Software Engineering Best Practices',
            'Robotics and Artificial Intelligence',
            'Neural Networks for Pattern Recognition',
            'Blockchain Technology in Finance',
            'Internet of Things Security',
            'Cloud Computing Architectures',
            'Mobile Application Development',
            'Database Optimization Techniques',
            'Web Development Frameworks',
            'Artificial Intelligence Ethics'
        ]

        for conference in conferences:
            if conference.status in ['draft']:
                continue  # No submissions for draft conferences

            num_submissions = random.randint(5, 15)
            for i in range(num_submissions):
                author = random.choice(authors)
                track = random.choice(list(conference.tracks.all())) if conference.tracks.exists() else None

                # Determine status based on conference status
                if conference.status == 'open':
                    status = random.choice(['draft', 'submitted'])
                elif conference.status == 'review':
                    status = random.choice(['submitted', 'under_review'])
                elif conference.status == 'closed':
                    status = random.choice(['accepted', 'rejected'])
                else:
                    status = 'submitted'

                submission = Submission.objects.create(
                    conference=conference,
                    track=track,
                    submitted_by=author,
                    title=random.choice(paper_titles),
                    abstract='This paper presents research on advanced topics in computer science and technology.',
                    keywords=['research', 'technology', 'innovation'],
                    status=status,
                    submitted_at=timezone.now() - timedelta(days=random.randint(1, 30)) if status != 'draft' else None
                )

                # Create submission authors
                SubmissionAuthor.objects.create(
                    submission=submission,
                    user=author,
                    name=author.get_full_name(),
                    email=author.email,
                    affiliation=author.affiliation.institution if hasattr(author, 'affiliation') and author.affiliation else 'University',
                    is_primary=True,
                    is_corresponding=True
                )

                # Add co-authors sometimes
                if random.choice([True, False]):
                    co_author = random.choice([u for u in authors if u != author])
                    SubmissionAuthor.objects.create(
                        submission=submission,
                        user=co_author,
                        name=co_author.get_full_name(),
                        email=co_author.email,
                        affiliation=co_author.affiliation.institution if hasattr(co_author, 'affiliation') and co_author.affiliation else 'University',
                        order=1
                    )

                # Create a mock file
                SubmissionFile.objects.create(
                    submission=submission,
                    uploaded_by=author,
                    file_type='paper',
                    file_url=f'https://cloudinary.com/mock/{uuid.uuid4()}.pdf',
                    original_filename=f'paper_{submission.id}.pdf',
                    file_size=random.randint(500000, 2000000),  # 0.5-2MB
                    mime_type='application/pdf'
                )

                submissions.append(submission)

        return submissions

    def create_review_assignments(self, submissions, users):
        """Create review assignments for submissions."""
        reviewers = [u for u in users if u.is_reviewer]

        for submission in submissions:
            if submission.status in ['draft']:
                continue

            # Assign 2-3 reviewers per submission
            num_reviewers = random.randint(2, 3)
            assigned_reviewers = random.sample(reviewers, min(num_reviewers, len(reviewers)))

            for reviewer in assigned_reviewers:
                status = 'pending'
                if submission.status == 'under_review':
                    status = random.choice(['accepted', 'completed'])
                elif submission.status in ['accepted', 'rejected']:
                    status = 'completed'

                ReviewAssignment.objects.create(
                    submission=submission,
                    reviewer=reviewer,
                    assigned_by=submission.conference.organiser,
                    status=status,
                    due_date=submission.conference.review_deadline
                )

    def create_reviews(self, submissions, users):
        """Create reviews for assignments."""
        for submission in submissions:
            assignments = submission.review_assignments.filter(status='completed')
            for assignment in assignments:
                # Create COI sometimes
                if random.choice([True, False, False]):  # 33% chance
                    ConflictOfInterest.objects.create(
                        reviewer=assignment.reviewer,
                        submission=submission,
                        reason='Previous collaboration with authors'
                    )
                    continue

                # Create review
                Review.objects.create(
                    assignment=assignment,
                    reviewer=assignment.reviewer,
                    submission=submission,
                    comments_to_authors='This paper presents interesting research with solid methodology.',
                    comments_to_organisers='Recommend based on technical merit.',
                    recommendation=random.choice(['strong_accept', 'accept', 'weak_accept', 'borderline', 'weak_reject', 'reject']),
                    is_submitted=True,
                    submitted_at=timezone.now() - timedelta(days=random.randint(1, 14)),
                )

                # Create decision for some submissions (only once per submission)
                if random.choice([True, False]) and not hasattr(submission, '_decision_created'):
                    submission._decision_created = True
                    ReviewDecision.objects.create(
                        submission=submission,
                        conference=submission.conference,
                        decided_by=submission.conference.organiser,
                        decision=random.choice(['accept', 'reject', 'revision_required']),
                        decision_reason='Decision based on reviewer feedback and scoring.',
                    )

    def create_registrations(self, conferences, users):
        """Create registrations for conferences."""
        participants = [u for u in users if u.is_participant]

        for conference in conferences:
            if conference.status == 'draft':
                continue

            num_registrations = random.randint(10, 30)
            selected_participants = random.sample(participants, min(num_registrations, len(participants)))

            for participant in selected_participants:
                status = 'approved'
                if conference.status == 'open':
                    status = random.choice(['pending', 'approved', 'waitlisted'])
                elif conference.status in ['review', 'closed']:
                    status = random.choice(['approved', 'checked_in'])

                ticket_type = random.choice(['standard', 'student', 'author', 'reviewer'])

                registration = Registration.objects.create(
                    conference=conference,
                    participant=participant,
                    status=status,
                    ticket_type=ticket_type,
                    qr_code=str(uuid.uuid4())[:8].upper()
                )

                # Update conference participant count
                if status in ['approved', 'checked_in']:
                    conference.current_participants += 1
                    conference.save()

    def create_sessions(self, conferences, users):
        """Create sessions for conferences."""
        for conference in conferences:
            if conference.status == 'draft':
                continue

            # Create keynote
            Session.objects.create(
                conference=conference,
                session_type='keynote',
                title='Opening Keynote: Future of Technology',
                description='Inaugural keynote address',
                start_time=conference.start_date.replace(hour=9, minute=0),
                end_time=conference.start_date.replace(hour=10, minute=30),
                room='Main Hall',
                capacity=conference.max_participants or 500
            )

            # Create paper sessions
            for track in conference.tracks.all():
                Session.objects.create(
                    conference=conference,
                    track=track,
                    session_type='paper',
                    title=f'{track.name} Session 1',
                    description=f'Paper presentations in {track.name}',
                    start_time=conference.start_date.replace(hour=11, minute=0),
                    end_time=conference.start_date.replace(hour=12, minute=30),
                    room=f'Room {random.randint(101, 110)}',
                    capacity=50
                )

            # Create workshop
            Session.objects.create(
                conference=conference,
                session_type='workshop',
                title='Hands-on Workshop: Advanced Techniques',
                description='Interactive workshop session',
                start_time=conference.start_date.replace(hour=14, minute=0),
                end_time=conference.start_date.replace(hour=17, minute=0),
                room='Workshop Room A',
                capacity=30
            )

    def create_announcements(self, conferences, users):
        """Create announcements for conferences."""
        for conference in conferences:
            organiser = conference.organiser

            announcements = [
                {
                    'title': f'Welcome to {conference.title}',
                    'content': f'We are excited to welcome you to {conference.title}. The conference will feature cutting-edge research and networking opportunities.',
                },
                {
                    'title': 'Registration Now Open',
                    'content': 'Registration is now open for all participants. Early bird discounts available until the deadline.',
                },
                {
                    'title': 'Call for Papers Extended',
                    'content': 'Due to popular demand, we have extended the submission deadline by one week.',
                },
                {
                    'title': 'Programme Published',
                    'content': 'The conference programme has been published. Check the schedule for session details.',
                }
            ]

            for ann_data in announcements:
                is_published = random.choice([True, True, False])  # 66% published
                Announcement.objects.create(
                    title=ann_data['title'],
                    content=ann_data['content'],
                    conference=conference,
                    author=organiser,
                    is_published=is_published,
                    published_at=timezone.now() - timedelta(days=random.randint(1, 30)) if is_published else None
                )

    def create_notifications(self, users, conferences):
        """Create notifications for users."""
        for user in users[:10]:  # Create notifications for first 10 users
            # Conference-related notifications
            for conference in conferences[:2]:  # Use first 2 conferences
                Notification.objects.create(
                    recipient=user,
                    notification_type='conference_created',
                    title=f'New Conference: {conference.title}',
                    message=f'A new conference "{conference.title}" has been announced.',
                    priority='medium',
                    expires_at=timezone.now() + timedelta(days=30),
                )

                if conference.status == 'open':
                    Notification.objects.create(
                        recipient=user,
                        notification_type='conference_opened',
                        title=f'Conference Now Open: {conference.short_name}',
                        message=f'{conference.title} is now accepting submissions and registrations.',
                        priority='high',
                        expires_at=timezone.now() + timedelta(days=14),
                    )

            # System notifications
            Notification.objects.create(
                recipient=user,
                notification_type='system',
                title='Welcome to K-Conference',
                message='Welcome to the K-Conference platform! Your account has been set up successfully.',
                priority='low',
                expires_at=timezone.now() + timedelta(days=7),
            )