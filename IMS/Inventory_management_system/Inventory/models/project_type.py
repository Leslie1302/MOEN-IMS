from django.db import models
import auto_prefetch


class ProjectType(auto_prefetch.Model):
    """
    Canonical project type. One source of truth that replaces the
    previously-disagreeing string enums on Project.project_type and
    MaterialOrder.project_type.

    The `consignee_role` field drives the auto-resolution rule for who
    receives the materials in a given release: SHEP -> 'consultant',
    Cost Sharing & Streetlights -> 'mp'. Phase F's release-letter
    generation reads this to render the correct consignee block.
    """

    CONSIGNEE_ROLE_CHOICES = [
        ('consultant', 'Project Consultant'),
        ('mp', 'Member of Parliament'),
        ('other', 'Other / not yet defined'),
    ]

    code = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Stable machine identifier, e.g. 'shep', 'cost_sharing', 'streetlights'.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name, e.g. 'SHEP', 'Cost Sharing', 'Streetlights'.",
    )
    consignee_role = models.CharField(
        max_length=20,
        choices=CONSIGNEE_ROLE_CHOICES,
        default='other',
        help_text="Drives whom releases under this project consign to.",
    )
    description = models.TextField(blank=True)
    active = models.BooleanField(
        default=True,
        help_text="Inactive types remain on legacy records but cannot be selected for new requests.",
    )
    sort_order = models.PositiveIntegerField(
        default=100,
        help_text="Lower numbers appear first in dropdowns.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['sort_order', 'name']
        verbose_name = 'project type'
        verbose_name_plural = 'project types'

    def __str__(self):
        return self.name

    @property
    def consigns_to_mp(self):
        return self.consignee_role == 'mp'

    @property
    def consigns_to_consultant(self):
        return self.consignee_role == 'consultant'
