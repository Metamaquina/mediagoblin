# GNU MediaGoblin -- federated, autonomous media hosting
# Copyright (C) 2011 MediaGoblin contributors.  See AUTHORS.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime, uuid

from mongokit import Document

from mediagoblin.auth import lib as auth_lib
from mediagoblin import mg_globals
from mediagoblin.db import migrations
from mediagoblin.db.util import ASCENDING, DESCENDING, ObjectId
from mediagoblin.tools.pagination import Pagination
from mediagoblin.tools import url, common

###################
# Custom validators
###################

########
# Models
########


class User(Document):
    """
    A user of MediaGoblin.

    Structure:
     - username: The username of this user, should be unique to this instance.
     - email: Email address of this user
     - created: When the user was created
     - plugin_data: a mapping of extra plugin information for this User.
       Nothing uses this yet as we don't have plugins, but someday we
       might... :)
     - pw_hash: Hashed version of user's password.
     - email_verified: Whether or not the user has verified their email or not.
       Most parts of the site are disabled for users who haven't yet.
     - status: whether or not the user is active, etc.  Currently only has two
       values, 'needs_email_verification' or 'active'.  (In the future, maybe
       we'll change this to a boolean with a key of 'active' and have a
       separate field for a reason the user's been disabled if that's
       appropriate... email_verified is already separate, after all.)
     - verification_key: If the user is awaiting email verification, the user
       will have to provide this key (which will be encoded in the presented
       URL) in order to confirm their email as active.
     - is_admin: Whether or not this user is an administrator or not.
     - url: this user's personal webpage/website, if appropriate.
     - bio: biography of this user (plaintext, in markdown)
     - bio_html: biography of the user converted to proper HTML.
    """
    __collection__ = 'users'

    structure = {
        'username': unicode,
        'email': unicode,
        'created': datetime.datetime,
        'plugin_data': dict, # plugins can dump stuff here.
        'pw_hash': unicode,
        'email_verified': bool,
        'status': unicode,
        'verification_key': unicode,
        'is_admin': bool,
        'url' : unicode,
        'bio' : unicode,     # May contain markdown
        'bio_html': unicode, # May contain plaintext, or HTML
        'fp_verification_key': unicode, # forgotten password verification key
        'fp_token_expire': datetime.datetime
        }

    required_fields = ['username', 'created', 'pw_hash', 'email']

    default_values = {
        'created': datetime.datetime.utcnow,
        'email_verified': False,
        'status': u'needs_email_verification',
        'verification_key': lambda: unicode(uuid.uuid4()),
        'is_admin': False}

    def check_login(self, password):
        """
        See if a user can login with this password
        """
        return auth_lib.bcrypt_check_password(
            password, self['pw_hash'])


class MediaEntry(Document):
    """
    Record of a piece of media.

    Structure:
     - uploader: A reference to a User who uploaded this.

     - title: Title of this work

     - slug: A normalized "slug" which can be used as part of a URL to retrieve
       this work, such as 'my-works-name-in-slug-form' may be viewable by
       'http://mg.example.org/u/username/m/my-works-name-in-slug-form/'
       Note that since URLs are constructed this way, slugs must be unique
       per-uploader.  (An index is provided to enforce that but code should be
       written on the python side to ensure this as well.)

     - created: Date and time of when this piece of work was uploaded.

     - description: Uploader-set description of this work.  This can be marked
       up with MarkDown for slight fanciness (links, boldness, italics,
       paragraphs...)

     - description_html: Rendered version of the description, run through
       Markdown and cleaned with our cleaning tool.

     - media_type: What type of media is this?  Currently we only support
       'image' ;)

     - media_data: Extra information that's media-format-dependent.
       For example, images might contain some EXIF data that's not appropriate
       to other formats.  You might store it like:

         mediaentry['media_data']['exif'] = {
             'manufacturer': 'CASIO',
             'model': 'QV-4000',
             'exposure_time': .659}

       Alternately for video you might store:

         # play length in seconds
         mediaentry['media_data']['play_length'] = 340

       ... so what's appropriate here really depends on the media type.

     - plugin_data: a mapping of extra plugin information for this User.
       Nothing uses this yet as we don't have plugins, but someday we
       might... :)

     - tags: A list of tags.  Each tag is stored as a dictionary that has a key
       for the actual name and the normalized name-as-slug, so ultimately this
       looks like:
         [{'name': 'Gully Gardens',
           'slug': 'gully-gardens'},
          {'name': 'Castle Adventure Time?!",
           'slug': 'castle-adventure-time'}]

     - state: What's the state of this file?  Active, inactive, disabled, etc...
       But really for now there are only two states:
        "unprocessed": uploaded but needs to go through processing for display
        "processed": processed and able to be displayed

     - favorites: Number of times a user has marked this media as a favorite.

     - queued_media_file: storage interface style filepath describing a file
       queued for processing.  This is stored in the mg_globals.queue_store
       storage system.

     - queued_task_id: celery task id.  Use this to fetch the task state.

     - media_files: Files relevant to this that have actually been processed
       and are available for various types of display.  Stored like:
         {'thumb': ['dir1', 'dir2', 'pic.png'}

     - attachment_files: A list of "attachment" files, ones that aren't
       critical to this piece of media but may be usefully relevant to people
       viewing the work.  (currently unused.)

     - fail_error: path to the exception raised 
     - fail_metadata: 
    """
    __collection__ = 'media_entries'

    structure = {
        'uploader': ObjectId,
        'title': unicode,
        'slug': unicode,
        'created': datetime.datetime,
        'description': unicode, # May contain markdown/up
        'description_html': unicode, # May contain plaintext, or HTML
        'media_type': unicode,
        'media_data': dict, # extra data relevant to this media_type
        'plugin_data': dict, # plugins can dump stuff here.
        'tags': [dict],
        'state': unicode,
        'favorites': int,

        # For now let's assume there can only be one main file queued
        # at a time
        'queued_media_file': [unicode],
        'queued_task_id': unicode,

        # A dictionary of logical names to filepaths
        'media_files': dict,

        # The following should be lists of lists, in appropriate file
        # record form
        'attachment_files': list,

        # If things go badly in processing things, we'll store that
        # data here
        'fail_error': unicode,
        'fail_metadata': dict}

    required_fields = [
        'uploader', 'created', 'media_type', 'slug']

    default_values = {
        'created': datetime.datetime.utcnow,
        'state': u'unprocessed',
        'favorites': 0}

    def get_comments(self):
        return self.db.MediaComment.find({
                'media_entry': self['_id']}).sort('created', DESCENDING)

    def get_display_media(self, media_map, fetch_order=common.DISPLAY_IMAGE_FETCHING_ORDER):
        """
        Find the best media for display.

        Args:
        - media_map: a dict like
          {u'image_size': [u'dir1', u'dir2', u'image.jpg']}
        - fetch_order: the order we should try fetching images in

        Returns:
        (media_size, media_path)
        """
        media_sizes = media_map.keys()

        for media_size in common.DISPLAY_IMAGE_FETCHING_ORDER:
            if media_size in media_sizes:
                return media_map[media_size]

    def main_mediafile(self):
        pass

    def generate_slug(self):
        self['slug'] = url.slugify(self['title'])

        duplicate = mg_globals.database.media_entries.find_one(
            {'slug': self['slug']})

        if duplicate:
            self['slug'] = "%s-%s" % (self['_id'], self['slug'])

    def url_for_self(self, urlgen):
        """
        Generate an appropriate url for ourselves

        Use a slug if we have one, else use our '_id'.
        """
        uploader = self.uploader()

        if self.get('slug'):
            return urlgen(
                'mediagoblin.user_pages.media_home',
                user=uploader['username'],
                media=self['slug'])
        else:
            return urlgen(
                'mediagoblin.user_pages.media_home',
                user=uploader['username'],
                media=unicode(self['_id']))

    def url_to_prev(self, urlgen):
        """
        Provide a url to the previous entry from this user, if there is one
        """
        cursor = self.db.MediaEntry.find({'_id' : {"$gt": self['_id']},
                                          'uploader': self['uploader'],
                                          'state': 'processed'}).sort(
                                                    '_id', ASCENDING).limit(1)
        if cursor.count():
            return urlgen('mediagoblin.user_pages.media_home',
                          user=self.uploader()['username'],
                          media=unicode(cursor[0]['slug']))

    def url_to_next(self, urlgen):
        """
        Provide a url to the next entry from this user, if there is one
        """
        cursor = self.db.MediaEntry.find({'_id' : {"$lt": self['_id']},
                                          'uploader': self['uploader'],
                                          'state': 'processed'}).sort(
                                                    '_id', DESCENDING).limit(1)

        if cursor.count():
            return urlgen('mediagoblin.user_pages.media_home',
                          user=self.uploader()['username'],
                          media=unicode(cursor[0]['slug']))

    def uploader(self):
        return self.db.User.find_one({'_id': self['uploader']})

    def get_fail_exception(self):
        """
        Get the exception that's appropriate for this error
        """
        if self['fail_error']:
            return common.import_component(self['fail_error'])


class MediaComment(Document):
    """
    A comment on a MediaEntry.

    Structure:
     - media_entry: The media entry this comment is attached to
     - author: user who posted this comment
     - created: when the comment was created
     - content: plaintext (but markdown'able) version of the comment's content.
     - content_html: the actual html-rendered version of the comment displayed.
       Run through Markdown and the HTML cleaner.
    """

    __collection__ = 'media_comments'

    structure = {
        'media_entry': ObjectId,
        'author': ObjectId,
        'created': datetime.datetime,
        'content': unicode,
        'content_html': unicode}

    required_fields = [
        'media_entry', 'author', 'created', 'content']

    default_values = {
        'created': datetime.datetime.utcnow}

    def media_entry(self):
        return self.db.MediaEntry.find_one({'_id': self['media_entry']})

    def author(self):
        return self.db.User.find_one({'_id': self['author']})

class UserFavorite(Document):
    """
    A user's selection of a MediaEntry as a favorite

    Structure:
     - user: The User who favorited the MediaEntry
     - media_entry: The MediaEntry favorited
     - created: When the MediaEntry was favorited
    """

    __collection__ = 'user_favorites'

    structure = {
        'user': ObjectId,
        'media_entry': ObjectId,
        'created': datetime.datetime
        }

    required_fields = ['user', 'media_entry', 'created']

    default_values = {
        'created': datetime.datetime.utcnow}

REGISTER_MODELS = [
    MediaEntry,
    User,
    MediaComment,
    UserFavorite]


def register_models(connection):
    """
    Register all models in REGISTER_MODELS with this connection.
    """
    connection.register(REGISTER_MODELS)

