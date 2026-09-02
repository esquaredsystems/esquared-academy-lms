"""
Give the topics that already exist a path.

Every topic before this migration is top-level, so its path is its own id
and its depth is 0. `Topic.save()` maintains both from here on.
"""

from django.db import migrations


def populate(apps, schema_editor):
    Topic = apps.get_model("app", "Topic")
    rows = list(Topic.objects.filter(path="").only("pk"))
    for row in rows:
        row.path = str(row.pk)
        row.depth = 0
    if rows:
        Topic.objects.bulk_update(rows, ["path", "depth"], batch_size=500)


def clear(apps, schema_editor):
    apps.get_model("app", "Topic").objects.update(path="", depth=0)


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0010_topic_hierarchy"),
    ]

    operations = [
        migrations.RunPython(populate, clear),
    ]
