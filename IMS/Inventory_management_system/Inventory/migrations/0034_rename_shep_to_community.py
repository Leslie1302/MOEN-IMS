# Phase B foundation migration:
#   1. Renames model SHEPCommunity -> Community (table rename happens
#      automatically via RenameModel).
#   2. Makes package_number optional (blank=True) so non-SHEP communities
#      can be added without it.
#   3. Adds project_type FK to ProjectType (nullable initially), then
#      backfills every existing row to the SHEP project_type, then
#      tightens constraints / verbose names.
#   4. Adds optional member_of_parliament FK and constituency CharField
#      so Cost Sharing / Streetlights releases can resolve their consignee
#      via an explicit binding instead of falling back to region match.
#
# This is non-breaking: SHEPCommunity remains importable as an alias for
# Community in Inventory/models/__init__.py, so all existing views, forms,
# and templates that import SHEPCommunity keep working through the
# transition. Subsequent Phase B turns will rename callers and templates.

from django.db import migrations, models
import auto_prefetch


def backfill_project_type_to_shep(apps, schema_editor):
    """
    Every Community row that exists at migration time predates the project
    type concept and is implicitly SHEP. Bind them to the seeded SHEP
    ProjectType. New rows after this migration will require the form to
    pick a project_type explicitly.
    """
    Community = apps.get_model('Inventory', 'Community')
    ProjectType = apps.get_model('Inventory', 'ProjectType')
    try:
        shep = ProjectType.objects.get(code='shep')
    except ProjectType.DoesNotExist:
        # Should never happen because 0033 seeds it before this migration
        # runs. Bail gracefully rather than crash the deploy.
        return
    Community.objects.filter(project_type__isnull=True).update(project_type=shep)


def reverse_backfill_project_type(apps, schema_editor):
    """Clear project_type so RemoveField can run cleanly on rollback."""
    Community = apps.get_model('Inventory', 'Community')
    Community.objects.update(project_type=None)


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0033_project_type_people_and_seed'),
    ]

    operations = [
        # 1. Rename the model -- changes the DB table from
        # Inventory_shepcommunity to Inventory_community automatically.
        migrations.RenameModel(
            old_name='SHEPCommunity',
            new_name='Community',
        ),

        # 2. Adjust verbose names so the admin and forms reflect the
        # generalized model. base_manager_name is preserved so auto_prefetch
        # continues to work (omitting it triggers a no-op makemigrations
        # proposal because the previous options included it).
        migrations.AlterModelOptions(
            name='community',
            options={
                'base_manager_name': 'prefetch_manager',
                'ordering': ['region', 'district', 'community'],
                'verbose_name': 'Community',
                'verbose_name_plural': 'Communities',
            },
        ),

        # 3. Make package_number optional. Form-level validation will still
        # require it when project_type is SHEP.
        migrations.AlterField(
            model_name='community',
            name='package_number',
            field=models.CharField(
                blank=True,
                help_text='SHEP package number for this community. SHEP-only; leave blank for other project types.',
                max_length=50,
            ),
        ),

        # 4. Add project_type FK (nullable, populated by RunPython below).
        migrations.AddField(
            model_name='community',
            name='project_type',
            field=auto_prefetch.ForeignKey(
                help_text='Which project this community is served under.',
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name='communities',
                to='Inventory.projecttype',
            ),
        ),

        # 5. Add the optional MP binding and constituency string. Both
        # nullable -- only used when project_type's consignee_role is 'mp'.
        migrations.AddField(
            model_name='community',
            name='member_of_parliament',
            field=auto_prefetch.ForeignKey(
                blank=True,
                help_text='Optional explicit MP binding. If set, used as the consignee for Cost Sharing and Streetlights releases at this community.',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='communities',
                to='Inventory.memberofparliament',
            ),
        ),
        migrations.AddField(
            model_name='community',
            name='constituency',
            field=models.CharField(
                blank=True,
                help_text='Optional. Used by the consignee resolver to look up the MP when no explicit member_of_parliament binding is set.',
                max_length=200,
            ),
        ),

        # 6. Backfill every existing row to the SHEP project_type.
        migrations.RunPython(
            backfill_project_type_to_shep,
            reverse_code=reverse_backfill_project_type,
        ),
    ]
