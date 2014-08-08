from django import forms
from django.contrib.admin import widgets
from django.contrib.auth.models import Group
from django.contrib.contenttypes.generic import GenericRelation
from django.db import models
from django.db.models.fields.related import ManyToManyRel, RelatedField, add_lazy_relation
from django.forms import fields
from django.utils.translation import ugettext as _
from django.utils.functional import curry
from django.db.backends import util
from django.db import connection, connections, router

from django.db.models.related import RelatedObject
from django.db.models.fields import Field

from guardian.models import GroupObjectPermission
from guardian.shortcuts import assign


class GroupPermRel(ManyToManyRel):
  def __init__(self):
    self.related_name = None
    self.limit_choices_to = {}
    self.symmetrical = True
    self.multiple = True
    self.through = None


class GroupPermManager(RelatedField, Field):
  def __init__(self, verbose_name=_("Groups"),
    help_text=_("Who should be able to access this object?"), through=None, blank=False, permission='add', **kwargs):
    Field.__init__(self, verbose_name=verbose_name, help_text=help_text, blank=blank, null=True, serialize=False)
    self.permission = permission
    self.through = through or GroupObjectPermission
    self.rel = GroupPermRel()
    self.db_table = kwargs.pop('db_table', None)

  def __get__(self, instance, model):
    if instance is not None and instance.pk is None:
      raise ValueError("%s objects need to have a primary key value "
          "before you can access their groups." % model.__name__)
    manager = _GroupPermManager(
      through=self.through, model=model, instance=instance, codename=self.codename
    )
    return manager

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
    self.m2m_db_table = curry(self._get_m2m_db_table, cls._meta)
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

  def _get_m2m_db_table(self, opts):
    "Function that can be curried to provide the m2m table name for this relation"
    if self.rel.through is not None:
      return self.rel.through._meta.db_table
    elif self.db_table:
      return self.db_table
    else:
      return util.truncate_name('%s_%s' % (opts.db_table, self.name),
                                  connection.ops.max_name_length())

  def post_through_setup(self, cls):
    self.use_gfk = (
      self.through is None
    )
    self.rel.to = self.through._meta.get_field("group").rel.to
    self.related = RelatedObject(self.through, cls, self)
    if self.use_gfk:
      groups = GenericRelation(self.through)
      groups.contribute_to_class(cls, "groups")

  def related_query_name(self):
    return self.model._meta.module_name

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


from south.modelsinspector import add_ignored_fields
add_ignored_fields(["^guardian_admin_field\.managers"])
