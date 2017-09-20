from django import forms
from django.contrib.admin import widgets
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django import VERSION
from django.db.models.fields.related import ManyToManyRel, RelatedField, add_lazy_relation
if VERSION < (1, 8):
  from django.db.models.related import RelatedObject
else:
  RelatedObject = None
from django.db.models.fields import Field
from django.forms import fields
from django.utils.translation import ugettext_lazy as _


from guardian.models import GroupObjectPermission
from guardian.shortcuts import assign


def _model_name(model):
  if VERSION < (1, 7):
    return model._meta.module_name
  else:
    return model._meta.model_name


class GroupPermRel(ManyToManyRel):
  def __init__(self, field):
    self.related_name = None
    self.limit_choices_to = {}
    self.symmetrical = True
    self.multiple = True
    self.through = None
    self.field = field

class GroupPermManager(RelatedField, Field):
  def __init__(self, verbose_name=_("Groups"),
    help_text=_("Who should be able to access this object?"), through=None, blank=False, permission='add'):
    Field.__init__(self, verbose_name=verbose_name, help_text=help_text, blank=blank, null=True, serialize=False)
    self.permission = permission
    self.through = through or GroupObjectPermission
    self.rel = GroupPermRel(self)

  def m2m_target_field_name(self):
    return self.model._meta.pk.name

  def m2m_reverse_target_field_name(self):
    return self.rel.to._meta.pk.name

  def m2m_column_name(self):
    if self.use_gfk:
      return self.through._meta.virtual_fields[0].fk_field
    return self.through._meta.get_field('content_object').column

  def db_type(self, connection=None):
    return None

  def m2m_db_table(self):
    return self.through._meta.db_table

  def __get__(self, instance, model):
    if instance is not None and instance.pk is None:
      raise ValueError("%s objects need to have a primary key value "
          "before you can access their groups." % model.__name__)
    manager = _GroupPermManager(
      through=self.through, model=model, instance=instance, codename=self.codename
    )
    return manager

  def contribute_to_class(self, cls, name):
    self.name = self.column = self.attname = name
    if self.column:
      self.concrete = True
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
    if RelatedObject is not None:
      self.related = RelatedObject(self.through, cls, self)
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

  def related_query_name(self):
    return _model_name(self.model)

  def bulk_related_objects(self, new_objs, using):
    return []


class _GroupPermManager(models.Manager):
  def __init__(self, through, model, instance, codename):
    self.through = through
    self.model = model
    self.instance = instance
    self.codename = codename

  def get_query_set(self):
    group_ids = self.through.objects.filter(object_pk=self.instance.pk,
        permission__codename=self.codename).values_list('group_id', flat=True)
    return Group.objects.filter(id__in=group_ids)


if VERSION < (1, 7):
  from south.modelsinspector import add_ignored_fields
  add_ignored_fields(["^guardian_admin_field\.managers"])
