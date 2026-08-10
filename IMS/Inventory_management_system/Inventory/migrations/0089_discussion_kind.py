# Two kinds of call: a conversation, and a correction.
#
# `DiscussionRequest` was deliberately one-tier — a call, never a rejection —
# because a chain with a reject state teaches people to use it for small things
# and every release ends up carrying a black mark for a typo.
#
# That reasoning holds for the conversation. It does not cover the other case: a
# signatory who has found an actual error in a document that is already signed.
# Until now the only route there was void-and-reissue, and the practical effect
# was that corrections happened by phone and the record showed a clean release
# that had quietly been rebuilt. An off-record correction is worse than a
# recorded one, so the correction now has a name, a note, and consequences.
#
# `kind='correction'` supersedes the signatures on the named document and every
# later step, unlocks them, and returns the release to the officer. Signatures
# are never deleted — the record that someone signed v1 survives the issue of v2.
#
# Defaults to 'routine', so every existing row keeps exactly the meaning it had.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0088_sent_for_signature'),
    ]

    operations = [
        migrations.AddField(
            model_name='discussionrequest',
            name='kind',
            field=models.CharField(
                max_length=12,
                choices=[
                    ('routine', 'Routine discussion — nothing changes'),
                    ('correction', 'Correction required — returns to the officer'),
                ],
                default='routine',
                db_index=True,
                help_text="A routine call moves nothing. A correction supersedes the "
                          "signatures on the named document and every later step, and "
                          "returns the release to the preparing officer."),
        ),
        migrations.AddField(
            model_name='discussionrequest',
            name='superseded_count',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="How many signatures this correction superseded. Recorded so "
                          "the release history shows what a correction actually cost."),
        ),
    ]
