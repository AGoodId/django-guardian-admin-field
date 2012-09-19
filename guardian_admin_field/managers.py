from django import forms
from django.contrib.admin import widgets
from django.contrib.auth.models import Group
from django.contrib.contenttypes.generic import GenericRelation
from django.db import models
from django.db.models.fields.related import ManyToManyRel, RelatedField, add_lazy_relation
from django.forms import fields
from django.utils.translation import ugettext as _


from guardian.models import GroupObjectPermission
from guardian.shortcuts import assign


class GroupPermRel(ManyToManyRel):
  def __init__(self):
    self.related_name = None
    self.limit_choices_to = {}
    self.symmetrical = True
    self.multiple = True
    self.through = None


class GroupPermManager(RelatedField):
  def __init__(self, verbose_name=_("Groups"),
    help_text=_("Who should be able to access this object?"), through=None, blank=False, permission='add'):
    self.permission = permission
    self.through = through or GroupObjectPermission
    self.rel = GroupPermRel()
    self.verbose_name = verbose_name
    self.help_text = help_text
    self.blank = blank
    self.editable = True
    self.unique = False
    self.creates_table = False
    self.db_column = None
    self.choices = None
    self.serialize = False
    self.null = True
    self.creation_counter = models.Field.creation_counter
    models.Field.creation_counter += 1

  def contribute_to_class(self, cls, name):
    self.name = self.column = name
    self.model = cls
    
    # Put together permission codename using the models name
    self.codename = "%s_%s" % (
      self.permission,
      self.model._meta.object_name.lower()
    )
    
    cls._meta.add_field(self)
    setattr(cls, name, self)
    
    # Store the opts for related_query_name()
    self.opts = cls._meta
    
    if not cls._meta.abstract:
      if isinstance(self.through, basestring):
        def resolve_related_class(field, model, cls):
          self.through = model
          self.post_through_setup(cls)
        add_lazy_relation(
          cls, self, self.through, resolve_related_class
        )
      else:
        self.post_through_setup(cls)

  def post_through_setup(self, cls):
    self.use_gfk = (
      self.through is None
    )
    self.rel.to = self.through._meta.get_field("group").rel.to
    if self.use_gfk:
      groups = GenericRelation(self.through)
      groups.contribute_to_class(cls, "groups")

  def formfield(self, form_class=forms.ModelMultipleChoiceField, **kwargs):
    qs = Group.objects.all()
    defaults = {
      "label": _("Groups"),
      "help_text": self.help_text,
      "required": not self.blank,
      "widget": widgets.FilteredSelectMultiple(_('groups'), False)
    }
    defaults.update(kwargs)
    return form_class(qs, **defaults)

  def value_from_object(self, instance):
    if instance.pk:
      selected_groups = []
      objects = self.through.objects.filter(**{'object_pk': instance.pk, 'permission__codename': self.codename})
      for obj in objects:
        selected_groups.append(obj.group.pk)
      return selected_groups
    return []

  def save_form_data(self, instance, data):
    # Clear any permissions set
    self.through.objects.filter(**{'object_pk': instance.pk,
      'permission__codename': self.codename}).delete()

    # Save the new permissions
    for group in data:
      assign(self.codename, group, obj=instance)

    # Update the cached boolean
    new_group_permissions = len(data) > 0
    if instance.group_permissions != new_group_permissions:
      instance.group_permissions = new_group_permissions
      instance.save()

  def bulk_related_objects(self, new_objs, using):
    return []


from south.modelsinspector import add_ignored_fields
add_ignored_fields(["^guardian_admin_field\.managers"])
