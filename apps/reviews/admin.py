"""Django admin for the Reviews app."""
from django.contrib import admin
from django.utils.html import format_html
from apps.reviews.models import ReviewAssignment, ConflictOfInterest, Review, ReviewScore, ReviewDecision


class ReviewScoreInline(admin.TabularInline):
    model = ReviewScore
    extra = 0
    fields = ('criterion_name', 'criterion_weight', 'score', 'comment')
    readonly_fields = ('criterion_name', 'criterion_weight')


@admin.register(ReviewAssignment)
class ReviewAssignmentAdmin(admin.ModelAdmin):
    list_display = ('reviewer', 'submission', 'status_badge', 'is_active', 'due_date', 'assigned_at')
    list_filter = ('status', 'is_active', 'submission__conference')
    search_fields = ('reviewer__email', 'submission__title')
    readonly_fields = ('assigned_at', 'updated_at')
    ordering = ('-assigned_at',)

    def status_badge(self, obj):
        colours = {
            'pending': '#f39c12', 'accepted': '#3498db',
            'declined': '#e74c3c', 'completed': '#27ae60', 'recused': '#95a5a6',
        }
        colour = colours.get(obj.status, '#aaa')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(ConflictOfInterest)
class ConflictOfInterestAdmin(admin.ModelAdmin):
    list_display = ('reviewer', 'submission', 'declared_at', 'acknowledged_by', 'acknowledged_at')
    search_fields = ('reviewer__email', 'submission__title', 'reason')
    readonly_fields = ('declared_at',)
    ordering = ('-declared_at',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        'reviewer', 'submission', 'recommendation_badge',
        'aggregate_score', 'is_submitted', 'is_locked', 'submitted_at'
    )
    list_filter = ('is_submitted', 'is_locked', 'recommendation', 'submission__conference')
    search_fields = ('reviewer__email', 'submission__title')
    readonly_fields = ('submitted_at', 'created_at', 'updated_at', 'override_at', 'aggregate_score')
    ordering = ('-created_at',)
    inlines = [ReviewScoreInline]

    def recommendation_badge(self, obj):
        if not obj.recommendation:
            return '—'
        colours = {
            'strong_accept': '#27ae60', 'accept': '#2ecc71', 'weak_accept': '#a8d8a8',
            'borderline': '#f39c12',
            'weak_reject': '#e67e22', 'reject': '#e74c3c', 'strong_reject': '#c0392b',
        }
        colour = colours.get(obj.recommendation, '#aaa')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_recommendation_display()
        )
    recommendation_badge.short_description = 'Recommendation'


@admin.register(ReviewDecision)
class ReviewDecisionAdmin(admin.ModelAdmin):
    list_display = (
        'submission', 'conference', 'decision_badge',
        'aggregate_score', 'review_count', 'is_override', 'is_published', 'published_at'
    )
    list_filter = ('decision', 'is_override', 'is_published', 'conference')
    search_fields = ('submission__title', 'decided_by__email')
    readonly_fields = ('created_at', 'updated_at', 'published_at', 'aggregate_score', 'review_count')
    ordering = ('-created_at',)

    def decision_badge(self, obj):
        colours = {
            'accept': '#27ae60', 'best_paper': '#8e44ad',
            'reject': '#e74c3c', 'revision_required': '#f39c12',
        }
        colour = colours.get(obj.decision, '#aaa')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_decision_display()
        )
    decision_badge.short_description = 'Decision'
