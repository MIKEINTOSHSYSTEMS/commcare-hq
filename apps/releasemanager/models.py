import settings
import logging
import datetime
import os

from django.db import models

from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse

from domain.models import Domain

FILE_PATH       = settings.RAPIDSMS_APPS['releasemanager']['file_path']
JARJAD_PATH     = os.path.join(FILE_PATH, "jarjad")
BUILD_PATH      = os.path.join(FILE_PATH, "builds")

# currently unused
# RESOURCE_PATH   = os.path.join(FILE_PATH, "resources")

class Jarjad(models.Model):
    ''' Index of JAR/JAD files '''
    
    uploaded_by = models.ForeignKey(User, related_name="core_uploaded") 
    # released_by = models.ForeignKey(User, related_name="core_released", null=True, blank=True) 

    is_release = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    description = models.CharField(max_length=255, null=True, blank=True, unique=True)
    build_number = models.PositiveIntegerField(help_text="the teamcity build number")
    revision_number = models.CharField(max_length=255, null=True, blank=True, help_text="the source control revision number")
    version = models.CharField(max_length=20, null=True, blank=True, help_text = 'the "release" version.  e.g. 2.0.1')

    jar_file = models.FilePathField(_('JAR File Location'), match='.*\.jar$', recursive=True, path=FILE_PATH, max_length=255)
    jad_file = models.FilePathField(_('JAD File Location'), match='.*\.jad$', recursive=True, path=FILE_PATH, max_length=255)
    
    class Meta:
        unique_together = ('build_number', 'revision_number', 'version')

    def __unicode__(self):
        return "#%s \"%s\"" %\
                (self.build_number, self.description)

    def __str__(self):
        return unicode(self).encode('utf-8')
            

    def jad_content(self):
        return open(self.jad_file).read()
    
        
    # TODO: not sure if needed, check Django file upload docs
    def save_file(self, file_obj):
        """Simple utility function to save the uploaded file to the right location and set the property of the model"""
        # try:

        # get/create destinaton directory
        save_path = os.path.join(JARJAD_PATH, str(self.build_number))
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        
        # copy file to that directory
        new_filename = os.path.join(save_path, file_obj.name)
        fout = open(new_filename, 'w')
        fout.write(file_obj.read())
        fout.close()
    
        # set self.jar_file or self.jad_file
        ext = new_filename.split('.')[-1]
        if ext == 'jad':
            self.jad_file = new_filename
        elif ext == 'jar':
            self.jar_file = new_filename
        else:
            raise "File extension not Jar or Jad"

        # except Exception, e:
        #     logging.error("Error saving file", extra={"exception":e, "new_filename":new_filename})
    


class ResourceSet(models.Model):
    domain = models.ForeignKey(Domain)
    url = models.URLField(max_length=512)
    name   = models.CharField(max_length=255, unique=True)
    is_release = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return self.name

    def __str__(self):
        return unicode(self).encode('utf-8')



class Build(models.Model):
    # domain = models.ForeignKey(Domain)
    # name   = models.CharField(max_length=255)
    is_release = models.BooleanField(default=False)
    jarjad = models.ForeignKey(Jarjad, limit_choices_to={ 'is_release' : True })
    resource_set = models.ForeignKey(ResourceSet, limit_choices_to={ 'is_release' : True })
    created_at = models.DateTimeField(auto_now_add=True)
    jar_file = models.FilePathField(_('JAR File Location'), match='.*\.jar$', recursive=True, path=FILE_PATH, max_length=255)
    jad_file = models.FilePathField(_('JAD File Location'), match='.*\.jad$', recursive=True, path=FILE_PATH, max_length=255)
    zip_file = models.FilePathField(_('ZIP File Location'), match='.*\.zip$', recursive=True, path=FILE_PATH, max_length=255)

    def jad_content(self):
        return open(self.jad_file).read()

    
# class Package(models.Model):
    
# this is to allow uploading resource files locally, rather than use source control. Not implemented for now.
# class ResourceFile(models.Model):
#     build = models.ForeignKey(Build)
#     file_path = models.FilePathField(path=FILE_PATH, max_length=255)
#     created_at = models.DateTimeField(auto_now_add=True)