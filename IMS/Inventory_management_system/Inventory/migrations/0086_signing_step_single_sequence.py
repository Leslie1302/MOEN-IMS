# The signing chain spans BOTH documents in one sequence.
#
# The old constraint was unique(document_kind, order) among active steps, which
# permitted a memo step 1 and a letter step 1 — two independent chains with no
# defined order between them. Nothing stopped the Chief Director signing the
# release letter before the Ag. Director had approved the memo, which is
# backwards: the signed memo IS the authority for the letter.
#
# Now unique(order) among active steps, so the release has a single ordered
# queue of approvers.
#
# NOTE for existing installations: if you already have a memo step 1 and a
# letter step 1, the new constraint will reject them. Renumber first —
# typically memo = 1, letter = 2. The data migration below does that
# automatically for the common two-step case.

from django.db import migrations, models


def renumber_to_single_sequence(apps, schema_editor):
    """Give active steps distinct positions, memo before letter.

    Only touches rows that would violate the new constraint, and preserves any
    ordering already expressed within each document.
    """
    SigningStep = apps.get_model('Inventory', 'SigningStep')
    active = list(SigningStep.objects.filter(active=True))
    if not active:
        return

    # memo steps first, then letter, each keeping its existing relative order.
    kind_rank = {'memo': 0, 'letter': 1}
    active.sort(key=lambda s: (kind_rank.get(s.document_kind, 2), s.order, s.pk))

    for position, step in enumerate(active, start=1):
        if step.order != position:
            step.order = position
            step.save(update_fields=['order'])


def noop(apps, schema_editor):
    """Reversing the constraint needs no data change — duplicates are allowed again."""


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0085_archive_release_letter'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='signingstep',
            name='unique_active_step_order_per_document',
        ),
        migrations.RunPython(renumber_to_single_sequence, noop),
        migrations.AlterModelOptions(
            name='signingstep',
            options={'ordering': ['order', 'document_kind'],
                     'verbose_name': 'signing step',
                     'verbose_name_plural': 'signing steps'},
        ),
        migrations.AlterField(
            model_name='signingstep',
            name='document_kind',
            field=models.CharField(
                choices=[('memo', 'Approval memo'), ('letter', 'Release letter')],
                db_index=True, max_length=10,
                help_text='Which document this step signs.'),
        ),
        migrations.AlterField(
            model_name='signingstep',
            name='order',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Position in the release's signing sequence — ACROSS both "
                          "documents, not within one. Typically 1 = Ag. Director Power "
                          "signs the memo, 2 = Chief Director signs the letter."),
        ),
        migrations.AddConstraint(
            model_name='signingstep',
            constraint=models.UniqueConstraint(
                condition=models.Q(('active', True)),
                fields=('order',),
                name='unique_active_step_order'),
        ),
    ]
