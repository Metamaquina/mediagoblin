# MediaGoblin -- federated, autonomous media hosting
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

from webob import exc

from mediagoblin import messages, mg_globals
from mediagoblin.db.util import DESCENDING, ObjectId
from mediagoblin.tools.text import cleaned_markdown_conversion
from mediagoblin.tools.response import render_to_response, render_404, redirect
from mediagoblin.tools.translate import pass_to_ugettext as _
from mediagoblin.tools.pagination import Pagination
from mediagoblin.tools.files import delete_media_files
from mediagoblin.user_pages import forms as user_forms

from mediagoblin.decorators import (uses_pagination, get_user_media_entry,
    require_active_login, user_may_delete_media)

from werkzeug.contrib.atom import AtomFeed


@uses_pagination
def user_home(request, page):
    """'Homepage' of a User()"""
    user = request.db.User.find_one({
            'username': request.matchdict['user']})
    if not user:
        return render_404(request)
    elif user['status'] != u'active':
        return render_to_response(
            request,
            'mediagoblin/user_pages/user.html',
            {'user': user})

    cursor = request.db.MediaEntry.find(
        {'uploader': user['_id'],
         'state': 'processed'}).sort('created', DESCENDING)

    pagination = Pagination(page, cursor)
    media_entries = pagination()

    #if no data is available, return NotFound
    if media_entries == None:
        return render_404(request)
    
    user_gallery_url = request.urlgen(
        'mediagoblin.user_pages.user_gallery',
        user=user['username'])

    return render_to_response(
        request,
        'mediagoblin/user_pages/user.html',
        {'user': user,
         'user_gallery_url': user_gallery_url,
         'media_entries': media_entries,
         'pagination': pagination})

@uses_pagination
def user_gallery(request, page):
    """'Gallery' of a User()"""
    user = request.db.User.find_one({
            'username': request.matchdict['user'],
            'status': 'active'})
    if not user:
        return render_404(request)

    cursor = request.db.MediaEntry.find(
        {'uploader': user['_id'],
         'state': 'processed'}).sort('created', DESCENDING)

    pagination = Pagination(page, cursor)
    media_entries = pagination()

    #if no data is available, return NotFound
    if media_entries == None:
        return render_404(request)
    
    return render_to_response(
        request,
        'mediagoblin/user_pages/gallery.html',
        {'user': user,
         'media_entries': media_entries,
         'pagination': pagination})

MEDIA_COMMENTS_PER_PAGE = 50

@get_user_media_entry
@uses_pagination
def media_home(request, media, page, **kwargs):
    """
    'Homepage' of a MediaEntry()
    """
    if ObjectId(request.matchdict.get('comment')):
        pagination = Pagination(
            page, media.get_comments(), MEDIA_COMMENTS_PER_PAGE,
            ObjectId(request.matchdict.get('comment')))
    else:
        pagination = Pagination(
            page, media.get_comments(), MEDIA_COMMENTS_PER_PAGE)

    comments = pagination()

    comment_form = user_forms.MediaCommentForm(request.POST)

    # See if the user has favorited this media
    user = request.db.User.find_one({
            'username': request.matchdict['user']})

    has_favorited = False

    if request.user:
        cursor = request.db.UserFavorite.find(
            {'user': request.user['_id'],
             'media_entry': ObjectId(media['_id'])})

        if cursor.count() > 0:
            has_favorited = True

    return render_to_response(
        request,
        'mediagoblin/user_pages/media.html',
        {'media': media,
         'comments': comments,
         'has_favorited': has_favorited,
         'pagination': pagination,
         'comment_form': comment_form,
         'app_config': mg_globals.app_config})


@require_active_login
def media_post_comment(request):
    """
    recieves POST from a MediaEntry() comment form, saves the comment.
    """
    comment = request.db.MediaComment()
    comment['media_entry'] = ObjectId(request.matchdict['media'])
    comment['author'] = request.user['_id']
    comment['content'] = unicode(request.POST['comment_content'])

    comment['content_html'] = cleaned_markdown_conversion(comment['content'])

    comment.save()

    messages.add_message(
        request, messages.SUCCESS,
        'Comment posted!')

    return redirect(request, 'mediagoblin.user_pages.media_home',
        media = request.matchdict['media'],
        user = request.matchdict['user'])


@get_user_media_entry
@require_active_login
@user_may_delete_media
def media_confirm_delete(request, media):

    form = user_forms.ConfirmDeleteForm(request.POST)

    if request.method == 'POST' and form.validate():
        if form.confirm.data is True:
            username = media.uploader()['username']

            # Delete all files on the public storage
            delete_media_files(media)

            media.delete()

            return redirect(request, "mediagoblin.user_pages.user_home",
                user=username)
        else:
            return exc.HTTPFound(
                location=media.url_for_self(request.urlgen))

    if ((request.user[u'is_admin'] and
         request.user[u'_id'] != media.uploader()[u'_id'])):
        messages.add_message(
            request, messages.WARNING,
            _("You are about to delete another user's media. "
              "Proceed with caution."))

    return render_to_response(
        request,
        'mediagoblin/user_pages/media_confirm_delete.html',
        {'media': media,
         'form': form})

@require_active_login
def media_favorite(request):
    """
    Marks media as a favorite of user
    """

    # Get the MediaEntry
    media_entry_id = ObjectId(request.matchdict['media'])
    media_entry = request.db.MediaEntry.find_one({'_id': media_entry_id})

    # See if this user has already favorited this media
    existing_entry = request.db.UserFavorite.find_one({'media_entry': media_entry_id, 
                                                       'user': request.user['_id']})

    # If the user hasn't already favorited this, create a UserFavorite
    # instance and increment the entry's favorites count
    if not existing_entry:
        user_favorite = request.db.UserFavorite()
        user_favorite['media_entry'] = media_entry_id
        user_favorite['user'] = request.user['_id']
        user_favorite.save()

        request.db['media_entries'].update( { '_id': media_entry_id }, { '$inc' : { 'favorites' : 1 } } )

    # If the user has favorited it, unfavorite it
    else:
        existing_entry.delete()

        request.db['media_entries'].update( { '_id': media_entry_id }, { '$inc' : { 'favorites' : -1 } } )

    return redirect(request, 'mediagoblin.user_pages.media_home',
        media = request.matchdict['media'],
        user = request.matchdict['user'])


def atom_feed(request):
    """
    generates the atom feed with the newest images
    """

    user = request.db.User.find_one({
               'username': request.matchdict['user'],
               'status': 'active'})
    if not user:
        return render_404(request)

    cursor = request.db.MediaEntry.find({
                 'uploader': user['_id'],
                 'state': 'processed'}) \
                 .sort('created', DESCENDING) \
                 .limit(ATOM_DEFAULT_NR_OF_UPDATED_ITEMS)

    feed = AtomFeed(request.matchdict['user'],
               feed_url=request.url,
               url=request.host_url)
    
    for entry in cursor:
        feed.add(entry.get('title'),
            entry.get('description_html'),
            content_type='html',
            author=request.matchdict['user'],
            updated=entry.get('created'),
            url=entry.url_for_self(request.urlgen))

    return feed.get_response()


@require_active_login
def processing_panel(request):
    """
    Show to the user what media is still in conversion/processing...
    and what failed, and why!
    """
    # Get the user
    user = request.db.User.find_one(
        {'username': request.matchdict['user'],
         'status': 'active'})

    # Make sure the user exists and is active
    if not user:
        return render_404(request)
    elif user['status'] != u'active':
        return render_to_response(
            request,
            'mediagoblin/user_pages/user.html',
            {'user': user})

    # XXX: Should this be a decorator?
    #
    # Make sure we have permission to access this user's panel.  Only
    # admins and this user herself should be able to do so.
    if not (user[u'_id'] == request.user[u'_id']
            or request.user.is_admin):
        # No?  Let's simply redirect to this user's homepage then.
        return redirect(
            request, 'mediagoblin.user_pages.user_home',
            user=request.matchdict['user'])

    # Get media entries which are in-processing
    processing_entries = request.db.MediaEntry.find(
        {'uploader': user['_id'],
         'state': 'processing'}).sort('created', DESCENDING)

    # Get media entries which have failed to process
    failed_entries = request.db.MediaEntry.find(
        {'uploader': user['_id'],
         'state': 'failed'}).sort('created', DESCENDING)

    # Render to response
    return render_to_response(
        request,
        'mediagoblin/user_pages/processing_panel.html',
        {'user': user,
         'processing_entries': processing_entries,
         'failed_entries': failed_entries})
