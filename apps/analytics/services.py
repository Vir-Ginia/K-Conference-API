"""
Analytics service layer.
All stats are computed live from the database.
Results can optionally be saved as AnalyticsReport snapshots.
"""
from django.db.models import Count, Avg, Q
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings


def _analytics_cache_timeout():
    return getattr(settings, 'CACHE_TIMEOUT_ANALYTICS', 300)


class AnalyticsService:

    @staticmethod
    def overview(conference):
        """
        High-level dashboard snapshot for a conference.
        Combines key metrics from all modules.
        """
        cache_key = f'analytics:overview:{conference.pk}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.submissions.models import Submission
        from apps.reviews.models import ReviewAssignment, ReviewDecision
        from apps.registrations.models import Registration
        from apps.scheduling.models import Session

        submission_qs = Submission.objects.filter(conference=conference)
        registration_qs = Registration.objects.filter(conference=conference)

        total_submissions = submission_qs.count()
        accepted = submission_qs.filter(status='accepted').count()

        result = {
            'conference': conference.short_name,
            'generated_at': timezone.now().isoformat(),
            'submissions': {
                'total': total_submissions,
                'accepted': accepted,
                'rejected': submission_qs.filter(status='rejected').count(),
                'under_review': submission_qs.filter(status='under_review').count(),
                'acceptance_rate': round(accepted / total_submissions * 100, 1) if total_submissions else 0,
            },
            'reviews': {
                'total_assignments': ReviewAssignment.objects.filter(
                    submission__conference=conference
                ).count(),
                'completed': ReviewAssignment.objects.filter(
                    submission__conference=conference, status='completed'
                ).count(),
                'decisions_made': ReviewDecision.objects.filter(conference=conference).count(),
                'decisions_published': ReviewDecision.objects.filter(
                    conference=conference, is_published=True
                ).count(),
            },
            'registrations': {
                'total': registration_qs.count(),
                'approved': registration_qs.filter(status='approved').count(),
                'waitlisted': registration_qs.filter(status='waitlisted').count(),
                'checked_in': registration_qs.filter(status='checked_in').count(),
                'capacity': conference.max_participants,
            },
            'sessions': {
                'total': Session.objects.filter(conference=conference).count(),
                'published': Session.objects.filter(conference=conference, status='published').count(),
            },
        }
        cache.set(cache_key, result, _analytics_cache_timeout())
        return result

    @staticmethod
    def submission_stats(conference):
        """
        Detailed submission breakdown:
        - Counts by status
        - Acceptance rate
        - Per-track breakdown
        - Keyword frequency (top 20)
        - Author affiliation demographics
        """
        cache_key = f'analytics:submissions:{conference.pk}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.submissions.models import Submission, SubmissionAuthor

        qs = Submission.objects.filter(conference=conference)
        total = qs.count()

        # Status breakdown
        by_status = {
            item['status']: item['count']
            for item in qs.values('status').annotate(count=Count('id'))
        }

        accepted = by_status.get('accepted', 0)
        rejected = by_status.get('rejected', 0)
        decided = accepted + rejected

        # Per-track breakdown
        by_track = list(
            qs.values('track__name').annotate(
                total=Count('id'),
                accepted=Count('id', filter=Q(status='accepted')),
                rejected=Count('id', filter=Q(status='rejected')),
            ).order_by('-total')
        )

        # Keyword frequency
        keywords = {}
        for submission in qs.exclude(keywords=[]).values_list('keywords', flat=True):
            if isinstance(submission, list):
                for kw in submission:
                    kw = kw.strip().lower()
                    if kw:
                        keywords[kw] = keywords.get(kw, 0) + 1
        top_keywords = sorted(keywords.items(), key=lambda x: -x[1])[:20]

        # Author affiliation/country demographics
        affiliations = list(
            SubmissionAuthor.objects.filter(submission__conference=conference)
            .exclude(affiliation='')
            .values('affiliation')
            .annotate(count=Count('id'))
            .order_by('-count')[:15]
        )

        result = {
            'conference': conference.short_name,
            'generated_at': timezone.now().isoformat(),
            'total': total,
            'by_status': by_status,
            'acceptance_rate': round(accepted / decided * 100, 1) if decided else None,
            'by_track': by_track,
            'top_keywords': [{'keyword': k, 'count': c} for k, c in top_keywords],
            'author_affiliations': affiliations,
        }
        cache.set(cache_key, result, _analytics_cache_timeout())
        return result

    @staticmethod
    def review_stats(conference):
        """
        Review progress and rubric score distributions.
        - Assignment completion rates
        - Average scores per criterion
        - Recommendation distribution
        - COI count
        """
        cache_key = f'analytics:reviews:{conference.pk}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.reviews.models import ReviewAssignment, Review, ReviewScore, ConflictOfInterest

        assignments = ReviewAssignment.objects.filter(submission__conference=conference)
        total_assignments = assignments.count()
        completed = assignments.filter(status='completed').count()

        # Completion per submission
        completion_by_submission = list(
            assignments.values('submission__title').annotate(
                total=Count('id'),
                completed=Count('id', filter=Q(status='completed')),
                pending=Count('id', filter=Q(status='pending')),
            ).order_by('submission__title')
        )

        # Recommendation distribution
        recommendation_dist = {
            item['recommendation']: item['count']
            for item in Review.objects.filter(
                submission__conference=conference, is_submitted=True
            ).values('recommendation').annotate(count=Count('id'))
        }

        # Average score per criterion
        criterion_avgs = list(
            ReviewScore.objects.filter(
                review__submission__conference=conference,
                review__is_submitted=True,
            ).values('criterion_name').annotate(
                avg_score=Avg('score'),
                count=Count('id'),
            ).order_by('criterion_name')
        )

        # COI count
        coi_count = ConflictOfInterest.objects.filter(
            submission__conference=conference
        ).count()

        result = {
            'conference': conference.short_name,
            'generated_at': timezone.now().isoformat(),
            'assignments': {
                'total': total_assignments,
                'completed': completed,
                'pending': assignments.filter(status='pending').count(),
                'declined': assignments.filter(status='declined').count(),
                'recused': assignments.filter(status='recused').count(),
                'completion_rate': round(completed / total_assignments * 100, 1) if total_assignments else 0,
            },
            'completion_by_submission': completion_by_submission,
            'recommendation_distribution': recommendation_dist,
            'criterion_averages': [
                {
                    'criterion': item['criterion_name'],
                    'avg_score': round(float(item['avg_score']), 2) if item['avg_score'] else None,
                    'response_count': item['count'],
                }
                for item in criterion_avgs
            ],
            'conflict_of_interest_count': coi_count,
        }
        cache.set(cache_key, result, _analytics_cache_timeout())
        return result

    @staticmethod
    def registration_stats(conference):
        """
        Registration numbers and trends.
        - Counts by status and ticket type
        - Registrations over time (daily)
        - Check-in rate
        """
        cache_key = f'analytics:registrations:{conference.pk}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.registrations.models import Registration
        from django.db.models.functions import TruncDate

        qs = Registration.objects.filter(conference=conference)
        total = qs.count()

        by_status = {
            item['status']: item['count']
            for item in qs.values('status').annotate(count=Count('id'))
        }

        by_ticket_type = {
            item['ticket_type']: item['count']
            for item in qs.values('ticket_type').annotate(count=Count('id'))
        }

        # Registrations over time (daily)
        over_time = list(
            qs.annotate(date=TruncDate('registered_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )
        over_time = [
            {'date': item['date'].isoformat(), 'count': item['count']}
            for item in over_time
        ]

        checked_in = by_status.get('checked_in', 0)
        approved = by_status.get('approved', 0) + checked_in

        result = {
            'conference': conference.short_name,
            'generated_at': timezone.now().isoformat(),
            'total': total,
            'by_status': by_status,
            'by_ticket_type': by_ticket_type,
            'check_in_rate': round(checked_in / approved * 100, 1) if approved else 0,
            'capacity': conference.max_participants,
            'capacity_used': round(approved / conference.max_participants * 100, 1) if conference.max_participants else None,
            'registrations_over_time': over_time,
        }
        cache.set(cache_key, result, _analytics_cache_timeout())
        return result

    @staticmethod
    def attendance_stats(conference):
        """
        Event-day attendance: check-ins per session and overall.
        """
        cache_key = f'analytics:attendance:{conference.pk}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.registrations.models import Registration
        from apps.scheduling.models import Session

        checked_in_qs = Registration.objects.filter(
            conference=conference, status='checked_in'
        )

        # Check-ins over time
        from django.db.models.functions import TruncHour
        check_ins_by_hour = list(
            checked_in_qs.annotate(hour=TruncHour('checked_in_at'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('hour')
        )

        sessions = Session.objects.filter(
            conference=conference, status='published'
        ).prefetch_related('presentations').order_by('start_time')

        session_summary = [
            {
                'session': s.title,
                'type': s.session_type,
                'start_time': s.start_time.isoformat(),
                'presentation_count': s.presentations.count(),
                'format': s.format,
                'room': s.room,
            }
            for s in sessions
        ]

        result = {
            'conference': conference.short_name,
            'generated_at': timezone.now().isoformat(),
            'total_checked_in': checked_in_qs.count(),
            'check_ins_by_hour': [
                {'hour': item['hour'].isoformat() if item['hour'] else None, 'count': item['count']}
                for item in check_ins_by_hour
            ],
            'sessions': session_summary,
        }
        cache.set(cache_key, result, _analytics_cache_timeout())
        return result
