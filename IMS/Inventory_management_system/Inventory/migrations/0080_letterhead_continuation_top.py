# The letterhead is printed stock for page 1 only; continuation pages go on
# plain paper. Page 2+ therefore needs its own (much smaller) top margin — there
# is no header band to clear. Left/right/bottom stay as calibrated so the text
# block on a continuation page lines up with page 1.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0079_letterhead_memo_insets'),
    ]

    operations = [
        migrations.AddField(
            model_name='letterhead',
            name='cont_inset_top',
            field=models.PositiveSmallIntegerField(
                default=62,
                help_text='Top margin in points for continuation pages (page 2 onwards, plain paper).'),
        ),
    ]
