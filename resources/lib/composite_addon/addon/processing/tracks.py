# -*- coding: utf-8 -*-
"""

    Copyright (C) 2011-2018 PleXBMC (plugin.video.plexbmc) by hippojay (Dave Hawes-Johnson)
    Copyright (C) 2018-2020 Composite (plugin.video.composite_for_plex)

    This file is part of Composite (plugin.video.composite_for_plex)

    SPDX-License-Identifier: GPL-2.0-or-later
    See LICENSES/GPL-2.0-or-later.txt for more information.
"""

from kodi_six import xbmc  # pylint: disable=import-error
from kodi_six import xbmcplugin  # pylint: disable=import-error

from ..common import get_handle
from ..containers import Item
from ..items.movie import create_movie_item
from ..items.photo import create_photo_item
from ..items.track import create_track_item
from ..utils import get_xml


def process_tracks(context, url, tree=None):
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DURATION)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_SONG_RATING)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TRACKNUM)

    tree = get_xml(context, url, tree)
    if tree is None:
        return

    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()

    server = context.plex_network.get_server_from_url(url)

    content_type = 'songs'
    items = []
    for track in tree:
        item = Item(server, url, tree, track)
        if track.tag.lower() == 'track':
            items.append(create_track_item(context, item))
        elif track.tag.lower() == 'photo':  # mixed content audio playlist
            content_type = 'movies'  # use movies for mixed content playlists
            items.append(create_photo_item(context, item))
        elif track.tag.lower() == 'video':  # mixed content audio playlist
            content_type = 'movies'  # use movies for mixed content playlists
            items.append(create_movie_item(context, item))

    xbmcplugin.setContent(get_handle(), content_type)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
