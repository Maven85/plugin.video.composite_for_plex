"""
    @document   : plexbmc.py
    @package    : PleXBMC add-on
    @author     : Hippojay (aka Dave Hawes-Johnson)
    @copyright  : 2011-2015, Hippojay
    @version    : 4.0 (Helix)

    @license    : Gnu General Public License - see LICENSE.TXT
    @description: pleXBMC XBMC add-on

    This file is part of the XBMC PleXBMC Plugin.

    PleXBMC Plugin is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    PleXBMC Plugin is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with PleXBMC Plugin.  If not, see <http://www.gnu.org/licenses/>.
"""

import time
import random
import datetime
import urllib

import xbmcplugin
import xbmcgui

from six.moves.urllib_parse import urlparse

from .common import *  # Needed first to setup import locations
from .plex import plex


ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id').decode("utf-8")
ADDON_ICON = ADDON.getAddonInfo('icon').decode("utf-8")
ADDON_NAME = ADDON.getAddonInfo('name').decode("utf-8")
ADDON_PATH = ADDON.getAddonInfo('path').decode("utf-8")
ADDON_VERSION = ADDON.getAddonInfo('version').decode("utf-8")
ADDON_DATA_PATH = xbmc.translatePath("special://profile/addon_data/%s" % ADDON_ID).decode("utf-8")
KODI_VERSION = int(xbmc.getInfoLabel("System.BuildVersion").split(".")[0])
WINDOW = xbmcgui.Window(10000)
SETTING = ADDON.getSetting
KODILANGUAGE = xbmc.getLanguage(xbmc.ISO_639_1)


def select_media_type(part_data, server, dvdplayback=False):
    stream = part_data['key']
    f = part_data['file']
    filelocation = ''

    if (f is None) or (settings.get_stream() == "1"):
        log_print.debug("Selecting stream")
        return server.get_formatted_url(stream)

    # First determine what sort of 'file' file is

    if f[0:2] == "\\\\":
        log_print.debug("Detected UNC source file")
        ftype = "UNC"
    elif f[0:1] == "/" or f[0:1] == "\\":
        log_print.debug("Detected unix source file")
        ftype = "nixfile"
    elif f[1:3] == ":\\" or f[1:2] == ":/":
        log_print.debug("Detected windows source file")
        ftype = "winfile"
    else:
        log_print.debug("Unknown file type source: %s" % file)
        ftype = None

    # 0 is auto select.  basically check for local file first, then stream if not found
    if settings.get_stream() == "0":
        # check if the file can be found locally
        if ftype == "nixfile" or ftype == "winfile":
            log_print.debug("Checking for local file")
            try:
                exists = open(f, 'r')
                log_print.debug("Local f found, will use this")
                exists.close()
                return "file:%s" % file
            except:
                pass

        log_print.debug("No local file")
        if dvdplayback:
            log_print.debug("Forcing SMB for DVD playback")
            settings.set_stream("2")
        else:
            return server.get_formatted_url(stream)

    # 2 is use SMB
    elif settings.get_stream() == "2" or settings.get_stream() == "3":

        f = urllib.unquote(f)
        if settings.get_stream() == "2":
            protocol = "smb"
        else:
            protocol = "afp"

        log_print.debug("Selecting smb/unc")
        if ftype == "UNC":
            filelocation = "%s:%s" % (protocol, f.replace("\\", "/"))
        else:
            # Might be OSX type, in which case, remove Volumes and replace with server
            server = server.get_location().split(':')[0]
            loginstring = ""

            if settings.get_setting('nasoverride'):
                if settings.get_setting('nasoverrideip'):
                    server = settings.get_setting('nasoverrideip')
                    log_print.debug("Overriding server with: %s" % server)

                if settings.get_setting('nasuserid'):
                    loginstring = "%s:%s@" % (settings.get_setting('nasuserid'), settings.get_setting('naspass'))
                    log_print.debug("Adding AFP/SMB login info for user: %s" % settings.get_setting('nasuserid'))

            if f.find('Volumes') > 0:
                filelocation = "%s:/%s" % (protocol, f.replace("Volumes", loginstring + server))
            else:
                if ftype == "winfile":
                    filelocation = ("%s://%s%s/%s" % (protocol, loginstring, server, f[3:].replace("\\", "/")))
                else:
                    # else assume its a file local to server available over smb/samba.  Add server name to file path.
                    filelocation = "%s://%s%s%s" % (protocol, loginstring, server, f)

        if settings.get_setting('nasoverride') and settings.get_setting('nasroot'):
            # Re-root the file path
            log_print.debug("Altering path %s so root is: %s" % (filelocation, settings.get_setting('nasroot')))
            if '/' + settings.get_setting('nasroot') + '/' in filelocation:
                components = filelocation.split('/')
                index = components.index(settings.get_setting('nasroot'))
                for i in range(3, index):
                    components.pop(3)
                filelocation = '/'.join(components)
    else:
        log_print.debug("No option detected, streaming is safest to choose")
        filelocation = server.get_formatted_url(stream)

    log_print.debug("Returning URL: %s " % filelocation)
    return filelocation


def add_item_to_gui(url, details, extra_data, context=None, folder=True):
    log_print.debug("Adding Dir for [%s]\n"
                    "      Passed details: %s\n"
                    "      Passed extraData: %s" % (details.get('title', 'Unknown'), details, extra_data))

    # Create the URL to pass to the item
    if not folder and extra_data['type'] == "image":
        link_url = url
    elif url.startswith('http') or url.startswith('file'):
        link_url = "%s?url=%s&mode=%s" % (argv[0], urllib.quote(url), extra_data.get('mode', 0))
    else:
        link_url = "%s?url=%s&mode=%s" % (argv[0], url, extra_data.get('mode', 0))

    if extra_data.get('parameters'):
        for argument, value in extra_data.get('parameters').items():
            link_url = "%s&%s=%s" % (link_url, argument, urllib.quote(value))

    log_print.debug("URL to use for listing: %s" % link_url)

    liz = xbmcgui.ListItem(item_translate(details.get('title', 'Unknown'), extra_data.get('source'), folder), iconImage=extra_data.get('thumb', GENERIC_THUMBNAIL), thumbnailImage=extra_data.get('thumb', GENERIC_THUMBNAIL))

    log_print.debug("Setting thumbnail as %s" % extra_data.get('thumb', GENERIC_THUMBNAIL))

    # Set the properties of the item, such as summary, name, season, etc
    liz.setInfo(type=extra_data.get('type', 'Video'), infoLabels=details)

    # Music related tags
    if extra_data.get('type', '').lower() == "music":
        liz.setProperty('Artist_Genre', details.get('genre', ''))
        liz.setProperty('Artist_Description', extra_data.get('plot', ''))
        liz.setProperty('Album_Description', extra_data.get('plot', ''))

    # For all end items    
    if not folder:
        liz.setProperty('IsPlayable', 'true')

        if extra_data.get('type', 'video').lower() == "video":
            liz.setProperty('TotalTime', str(extra_data.get('duration')))
            liz.setProperty('ResumeTime', str(extra_data.get('resume')))

            if not settings.get_setting('skipflags'):
                log_print.debug("Setting VrR as : %s" % extra_data.get('VideoResolution', ''))
                liz.setProperty('VideoResolution', extra_data.get('VideoResolution', ''))
                liz.setProperty('VideoCodec', extra_data.get('VideoCodec', ''))
                liz.setProperty('AudioCodec', extra_data.get('AudioCodec', ''))
                liz.setProperty('AudioChannels', extra_data.get('AudioChannels', ''))
                liz.setProperty('VideoAspect', extra_data.get('VideoAspect', ''))

                video_codec = {}
                if extra_data.get('xbmc_VideoCodec'):
                    video_codec['codec'] = extra_data.get('xbmc_VideoCodec')
                if extra_data.get('xbmc_VideoAspect'):
                    video_codec['aspect'] = float(extra_data.get('xbmc_VideoAspect'))
                if extra_data.get('xbmc_height'):
                    video_codec['height'] = int(extra_data.get('xbmc_height'))
                if extra_data.get('xbmc_width'):
                    video_codec['width'] = int(extra_data.get('xbmc_width'))
                if extra_data.get('duration'):
                    video_codec['duration'] = int(extra_data.get('duration'))

                audio_codec = {}
                if extra_data.get('xbmc_AudioCodec'):
                    audio_codec['codec'] = extra_data.get('xbmc_AudioCodec')
                if extra_data.get('xbmc_AudioChannels'):
                    audio_codec['channels'] = int(extra_data.get('xbmc_AudioChannels'))

                liz.addStreamInfo('video', video_codec)
                liz.addStreamInfo('audio', audio_codec)

    if extra_data.get('source') == 'tvshows' or extra_data.get('source') == 'tvseasons':
        # Then set the number of watched and unwatched, which will be displayed per season
        liz.setProperty('TotalEpisodes', str(extra_data['TotalEpisodes']))
        liz.setProperty('WatchedEpisodes', str(extra_data['WatchedEpisodes']))
        liz.setProperty('UnWatchedEpisodes', str(extra_data['UnWatchedEpisodes']))

        # Hack to show partial flag for TV shows and seasons
        if extra_data.get('partialTV') == 1:
            liz.setProperty('TotalTime', '100')
            liz.setProperty('ResumeTime', '50')

    # assign artwork
    fanart = extra_data.get('fanart_image', '')
    thumb = extra_data.get('thumb', '')
    banner = extra_data.get('banner', '')

    # tvshow poster
    season_thumb = extra_data.get('season_thumb', '')

    if season_thumb:
        poster = season_thumb
    else:
        poster = thumb

    if fanart:
        log_print.debug("Setting fan art as %s" % fanart)
        liz.setProperty('fanart_image', fanart)
    if banner:
        log_print.debug("Setting banner as %s" % banner)
        liz.setProperty('banner', '%s' % banner)
    if season_thumb:
        log_print.debug("Setting season Thumb as %s" % season_thumb)
        liz.setProperty('seasonThumb', '%s' % season_thumb)

    liz.setArt({"fanart": fanart, "poster": poster, "banner": banner, "thumb": thumb})

    if context is not None:
        if not folder and extra_data.get('type', 'video').lower() == "video":
            # Play Transcoded
            context.insert(0, (ADDON.getLocalizedString(32086), "PlayMedia(%s&transcode=1)" % link_url,))
            log_print.debug("Setting transcode options to [%s&transcode=1]" % link_url)
        log_print.debug("Building Context Menus")
        liz.addContextMenuItems(context, settings.get_setting('contextreplace'))

    return xbmcplugin.addDirectoryItem(handle=pluginhandle, url=link_url, listitem=liz, isFolder=folder)


def display_sections(cfilter=None, display_shared=False):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'files')

    server_list = plex_network.get_server_list()
    log_print.debug("Using list of %s servers: %s" % (len(server_list), server_list))

    for server in server_list:

        server.discover_sections()

        for section in server.get_sections():

            if display_shared and server.is_owned():
                continue

            details = {'title': section.get_title()}

            if len(server_list) > 1:
                details['title'] = "%s: %s" % (server.get_name(), details['title'])

            extra_data = {'fanart_image': server.get_fanart(section),
                          'type': "Video"}

            # Determine what we are going to do process after a link selected by the user, based on the content we find

            path = section.get_path()

            if section.is_show():
                mode = MODE_TVSHOWS
                if (cfilter is not None) and (cfilter != "tvshows"):
                    continue

            elif section.is_movie():
                mode = MODE_MOVIES
                if (cfilter is not None) and (cfilter != "movies"):
                    continue

            elif section.is_artist():
                mode = MODE_ARTISTS
                if (cfilter is not None) and (cfilter != "music"):
                    continue

            elif section.is_photo():
                mode = MODE_PHOTOS
                if (cfilter is not None) and (cfilter != "photos"):
                    continue
            else:
                log_print.debug("Ignoring section %s of type %s as unable to process"
                                % (details['title'], section.get_type()))
                continue

            if settings.get_setting('secondary'):
                mode = MODE_GETCONTENT
            else:
                path = path + '/all'

            extra_data['mode'] = mode
            section_url = '%s%s' % (server.get_url_location(), path)

            if not settings.get_setting('skipcontextmenus'):
                context = [('Refresh library section', 'RunScript(plugin.video.plexbmc, update, %s, %s)'
                            % (server.get_uuid(), section.get_key()))]
            else:
                context = None

            # Build that listing..
            add_item_to_gui(section_url, details, extra_data, context)

    if display_shared:
        xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))
        return

    # For each of the servers we have identified            
    if plex_network.is_myplex_signedin():
        add_item_to_gui('http://myplexqueue', {'title': ADDON.getLocalizedString(32080)}, {'type': 'Video', 'mode': MODE_MYPLEXQUEUE})

    for server in server_list:

        if server.is_offline() or server.is_secondary():
            continue

        # Plex plugin handling
        if (cfilter is not None) and (cfilter != "plugins"):
            continue

        if len(server_list) > 1:
            prefix = server.get_name() + ": "
        else:
            prefix = ""

        details = {'title': prefix + ADDON.getLocalizedString(32084)}
        extra_data = {'type': "Video", 'mode': MODE_CHANNELVIEW}

        u = "%s/channels/all" % server.get_url_location()
        add_item_to_gui(u, details, extra_data)

        # Create plexonline link
        details['title'] = prefix + "Plex Online"
        extra_data['type'] = "file"
        extra_data['mode'] = MODE_PLEXONLINE

        u = "%s/system/plexonline" % server.get_url_location()
        add_item_to_gui(u, details, extra_data)

        # create playlist link
        details['title'] = prefix + ADDON.getLocalizedString(32085)
        extra_data['type'] = "file"
        extra_data['mode'] = MODE_PLAYLISTS

        u = "%s/playlists" % server.get_url_location()
        add_item_to_gui(u, details, extra_data)

    if plex_network.is_myplex_signedin():

        if plex_network.is_plexhome_enabled():
            details = {'title': ADDON.getLocalizedString(32076)}
            extra_data = {'type': 'file'}

            u = "cmd:switchuser"
            add_item_to_gui(u, details, extra_data)

        details = {'title': ADDON.getLocalizedString(32006)}
        extra_data = {'type': 'file'}

        u = "cmd:signout"
        add_item_to_gui(u, details, extra_data)
    else:
        details = {'title': ADDON.getLocalizedString(32081)}
        extra_data = {'type': 'file'}

        u = "cmd:signintemp"
        add_item_to_gui(u, details, extra_data)

    details = {'title': ADDON.getLocalizedString(32082)}
    extra_data = {'type': 'file'}
    data_url = "cmd:displayservers"
    add_item_to_gui(data_url, details, extra_data)

    if settings.get_setting('cache'):
        details = {'title': ADDON.getLocalizedString(32083)}
        extra_data = {'type': "file",
                      'mode': MODE_DELETE_REFRESH}

        u = "http://nothing"
        add_item_to_gui(u, details, extra_data)

    # All XML entries have been parsed and we are ready to allow the user to browse around.  So end the screen listing.
    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def process_movies(url, tree=None):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'movies')

    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_DATEADDED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_MPAA_RATING)

    # get the server name from the URL, which was passed via the on screen listing..

    server = plex_network.get_server_from_url(url)

    tree = get_xml(url, tree)
    if tree is None:
        return

    set_window_heading(tree)
    random_number = str(random.randint(1000000000, 9999999999))

    # Find all the video tags, as they contain the data we need to link to a file.
    start_time = time.time()
    count = 0
    for movie in tree:

        if movie.tag == "Video":
            movie_tag(url, server, tree, movie, random_number)
            count += 1

    log_print.info("PROCESS: It took %s seconds to process %s items" % (time.time() - start_time, count))
    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def build_context_menu(url, item_data, server):
    context = []
    url_parts = urlparse(url)
    section = url_parts.path.split('/')[3]
    item_id = item_data.get('ratingKey', '0')

    # Mark media unwatched
    context.append((xbmc.getLocalizedString(117), "RunScript(plugin.video.plexbmc, delete, %s, %s)" % (server.get_uuid(), item_id)))
    context.append((xbmc.getLocalizedString(16104), 'RunScript(plugin.video.plexbmc, watch, %s, %s, %s)' % (server.get_uuid(), item_id, 'unwatch')))
    context.append((xbmc.getLocalizedString(16103), 'RunScript(plugin.video.plexbmc, watch, %s, %s, %s)' % (server.get_uuid(), item_id, 'watch')))
    context.append((xbmc.getLocalizedString(292), "RunScript(plugin.video.plexbmc, audio, %s, %s)" % (server.get_uuid(), item_id)))
    context.append((xbmc.getLocalizedString(287), "RunScript(plugin.video.plexbmc, subs, %s, %s)" % (server.get_uuid(), item_id)))
    context.append((xbmc.getLocalizedString(653), 'RunScript(plugin.video.plexbmc, update, %s, %s)' % (server.get_uuid(), section)))
    context.append((xbmc.getLocalizedString(184), 'RunScript(plugin.video.plexbmc, refresh)'))

    log_print.debug("Using context menus: %s" % context)

    return context


def process_tvshows(url, tree=None):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'tvshows')
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_MPAA_RATING)

    # Get the URL and server name.  Get the XML and parse
    tree = get_xml(url, tree)
    if tree is None:
        return

    server = plex_network.get_server_from_url(url)

    set_window_heading(tree)
    # For each directory tag we find
    ShowTags = tree.findall('Directory')
    for show in ShowTags:

        tempgenre = []

        for child in show:
            if child.tag == "Genre":
                tempgenre.append(child.get('tag', ''))

        _watched = int(show.get('viewedLeafCount', 0))

        # Create the basic data structures to pass up
        details = {'title': show.get('title', 'Unknown').encode('utf-8'),
                   'sorttitle': show.get('titleSort', show.get('title', 'Unknown')).encode('utf-8'),
                   'tvshowname': show.get('title', 'Unknown').encode('utf-8'),
                   'studio': show.get('studio', '').encode('utf-8'),
                   'plot': show.get('summary', '').encode('utf-8'),
                   'season': 0,
                   'episode': int(show.get('leafCount', 0)),
                   'mpaa': show.get('contentRating', ''),
                   'rating': float(show.get('rating', 0)),
                   'aired': show.get('originallyAvailableAt', ''),
                   'genre': " / ".join(tempgenre),
                   'mediatype': "tvshow"}

        extraData = {'type': 'video',
                     'source': 'tvshows',
                     'UnWatchedEpisodes': int(details['episode']) - _watched,
                     'WatchedEpisodes': _watched,
                     'TotalEpisodes': details['episode'],
                     'thumb': get_thumb_image(show, server),
                     'fanart_image': get_fanart_image(show, server),
                     'banner': get_banner_image(show, server),
                     'key': show.get('key', ''),
                     'ratingKey': str(show.get('ratingKey', 0))}

        # Set up overlays for watched and unwatched episodes
        if extraData['WatchedEpisodes'] == 0:
            details['playcount'] = 0
        elif extraData['UnWatchedEpisodes'] == 0:
            details['playcount'] = 1
        else:
            extraData['partialTV'] = 1

        # Create URL based on whether we are going to flatten the season view
        if settings.get_setting('flatten') == "2":
            log_print.debug("Flattening all shows")
            extraData['mode'] = MODE_TVEPISODES
            u = '%s%s' % (server.get_url_location(), extraData['key'].replace("children", "allLeaves"))
        else:
            extraData['mode'] = MODE_TVSEASONS
            u = '%s%s' % (server.get_url_location(), extraData['key'])

        if not settings.get_setting('skipcontextmenus'):
            context = build_context_menu(url, extraData, server)
        else:
            context = None

        add_item_to_gui(u, details, extraData, context)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def process_tvseasons(url):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'seasons')

    # Get URL, XML and parse
    server = plex_network.get_server_from_url(url)
    tree = get_xml(url)
    if tree is None:
        return

    willFlatten = False
    if settings.get_setting('flatten') == "1":
        # check for a single season
        if int(tree.get('size', 0)) == 1:
            log_print.debug("Flattening single season show")
            willFlatten = True

    sectionart = get_fanart_image(tree, server)
    banner = get_banner_image(tree, server)
    set_window_heading(tree)
    # For all the directory tags
    SeasonTags = tree.findall('Directory')
    plot = tree.get('summary', '').encode('utf-8')
    for season in SeasonTags:

        if willFlatten:
            url = server.get_url_location() + season.get('key')
            process_tvepisodes(url)
            return

        if settings.get_setting('disable_all_season') and season.get('index') is None:
            continue

        _watched = int(season.get('viewedLeafCount', 0))

        # Create the basic data structures to pass up
        details = {'title': season.get('title', 'Unknown').encode('utf-8'),
                   'tvshowname': season.get('parentTitle', 'Unknown').encode('utf-8'),
                   'TVShowTitle': season.get('parentTitle', 'Unknown').encode('utf-8'),
                   'sorttitle': season.get('titleSort', season.get('title', 'Unknown')).encode('utf-8'),
                   'studio': season.get('studio', '').encode('utf-8'),
                   'plot': plot,
                   'season': season.get('index', 0),
                   'episode': int(season.get('leafCount', 0)),
                   'mpaa': season.get('contentRating', ''),
                   'aired': season.get('originallyAvailableAt', ''),
                   'mediatype': "season"
                   }

        if season.get('sorttitle'):
            details['sorttitle'] = season.get('sorttitle')

        extraData = {'type': 'video',
                     'source': 'tvseasons',
                     'TotalEpisodes': details['episode'],
                     'WatchedEpisodes': _watched,
                     'UnWatchedEpisodes': details['episode'] - _watched,
                     'thumb': get_thumb_image(season, server),
                     'fanart_image': get_fanart_image(season, server),
                     'banner': banner,
                     'key': season.get('key', ''),
                     'ratingKey': str(season.get('ratingKey', 0)),
                     'mode': MODE_TVEPISODES}

        if extraData['fanart_image'] == "":
            extraData['fanart_image'] = sectionart

        # Set up overlays for watched and unwatched episodes
        if extraData['WatchedEpisodes'] == 0:
            details['playcount'] = 0
        elif extraData['UnWatchedEpisodes'] == 0:
            details['playcount'] = 1
        else:
            extraData['partialTV'] = 1

        url = '%s%s' % (server.get_url_location(), extraData['key'])

        if not settings.get_setting('skipcontextmenus'):
            context = build_context_menu(url, season, server)
        else:
            context = None

        # Build the screen directory listing
        add_item_to_gui(url, details, extraData, context)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def process_tvepisodes(url, tree=None):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'episodes')

    tree = get_xml(url, tree)
    if tree is None:
        return

    set_window_heading(tree)

    # get season thumb for SEASON NODE
    season_thumb = tree.get('thumb', '')
    if season_thumb == "/:/resources/show.png":
        season_thumb = ""

    ShowTags = tree.findall('Video')
    server = plex_network.get_server_from_url(url)

    if not settings.get_setting('skipimages'):
        sectionart = get_fanart_image(tree, server)

    banner = get_banner_image(tree, server)

    randomNumber = str(random.randint(1000000000, 9999999999))

    if tree.get('mixedParents') == '1':
        log_print.info('Setting plex sort')
        xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_UNSORTED)  # maintain original plex sorted
    else:
        log_print.info('Setting KODI sort')
        xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_EPISODE)  # episode

    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_DATEADDED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_MPAA_RATING)

    for episode in ShowTags:

        log_print.debug("---New Item---")
        tempgenre = []
        tempcast = []
        tempdir = []
        tempwriter = []

        for child in episode:
            if child.tag == "Media":
                mediaarguments = dict(child.items())
            elif child.tag == "Genre" and not settings.get_setting('skipmetadata'):
                tempgenre.append(child.get('tag'))
            elif child.tag == "Writer" and not settings.get_setting('skipmetadata'):
                tempwriter.append(child.get('tag'))
            elif child.tag == "Director" and not settings.get_setting('skipmetadata'):
                tempdir.append(child.get('tag'))
            elif child.tag == "Role" and not settings.get_setting('skipmetadata'):
                tempcast.append(child.get('tag'))

        log_print.debug("Media attributes are %s" % mediaarguments)

        # Gather some data
        view_offset = episode.get('viewOffset', 0)
        duration = int(mediaarguments.get('duration', episode.get('duration', 0))) / 1000

        # Required listItem entries for XBMC
        details = {'plot': episode.get('summary', '').encode('utf-8'),
                   'title': episode.get('title', 'Unknown').encode('utf-8'),
                   'sorttitle': episode.get('titleSort', episode.get('title', 'Unknown')).encode('utf-8'),
                   'rating': float(episode.get('rating', 0)),
                   'studio': episode.get('studio', tree.get('studio', '')).encode('utf-8'),
                   'mpaa': episode.get('contentRating', tree.get('grandparentContentRating', '')),
                   'year': int(episode.get('year', 0)),
                   'tagline': episode.get('tagline', '').encode('utf-8'),
                   'episode': int(episode.get('index', 0)),
                   'aired': episode.get('originallyAvailableAt', ''),
                   'tvshowtitle': episode.get('grandparentTitle', tree.get('grandparentTitle', '')).encode('utf-8'),
                   'season': int(episode.get('parentIndex', tree.get('parentIndex', 0))),
                   'mediatype': "episode"}

        if episode.get('sorttitle'):
            details['sorttitle'] = episode.get('sorttitle').encode('utf-8')

        if tree.get('mixedParents') == '1':
            if tree.get('parentIndex') == '1':
                details['title'] = "%sx%s %s" % (details['season'], str(details['episode']).zfill(2), details['title'])
            else:
                details['title'] = "%s - %sx%s %s" % (details['tvshowtitle'], details['season'], str(details['episode']).zfill(2), details['title'])

        # Extra data required to manage other properties
        extraData = {'type': "Video",
                     'source': 'tvepisodes',
                     'thumb': get_thumb_image(episode, server),
                     'fanart_image': get_fanart_image(episode, server),
                     'banner': banner,
                     'key': episode.get('key', ''),
                     'ratingKey': str(episode.get('ratingKey', 0)),
                     'duration': duration,
                     'resume': int(int(view_offset) / 1000)}

        if extraData['fanart_image'] == "" and not settings.get_setting('skipimages'):
            extraData['fanart_image'] = sectionart

        if "-1" in extraData['fanart_image'] and not settings.get_setting('skipimages'):
            extraData['fanart_image'] = sectionart

        if season_thumb:
            extraData['season_thumb'] = server.get_url_location() + season_thumb

        # get ALL SEASONS or TVSHOW thumb
        if not season_thumb and episode.get('parentThumb', ""):
            extraData['season_thumb'] = "%s%s" % (server.get_url_location(), episode.get('parentThumb', ""))
        elif not season_thumb and episode.get('grandparentThumb', ""):
            extraData['season_thumb'] = "%s%s" % (server.get_url_location(), episode.get('grandparentThumb', ""))

        # Determine what tupe of watched flag [overlay] to use
        if int(episode.get('viewCount', 0)) > 0:
            details['playcount'] = 1
        else:
            details['playcount'] = 0

        # Extended Metadata
        if not settings.get_setting('skipmetadata'):
            details['cast'] = tempcast
            details['director'] = " / ".join(tempdir)
            details['writer'] = " / ".join(tempwriter)
            details['genre'] = " / ".join(tempgenre)

        # Add extra media flag data
        if not settings.get_setting('skipflags'):
            extraData.update(get_media_data(mediaarguments))

        # Build any specific context menu entries
        if not settings.get_setting('skipcontextmenus'):
            context = build_context_menu(url, extraData, server)
        else:
            context = None

        extraData['mode'] = MODE_PLAYLIBRARY
        separator = "?"
        if "?" in extraData['key']:
            separator = "&"
        u = "%s%s%st=%s" % (server.get_url_location(), extraData['key'], separator, randomNumber)

        add_item_to_gui(u, details, extraData, context, folder=False)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def get_audio_subtitles_from_media(server, tree, full=False):
    '''
        Cycle through the Parts sections to find all "selected" audio and subtitle streams
        If a stream is marked as selected=1 then we will record it in the dict
        Any that are not, are ignored as we do not need to set them
        We also record the media locations for playback decision later on
    '''
    log_print.debug("== ENTER ==")
    log_print.debug("Gather media stream info")

    parts = []
    partsCount = 0
    subtitle = {}
    subCount = 0
    audio = {}
    audioCount = 0
    media = {}
    subOffset = -1
    audioOffset = -1
    selectedSubOffset = -1
    selectedAudioOffset = -1
    full_data = {}
    contents = "type"
    media_type = "unknown"
    extra = {}

    timings = tree.find('Video')
    if timings is not None:
        media_type = "video"
        extra['path'] = timings.get('key')
    else:
        timings = tree.find('Track')
        if timings:
            media_type = "music"
            extra['path'] = timings.get('key')
        else:
            timings = tree.find('Photo')
            if timings:
                media_type = "picture"
                extra['path'] = timings.get('key')
            else:
                log_print.debug("No Video data found")
                return {}

    media['viewOffset'] = timings.get('viewOffset', 0)
    media['duration'] = timings.get('duration', 12 * 60 * 60)

    if full:
        if media_type == "video":
            full_data = {'plot': timings.get('summary', '').encode('utf-8'),
                         'title': timings.get('title', 'Unknown').encode('utf-8'),
                         'sorttitle': timings.get('titleSort', timings.get('title', 'Unknown')).encode('utf-8'),
                         'rating': float(timings.get('rating', 0)),
                         'studio': timings.get('studio', '').encode('utf-8'),
                         'mpaa': timings.get('contentRating', '').encode('utf-8'),
                         'year': int(timings.get('year', 0)),
                         'tagline': timings.get('tagline', ''),
                         'thumbnailImage': get_thumb_image(timings, server),
                         'mediatype': "video"}

            if timings.get('type') == "episode":
                full_data['episode'] = int(timings.get('index', 0))
                full_data['aired'] = timings.get('originallyAvailableAt', '')
                full_data['tvshowtitle'] = timings.get('grandparentTitle', tree.get('grandparentTitle', '')).encode('utf-8')
                full_data['season'] = int(timings.get('parentIndex', tree.get('parentIndex', 0)))
                full_data['mediatype'] = "episode"

        elif media_type == "music":

            full_data = {'TrackNumber': int(timings.get('index', 0)),
                         'discnumber': int(timings.get('parentIndex', 0)),
                         'title': str(timings.get('index', 0)).zfill(2) + ". " + timings.get('title', 'Unknown').encode('utf-8'),
                         'rating': float(timings.get('rating', 0)),
                         'album': timings.get('parentTitle', tree.get('parentTitle', '')).encode('utf-8'),
                         'artist': timings.get('grandparentTitle', tree.get('grandparentTitle', '')).encode('utf-8'),
                         'duration': int(timings.get('duration', 0)) / 1000,
                         'thumbnailImage': get_thumb_image(timings, server)}

            extra['album'] = timings.get('parentKey')
            extra['index'] = timings.get('index')

    details = timings.findall('Media')

    media_details_list = []
    for media_details in details:

        resolution = ""
        try:
            if media_details.get('videoResolution') == "sd":
                resolution = "SD"
            elif int(media_details.get('videoResolution', 0)) > 1088:
                resolution = "4K"
            elif int(media_details.get('videoResolution', 0)) >= 1080:
                resolution = "HD 1080"
            elif int(media_details.get('videoResolution', 0)) >= 720:
                resolution = "HD 720"
            elif int(media_details.get('videoResolution', 0)) < 720:
                resolution = "SD"
        except:
            pass

        media_details_temp = {'bitrate': round(float(media_details.get('bitrate', 0)) / 1000, 1),
                              'videoResolution': resolution,
                              'container': media_details.get('container', 'unknown'),
                              'codec': media_details.get('videoCodec')
                              }

        options = media_details.findall('Part')

        # Get the media locations (file and web) for later on
        for stuff in options:

            try:
                bits = stuff.get('key'), stuff.get('file')
                parts.append(bits)
                media_details_list.append(media_details_temp)
                partsCount += 1
            except:
                pass

    # if we are deciding internally or forcing an external subs file, then collect the data
    if media_type == "video" and settings.get_setting('streamControl') == SUB_AUDIO_PLEX_CONTROL:

        contents = "all"
        tags = tree.getiterator('Stream')

        for bits in tags:
            stream = dict(bits.items())

            # Audio Streams
            if stream['streamType'] == '2':
                audioCount += 1
                audioOffset += 1
                if stream.get('selected') == "1":
                    log_print.debug("Found preferred audio id: %s " % stream['id'])
                    audio = stream
                    selectedAudioOffset = audioOffset

            # Subtitle Streams
            elif stream['streamType'] == '3':

                if subOffset == -1:
                    subOffset = int(stream.get('index', -1))
                elif 0 < stream.get('index', -1) < subOffset:
                    subOffset = int(stream.get('index', -1))

                if stream.get('selected') == "1":
                    log_print.debug("Found preferred subtitles id : %s " % stream['id'])
                    subCount += 1
                    subtitle = stream
                    if stream.get('key'):
                        subtitle['key'] = server.get_formatted_url(stream['key'])
                    else:
                        selectedSubOffset = int(stream.get('index')) - subOffset

    else:
        log_print.debug("Stream selection is set OFF")

    streamData = {'contents': contents,  # What type of data we are holding
                  'audio': audio,  # Audio data held in a dict
                  'audioCount': audioCount,  # Number of audio streams
                  'subtitle': subtitle,  # Subtitle data (embedded) held as a dict
                  'subCount': subCount,  # Number of subtitle streams
                  'parts': parts,  # The differet media locations
                  'partsCount': partsCount,  # Number of media locations
                  'media': media,  # Resume/duration data for media
                  'details': media_details_list,  # Bitrate, resolution and container for each part
                  'subOffset': selectedSubOffset,  # Stream index for selected subs
                  'audioOffset': selectedAudioOffset,  # STream index for select audio
                  'full_data': full_data,  # Full metadata extract if requested
                  'type': media_type,  # Type of metadata
                  'extra': extra}  # Extra data

    log_print.debug(streamData)
    return streamData


def play_playlist(server, data):
    log_print.debug("== ENTER ==")
    log_print.debug("Creating new playlist")
    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()

    tree = get_xml(server.get_url_location() + data['extra'].get('album') + "/children")

    if tree is None:
        return

    TrackTags = tree.findall('Track')
    for track in TrackTags:
        log_print.debug("Adding playlist item")

        url, item = track_tag(server, tree, track, listing=False)

        liz = xbmcgui.ListItem(item.get('title', 'Unknown'), iconImage=data['full_data'].get('thumbnailImage', ''), thumbnailImage=data['full_data'].get('thumbnailImage', ''))

        liz.setInfo(type='music', infoLabels=item)
        playlist.add(url, liz)

    index = int(data['extra'].get('index', 0)) - 1
    log_print.debug("Playlist complete.  Starting playback from track %s [playlist index %s] " % (data['extra'].get('index', 0), index))
    xbmc.Player().playselected(index)

    return


def play_library_media(vids, override=False, force=None, full_data=False, helper=False):
    session = None
    if settings.get_setting('transcode'):
        override = True

    if override:
        full_data = True

    server = plex_network.get_server_from_url(vids)

    _id = vids.split('?')[0].split('&')[0].split('/')[-1]

    tree = get_xml(vids)
    if tree is None:
        return

    if force:
        full_data = True

    streams = get_audio_subtitles_from_media(server, tree, full_data)

    if force and streams['type'] == "music":
        play_playlist(server, streams)
        return

    url = select_media_to_play(streams, server)

    codec = streams.get('details', [{}])[0].get('codec')
    resolution = streams.get('details', [{}])[0].get('videoResolution')

    if codec and (settings.get_setting('transcode_hevc') and codec.lower() == 'hevc'):
        override = True
    if resolution and (settings.get_setting('transcode_g1080') and resolution.lower() == '4k'):
        override = True

    if url is None:
        return

    protocol = url.split(':', 1)[0]

    if protocol == "file":
        log_print.debug("We are playing a local file")
        playurl = url.split(':', 1)[1]
    elif protocol.startswith("http"):
        log_print.debug("We are playing a stream")
        if override:
            log_print.debug("We will be transcoding the stream")
            if settings.get_setting('transcode_type') == "universal":
                session, playurl = server.get_universal_transcode(streams['extra']['path'])
            elif settings.get_setting('transcode_type') == "legacy":
                session, playurl = server.get_legacy_transcode(_id, url)

        else:
            playurl = server.get_formatted_url(url)
    else:
        playurl = url

    resume = int(int(streams['media']['viewOffset']) / 1000)
    duration = int(int(streams['media']['duration']) / 1000)

    log_print.debug("Resume has been set to %s " % resume)

    item = xbmcgui.ListItem(path=playurl)

    if streams['full_data']:
        item.setInfo(type=streams['type'], infoLabels=streams['full_data'])
        item.setThumbnailImage(streams['full_data'].get('thumbnailImage', ''))
        item.setIconImage(streams['full_data'].get('thumbnailImage', ''))

    if force:

        if int(force) > 0:
            resume = int(int(force) / 1000)
        else:
            resume = force

    if force or session is not None:
        if resume:
            item.setProperty('ResumeTime', str(resume))
            item.setProperty('TotalTime', str(duration))
            item.setProperty('StartOffset', str(resume))
            log_print.info("Playback from resume point: %s" % resume)

    if streams['type'] == "picture":
        import json
        request = json.dumps({"id": 1,
                              "jsonrpc": "2.0",
                              "method": "Player.Open",
                              "params": {"item": {"file": playurl}}})
        html = xbmc.executeJSONRPC(request)
        return
    else:
        xbmcplugin.setResolvedUrl(pluginhandle, True, item)

    # record the playing file and server in the home window
    # so that plexbmc helper can find out what is playing
    WINDOW.setProperty('plexbmc.nowplaying.server', server.get_location())
    WINDOW.setProperty('plexbmc.nowplaying.id', _id)

    # Set a loop to wait for positive confirmation of playback
    count = 0
    while not xbmc.Player().isPlaying():
        log_print.debug("Not playing yet...sleep for 2")
        count = count + 2
        if count >= 20:
            return
        else:
            time.sleep(2)

    if not override:
        set_audio_subtitles(streams)

    if streams['type'] == "video" or streams['type'] == "music":
        monitor_playback(_id, server, playurl, session)

    return


def set_audio_subtitles(stream):
    '''
        Take the collected audio/sub stream data and apply to the media
        If we do not have any subs then we switch them off
    '''

    log_print.debug("== ENTER ==")

    # If we have decided not to collect any sub data then do not set subs
    if stream['contents'] == "type":
        log_print.info("No audio or subtitle streams to process.")

        # If we have decided to force off all subs, then turn them off now and return
        if settings.get_setting('streamControl') == SUB_AUDIO_NEVER_SHOW:
            xbmc.Player().showSubtitles(False)
            log_print.debug("All subs disabled")

        return True

    # Set the AUDIO component
    if settings.get_setting('streamControl') == SUB_AUDIO_PLEX_CONTROL:
        log_print.debug("Attempting to set Audio Stream")

        audio = stream['audio']

        if stream['audioCount'] == 1:
            log_print.info("Only one audio stream present - will leave as default")

        elif audio:
            log_print.debug("Attempting to use selected language setting: %s" % audio.get('language', audio.get('languageCode', 'Unknown')).encode('utf8'))
            log_print.info("Found preferred language at index %s" % stream['audioOffset'])
            try:
                xbmc.Player().setAudioStream(stream['audioOffset'])
                log_print.debug("Audio set")
            except:
                log_print.info("Error setting audio, will use embedded default stream")

    # Set the SUBTITLE component
    if settings.get_setting('streamControl') == SUB_AUDIO_PLEX_CONTROL:
        log_print.debug("Attempting to set preferred subtitle Stream")
        subtitle = stream['subtitle']
        if subtitle:
            log_print.debug("Found preferred subtitle stream")
            try:
                xbmc.Player().showSubtitles(False)
                if subtitle.get('key'):
                    xbmc.Player().setSubtitles(subtitle['key'])
                else:
                    log_print.info("Enabling embedded subtitles at index %s" % stream['subOffset'])
                    xbmc.Player().setSubtitleStream(int(stream['subOffset']))

                xbmc.Player().showSubtitles(True)
                return True
            except:
                log_print.info("Error setting subtitle")

        else:
            log_print.info("No preferred subtitles to set")
            xbmc.Player().showSubtitles(False)

    return False


def select_media_to_play(data, server):
    log_print.debug("== ENTER ==")
    # if we have two or more files for the same movie, then present a screen
    result = 0
    dvdplayback = False

    count = data['partsCount']
    options = data['parts']
    details = data['details']

    if count > 1:

        dialogOptions = []
        dvdIndex = []
        indexCount = 0
        for items in options:

            if items[1]:
                name = items[1].split('/')[-1]
                # name="%s %s %sMbps" % (items[1].split('/')[-1], details[indexCount]['videoResolution'], details[indexCount]['bitrate'])
            else:
                name = "%s %s %sMbps" % (items[0].split('.')[-1], details[indexCount]['videoResolution'], details[indexCount]['bitrate'])

            if settings.get_setting('forcedvd'):
                if '.ifo' in name.lower():
                    log_print.debug("Found IFO DVD file in " + name)
                    name = "DVD Image"
                    dvdIndex.append(indexCount)

            dialogOptions.append(name)
            indexCount += 1

        log_print.debug("Create selection dialog box - we have a decision to make!")
        startTime = xbmcgui.Dialog()
        result = startTime.select(ADDON.getLocalizedString(32071), dialogOptions)
        if result == -1:
            return None

        if result in dvdIndex:
            log_print.debug("DVD Media selected")
            dvdplayback = True

    else:
        if settings.get_setting('forcedvd'):
            if '.ifo' in options[result]:
                dvdplayback = True

    newurl = select_media_type({'key': options[result][0], 'file': options[result][1]}, server, dvdplayback)

    log_print.debug("We have selected media at %s" % newurl)
    return newurl


def monitor_playback(_id, server, playurl, session=None):
    log_print.debug("== ENTER ==")

    if session:
        log_print.debug("We are monitoring a transcode session")

    if settings.get_setting('monitoroff'):
        return

    playedTime = 0
    totalTime = 0
    currentTime = 0
    # Whilst the file is playing back
    while xbmc.Player().isPlaying():

        try:
            if not (playurl == xbmc.Player().getPlayingFile()):
                log_print.info("File stopped being played")
                break
        except:
            pass

        currentTime = int(xbmc.Player().getTime())
        totalTime = int(xbmc.Player().getTotalTime())

        try:
            progress = int((float(currentTime) / float(totalTime)) * 100)
        except:
            progress = 0

        if playedTime == currentTime:
            log_print.debug("Movies paused at: %s secs of %s @ %s%%" % (currentTime, totalTime, progress))
            server.report_playback_progress(_id, currentTime * 1000, state="paused", duration=totalTime * 1000)
        else:

            log_print.debug("Movies played time: %s secs of %s @ %s%%" % (currentTime, totalTime, progress))
            server.report_playback_progress(_id, currentTime * 1000, state="playing", duration=totalTime * 1000)
            playedTime = currentTime

        xbmc.sleep(2000)

    # If we get this far, playback has stopped
    log_print.debug("Playback Stopped")
    server.report_playback_progress(_id, playedTime * 1000, state='stopped', duration=totalTime * 1000)

    if session is not None:
        log_print.debug("Stopping PMS transcode job with session %s" % session)
        server.stop_transcode_session(session)

    return


def play_media_stream(url):
    log_print.debug("== ENTER ==")

    if url.startswith('file'):
        log_print.debug("We are playing a local file")
        # Split out the path from the URL
        playurl = url.split(':', 1)[1]
    elif url.startswith('http'):
        log_print.debug("We are playing a stream")
        if '?' in url:
            server = plex_network.get_server_from_url(url)
            playurl = server.get_formatted_url(url)
    else:
        playurl = url

    item = xbmcgui.ListItem(path=playurl)
    return xbmcplugin.setResolvedUrl(pluginhandle, True, item)


def play_video_channel(vids, prefix=None, indirect=None, transcode=False):
    server = plex_network.get_server_from_url(vids)
    if "node.plexapp.com" in vids:
        server = get_master_server()

    if indirect:
        # Probably should transcode this
        if vids.startswith('http'):
            vids = '/' + vids.split('/', 3)[3]
            transcode = True

        session, vids = server.get_universal_transcode(vids)

    '''# If we find the url lookup service, then we probably have a standard plugin, but possibly with resolution choices
    if '/services/url/lookup' in vids:
        printDebug.debug("URL Lookup service")
        tree=getXML(vids)
        if not tree:
            return

        mediaCount=0
        mediaDetails=[]
        for media in tree.getiterator('Media'):
            mediaCount+=1
            tempDict={'videoResolution' : media.get('videoResolution',"Unknown")}

            for child in media:
                tempDict['key']=child.get('key','')

            tempDict['identifier']=tree.get('identifier','')
            mediaDetails.append(tempDict)

        printDebug.debug( str(mediaDetails) )

        # If we have options, create a dialog menu
        result=0
        if mediaCount > 1:
            printDebug ("Select from plugin video sources")
            dialogOptions=[x['videoResolution'] for x in mediaDetails ]
            videoResolution = xbmcgui.Dialog()

            result = videoResolution.select('Select resolution..',dialogOptions)

            if result == -1:
                return

        videoPluginPlay(getLinkURL('',mediaDetails[result],server))
        return

    # Check if there is a further level of XML required
    if indirect or '&indirect=1' in vids:
        printDebug.debug("Indirect link")
        tree=getXML(vids)
        if not tree:
            return

        for bits in tree.getiterator('Part'):
            videoPluginPlay(getLinkURL(vids,bits,server))
            break

        return
    '''
    # if we have a plex URL, then this is a transcoding URL
    if 'plex://' in vids:
        log_print.debug("found webkit video, pass to transcoder")
        if not prefix:
            prefix = "system"
            if settings.get_setting('transcode_type') == "universal":
                session, vids = server.get_universal_transcode(vids)
            elif settings.get_setting('transcode_type') == "legacy":
                session, vids = server.get_legacy_transcode(0, vids, prefix)

        # Workaround for XBMC HLS request limit of 1024 byts
        if len(vids) > 1000:
            log_print.debug("XBMC HSL limit detected, will pre-fetch m3u8 playlist")

            playlist = get_xml(vids)

            if not playlist or "# EXTM3U" not in playlist:
                log_print.debug("Unable to get valid m3u8 playlist from transcoder")
                return

            server = plex_network.get_server_from_url(vids)
            session = playlist.split()[-1]
            vids = "%s/video/:/transcode/segmented/%s?t=1" % (server.get_url_location(), session)

    log_print.debug("URL to Play: %s " % vids)
    log_print.debug("Prefix is: %s" % prefix)

    # If this is an Apple movie trailer, add User Agent to allow access
    if 'trailers.apple.com' in vids:
        url = vids + "|User-Agent=QuickTime/7.6.9 (qtver=7.6.9;os=Windows NT 6.1Service Pack 1)"
    else:
        url = vids

    log_print.debug("Final URL is: %s" % url)

    item = xbmcgui.ListItem(path=url)
    xbmcplugin.setResolvedUrl(pluginhandle, True, item)

    if transcode:
        try:
            monitor_channel_transcode_playback(session, server)
        except:
            log_print.debug("Unable to start transcode monitor")
    else:
        log_print.debug("Not starting monitor")

    return


def monitor_channel_transcode_playback(sessionID, server):
    log_print.debug("== ENTER ==")

    # Logic may appear backward, but this does allow for a failed start to be detected
    # First while loop waiting for start

    if settings.get_setting('monitoroff'):
        return

    count = 0
    while not xbmc.Player().isPlaying():
        log_print.debug("Not playing yet...sleep for 2")
        count = count + 2
        if count >= 40:
            # Waited 20 seconds and still no movie playing - assume it isn't going to..
            return
        else:
            xbmc.sleep(2000)

    while xbmc.Player().isPlaying():
        log_print.debug("Waiting for playback to finish")
        xbmc.sleep(4000)

    log_print.debug("Playback Stopped")
    log_print.debug("Stopping PMS transcode job with session: %s" % sessionID)
    server.stop_transcode_session(sessionID)

    return


def get_params(paramstring):
    log_print.debug("== ENTER ==")
    log_print.debug("Parameter string: %s" % paramstring)
    param = {}
    if len(paramstring) >= 2:
        params = paramstring

        if params[0] == "?":
            cleanedparams = params[1:]
        else:
            cleanedparams = params

        if params[len(params) - 1] == '/':
            params = params[0:len(params) - 2]

        pairsofparams = cleanedparams.split('&')
        for i in range(len(pairsofparams)):
            splitparams = {}
            splitparams = pairsofparams[i].split('=')
            if (len(splitparams)) == 2:
                param[splitparams[0]] = splitparams[1]
            elif (len(splitparams)) == 3:
                param[splitparams[0]] = splitparams[1] + "=" + splitparams[2]
    log_print.debug("PleXBMC -> Detected parameters: " + str(param))
    return param


def channel_search(url, prompt):
    '''
        When we encounter a search request, branch off to this function to generate the keyboard
        and accept the terms.  This URL is then fed back into the correct function for
        onward processing.
    '''
    log_print.debug("== ENTER ==")

    if prompt:
        prompt = urllib.unquote(prompt)
    else:
        prompt = "Enter Search Term..."

    kb = xbmc.Keyboard('', 'heading')
    kb.setHeading(prompt)
    kb.doModal()
    if kb.isConfirmed():
        text = kb.getText()
        log_print.debug("Search term input: %s" % text)
        url = url + '&query=' + urllib.quote(text)
        plex_plugins(url)
    return


def get_content(url):
    '''
        This function takes teh URL, gets the XML and determines what the content is
        This XML is then redirected to the best processing function.
        If a search term is detected, then show keyboard and run search query
        @input: URL of XML page
        @return: nothing, redirects to another function
    '''
    log_print.debug("== ENTER ==")

    server = plex_network.get_server_from_url(url)
    lastbit = url.split('/')[-1]
    log_print.debug("URL suffix: %s" % lastbit)

    # Catch search requests, as we need to process input before getting results.
    if lastbit.startswith('search'):
        log_print.debug("This is a search URL.  Bringing up keyboard")
        kb = xbmc.Keyboard('', 'heading')
        kb.setHeading('Enter search term')
        kb.doModal()
        if kb.isConfirmed():
            text = kb.getText()
            log_print.debug("Search term input: %s" % text)
            url = url + '&query=' + urllib.quote(text)
        else:
            return

    tree = server.processed_xml(url)

    set_window_heading(tree)

    if lastbit == "folder" or lastbit == "playlists":
        process_xml(url, tree)
        return

    view_group = tree.get('viewGroup')

    if view_group == "movie":
        log_print.debug("This is movie XML, passing to Movies")
        process_movies(url, tree)
    elif view_group == "show":
        log_print.debug("This is tv show XML")
        process_tvshows(url, tree)
    elif view_group == "episode":
        log_print.debug("This is TV episode XML")
        process_tvepisodes(url, tree)
    elif view_group == 'artist':
        log_print.debug("This is music XML")
        artist(url, tree)
    elif view_group == 'album' or view_group == 'albums':
        albums(url, tree)
    elif view_group == 'track':
        log_print.debug("This is track XML")
        tracks(url, tree)  # sorthing is handled here
    elif view_group == "photo":
        log_print.debug("This is a photo XML")
        photo(url, tree)
    else:
        process_directory(url, tree)

    return


def process_directory(url, tree=None):
    log_print.debug("== ENTER ==")
    log_print.debug("Processing secondary menus")
    xbmcplugin.setContent(pluginhandle, "")
    server = plex_network.get_server_from_url(url)
    set_window_heading(tree)
    thumb = tree.get('thumb')
    for directory in tree:
        # log_print.info("TITLE: %s" % directory.get('title','Unknown').encode('utf-8'))
        details = {'title': directory_item_translate(directory.get('title', 'Unknown').encode('utf-8'), thumb)}
        extraData = {'thumb': get_thumb_image(tree, server), 'fanart_image': get_fanart_image(tree, server), 'mode': MODE_GETCONTENT}

        u = '%s' % (get_link_url(url, directory, server))

        add_item_to_gui(u, details, extraData)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def directory_item_translate(title, thumb):
    translated_title = title

    if thumb.endswith("show.png"):
        if title == "All Shows":
            translated_title = ADDON.getLocalizedString(32013)
        elif title == "Unwatched":
            translated_title = ADDON.getLocalizedString(32014)
        elif title == "Recently Aired":
            translated_title = ADDON.getLocalizedString(32015)
        elif title == 'Recently Added':
            translated_title = ADDON.getLocalizedString(32016)
        elif title == 'Recently Viewed Episodes':
            translated_title = ADDON.getLocalizedString(32017)
        elif title == 'Recently Viewed Shows':
            translated_title = ADDON.getLocalizedString(32018)
        elif title == "On Deck":
            translated_title = ADDON.getLocalizedString(32019)
        elif title == "By Collection":
            translated_title = ADDON.getLocalizedString(32020)
        elif title == "By First Letter":
            translated_title = ADDON.getLocalizedString(32021)
        elif title == "By Genre":
            translated_title = ADDON.getLocalizedString(32022)
        elif title == "By Year":
            translated_title = ADDON.getLocalizedString(32023)
        elif title == "By Content Rating":
            translated_title = ADDON.getLocalizedString(32024)
        elif title == "By Folder":
            translated_title = ADDON.getLocalizedString(32025)
        elif title == "Search Shows...":
            translated_title = ADDON.getLocalizedString(32026)
        elif title == "Search Episodes...":
            translated_title = ADDON.getLocalizedString(32027)

    if thumb.endswith("artist.png"):
        if title == "All Artists":
            translated_title = ADDON.getLocalizedString(32028)
        elif title == "By Album":
            translated_title = ADDON.getLocalizedString(32029)
        elif title == "By Genre":
            translated_title = ADDON.getLocalizedString(32030)
        elif title == "By Year":
            translated_title = ADDON.getLocalizedString(32031)
        elif title == "By Collection":
            translated_title = ADDON.getLocalizedString(32032)
        elif title == 'Recently Added':
            translated_title = ADDON.getLocalizedString(32033)
        elif title == "By Folder":
            translated_title = ADDON.getLocalizedString(32034)
        elif title == "Search Artists...":
            translated_title = ADDON.getLocalizedString(32035)
        elif title == "Search Albums...":
            translated_title = ADDON.getLocalizedString(32036)
        elif title == "Search Tracks...":
            translated_title = ADDON.getLocalizedString(32037)

    if thumb.endswith("movie.png") or thumb.endswith("video.png"):
        if title.startswith("All "):
            translated_title = ADDON.getLocalizedString(32038)
        elif title == "Unwatched":
            translated_title = ADDON.getLocalizedString(32039)
        elif title == "Recently Released":
            translated_title = ADDON.getLocalizedString(32040)
        elif title == 'Recently Added':
            translated_title = ADDON.getLocalizedString(32041)
        elif title == 'Recently Viewed':
            translated_title = ADDON.getLocalizedString(32042)
        elif title == "On Deck":
            translated_title = ADDON.getLocalizedString(32043)
        elif title == "By Collection":
            translated_title = ADDON.getLocalizedString(32044)
        elif title == "By Genre":
            translated_title = ADDON.getLocalizedString(32045)
        elif title == "By Year":
            translated_title = ADDON.getLocalizedString(32046)
        elif title == "By Decade":
            translated_title = ADDON.getLocalizedString(32047)
        elif title == "By Director":
            translated_title = ADDON.getLocalizedString(32048)
        elif title == "By Starring Actor":
            translated_title = ADDON.getLocalizedString(32049)
        elif title == "By Country":
            translated_title = ADDON.getLocalizedString(32050)
        elif title == "By Content Rating":
            translated_title = ADDON.getLocalizedString(32051)
        elif title == "By Rating":
            translated_title = ADDON.getLocalizedString(32052)
        elif title == "By Resolution":
            translated_title = ADDON.getLocalizedString(32053)
        elif title == "By First Letter":
            translated_title = ADDON.getLocalizedString(32054)
        elif title == "By Folder":
            translated_title = ADDON.getLocalizedString(32055)
        elif title == "Search...":
            translated_title = ADDON.getLocalizedString(32056)

    if thumb.endswith("photo.png"):
        if title == "All Photos":
            translated_title = ADDON.getLocalizedString(32057)
        elif title == "By Year":
            translated_title = ADDON.getLocalizedString(32058)
        elif title == "Recently Added":
            translated_title = ADDON.getLocalizedString(32059)
        elif title == "Camera Make":
            translated_title = ADDON.getLocalizedString(32060)
        elif title == "Camera Model":
            translated_title = ADDON.getLocalizedString(32061)
        elif title == 'Aperture':
            translated_title = ADDON.getLocalizedString(32062)
        elif title == "Shutter Speed":
            translated_title = ADDON.getLocalizedString(32063)
        elif title == "ISO":
            translated_title = ADDON.getLocalizedString(32064)
        elif title == "Lens":
            translated_title = ADDON.getLocalizedString(32065)

    return translated_title


def item_translate(title, source, folder):
    translated_title = title

    if folder and (source == 'tvshows' or source == 'tvseasons'):
        if title == "All episodes":
            translated_title = ADDON.getLocalizedString(32087)
        elif title.startswith("Season "):
            translated_title = ADDON.getLocalizedString(32088) + title[6:]

    return translated_title


def heading2_translate(tree):
    title = tree.get('title2')
    translated_title = directory_item_translate(title, tree.get('thumb'))

    if title.startswith("Season "):
        translated_title = ADDON.getLocalizedString(32088) + title[6:]
    elif title.startswith("Search for '"):
        translated_title = ADDON.getLocalizedString(32089) + title[10:]

    return translated_title


def artist(url, tree=None):
    '''
        Process artist XML and display data
        @input: url of XML page, or existing tree of XML page
        @return: nothing
    '''
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'artists')
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_ARTIST_IGNORE_THE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_LASTPLAYED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)

    # Get the URL and server name.  Get the XML and parse
    tree = get_xml(url, tree)
    if tree is None:
        return

    server = plex_network.get_server_from_url(url)
    set_window_heading(tree)
    ArtistTag = tree.findall('Directory')
    for _artist in ArtistTag:
        details = {'artist': _artist.get('title', '').encode('utf-8')}

        details['title'] = details['artist']

        extraData = {'type': "Music",
                     'thumb': get_thumb_image(_artist, server),
                     'fanart_image': get_fanart_image(_artist, server),
                     'ratingKey': _artist.get('title', ''),
                     'key': _artist.get('key', ''),
                     'mode': MODE_ALBUMS,
                     'plot': _artist.get('summary', '')}

        url = '%s%s' % (server.get_url_location(), extraData['key'])

        add_item_to_gui(url, details, extraData)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def albums(url, tree=None):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'albums')
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_ALBUM_IGNORE_THE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_ARTIST_IGNORE_THE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_LASTPLAYED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)

    # Get the URL and server name.  Get the XML and parse
    tree = get_xml(url, tree)
    if tree is None:
        return

    server = plex_network.get_server_from_url(url)
    sectionart = get_fanart_image(tree, server)
    set_window_heading(tree)
    AlbumTags = tree.findall('Directory')
    recent = True if 'recentlyAdded' in url else False
    for album in AlbumTags:

        details = {'album': album.get('title', '').encode('utf-8'),
                   'year': int(album.get('year', 0)),
                   'artist': tree.get('parentTitle', album.get('parentTitle', '')).encode('utf-8')}

        if recent:
            details['title'] = "%s - %s" % (details['artist'], details['album'])
        else:
            details['title'] = details['album']

        extraData = {'type': "Music",
                     'thumb': get_thumb_image(album, server),
                     'fanart_image': get_fanart_image(album, server),
                     'key': album.get('key', ''),
                     'mode': MODE_TRACKS,
                     'plot': album.get('summary', '')}

        if extraData['fanart_image'] == "":
            extraData['fanart_image'] = sectionart

        url = '%s%s' % (server.get_url_location(), extraData['key'])

        add_item_to_gui(url, details, extraData)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def tracks(url, tree=None):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'songs')
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_DURATION)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_SONG_RATING)
    xbmcplugin.addSortMethod(pluginhandle, xbmcplugin.SORT_METHOD_TRACKNUM)

    tree = get_xml(url, tree)
    if tree is None:
        return

    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()

    server = plex_network.get_server_from_url(url)
    sectionart = get_fanart_image(tree, server)
    sectionthumb = get_thumb_image(tree, server)
    set_window_heading(tree)
    TrackTags = tree.findall('Track')
    for track in TrackTags:
        if track.get('thumb'):
            sectionthumb = get_thumb_image(track, server)

        track_tag(server, tree, track, sectionart, sectionthumb)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def get_xml(url, tree=None):
    log_print.debug("== ENTER ==")

    if tree is None:
        tree = plex_network.get_processed_xml(url)

    if tree.get('message'):
        xbmcgui.Dialog().ok(tree.get('header', 'Message'), tree.get('message', ''))
        return None

    return tree


def plex_plugins(url, tree=None):
    '''
        Main function to parse plugin XML from PMS
        Will create dir or item links depending on what the
        main tag is.
        @input: plugin page URL
        @return: nothing, creates XBMC GUI listing
    '''
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'addons')
    server = plex_network.get_server_from_url(url)
    tree = get_xml(url, tree)
    if tree is None:
        return

    myplex_url = False
    if (tree.get('identifier') != "com.plexapp.plugins.myplex") and ("node.plexapp.com" in url):
        myplex_url = True
        log_print.debug("This is a myplex URL, attempting to locate master server")
        server = get_master_server()

    for plugin in tree:

        details = {'title': plugin.get('title', 'Unknown').encode('utf-8')}

        if details['title'] == "Unknown":
            details['title'] = plugin.get('name', "Unknown").encode('utf-8')

        if plugin.get('summary'):
            details['plot'] = plugin.get('summary')

        extraData = {'thumb': get_thumb_image(plugin, server),
                     'fanart_image': get_fanart_image(plugin, server),
                     'identifier': tree.get('identifier', ''),
                     'type': "Video",
                     'key': plugin.get('key', '')}

        if myplex_url:
            extraData['key'] = extraData['key'].replace('node.plexapp.com:32400', server.get_location())

        if extraData['fanart_image'] == "":
            extraData['fanart_image'] = get_fanart_image(tree, server)

        p_url = get_link_url(url, extraData, server)

        if plugin.tag == "Directory" or plugin.tag == "Podcast":

            if plugin.get('search') == '1':
                extraData['mode'] = MODE_CHANNELSEARCH
                extraData['parameters'] = {'prompt': plugin.get('prompt', "Enter Search Term").encode('utf-8')}
            else:
                extraData['mode'] = MODE_PLEXPLUGINS

            add_item_to_gui(p_url, details, extraData)

        elif plugin.tag == "Video":
            extraData['mode'] = MODE_VIDEOPLUGINPLAY

            for child in plugin:
                if child.tag == "Media":
                    extraData['parameters'] = {'indirect': child.get('indirect', '0')}

            add_item_to_gui(p_url, details, extraData, folder=False)

        elif plugin.tag == "Setting":

            if plugin.get('option') == 'hidden':
                value = "********"
            elif plugin.get('type') == "text":
                value = plugin.get('value')
            elif plugin.get('type') == "enum":
                value = plugin.get('values').split('|')[int(plugin.get('value', 0))]
            else:
                value = plugin.get('value')

            details['title'] = "%s - [%s]" % (plugin.get('label', 'Unknown').encode('utf-8'), value)
            extraData['mode'] = MODE_CHANNELPREFS
            extraData['parameters'] = {'id': plugin.get('id')}
            add_item_to_gui(url, details, extraData)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def channel_settings(url, settingID):
    '''
        Take the setting XML and parse it to create an updated
        string with the new settings.  For the selected value, create
        a user input screen (text or list) to update the setting.
        @ input: url
        @ return: nothing
    '''
    log_print.debug("== ENTER ==")
    log_print.debug("Setting preference for ID: %s" % settingID)

    if not settingID:
        log_print.debug("ID not set")
        return

    tree = get_xml(url)
    if tree is None:
        return

    set_window_heading(tree)
    setString = None
    for plugin in tree:

        if plugin.get('id') == settingID:
            log_print.debug("Found correct id entry for: %s" % settingID)
            sid = settingID

            label = plugin.get('label', "Enter value")
            option = plugin.get('option')
            value = plugin.get('value')

            if plugin.get('type') == "text":
                log_print.debug("Setting up a text entry screen")
                kb = xbmc.Keyboard(value, 'heading')
                kb.setHeading(label)

                if option == "hidden":
                    kb.setHiddenInput(True)
                else:
                    kb.setHiddenInput(False)

                kb.doModal()
                if kb.isConfirmed():
                    value = kb.getText()
                    log_print.debug("Value input: %s " % value)
                else:
                    log_print.debug("User cancelled dialog")
                    return False

            elif plugin.get('type') == "enum":
                log_print.debug("Setting up an enum entry screen")

                values = plugin.get('values').split('|')

                settingScreen = xbmcgui.Dialog()
                value = settingScreen.select(label, values)
                if value == -1:
                    log_print.debug("User cancelled dialog")
                    return False
            else:
                log_print.debug('Unknown option type: %s' % plugin.get('id'))

        else:
            value = plugin.get('value')
            sid = plugin.get('id')

        if setString is None:
            setString = '%s/set?%s=%s' % (url, sid, value)
        else:
            setString = '%s&%s=%s' % (setString, sid, value)

    log_print.debug("Settings URL: %s" % setString)
    plex_network.talk_to_server(setString)
    xbmc.executebuiltin("Container.Refresh")

    return False


def process_xml(url, tree=None):
    '''
        Main function to parse plugin XML from PMS
        Will create dir or item links depending on what the
        main tag is.
        @input: plugin page URL
        @return: nothing, creates XBMC GUI listing
    '''
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'movies')
    server = plex_network.get_server_from_url(url)
    tree = get_xml(url, tree)
    if tree is None:
        return
    set_window_heading(tree)
    for plugin in tree:

        details = {'title': plugin.get('title', 'Unknown').encode('utf-8')}

        if details['title'] == "Unknown":
            details['title'] = plugin.get('name', "Unknown").encode('utf-8')

        extraData = {'thumb': get_thumb_image(plugin, server),
                     'fanart_image': get_fanart_image(plugin, server),
                     'identifier': tree.get('identifier', ''),
                     'type': "Video"}

        if extraData['fanart_image'] == "":
            extraData['fanart_image'] = get_fanart_image(tree, server)

        p_url = get_link_url(url, plugin, server)

        if plugin.tag == "Directory" or plugin.tag == "Podcast":
            extraData['mode'] = MODE_PROCESSXML
            add_item_to_gui(p_url, details, extraData)

        elif plugin.tag == "Track":
            track_tag(server, tree, plugin)

        elif plugin.tag == "Playlist":
            playlist_tag(url, server, tree, plugin)

        elif tree.get('viewGroup') == "movie":
            process_movies(url, tree)
            return

        elif tree.get('viewGroup') == "episode":
            process_tvepisodes(url, tree)
            return

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def movie_tag(url, server, tree, movie, random_number):
    log_print.debug("---New Item---")
    tempgenre = []
    tempcast = []
    tempdir = []
    tempwriter = []

    # Lets grab all the info we can quickly through either a dictionary, or assignment to a list
    # We'll process it later
    for child in movie:
        if child.tag == "Media":
            mediaarguments = dict(child.items())
        elif child.tag == "Genre" and not settings.get_setting('skipmetadata'):
            tempgenre.append(child.get('tag'))
        elif child.tag == "Writer" and not settings.get_setting('skipmetadata'):
            tempwriter.append(child.get('tag'))
        elif child.tag == "Director" and not settings.get_setting('skipmetadata'):
            tempdir.append(child.get('tag'))
        elif child.tag == "Role" and not settings.get_setting('skipmetadata'):
            tempcast.append(child.get('tag'))

    log_print.debug("Media attributes are %s" % mediaarguments)

    # Gather some data
    view_offset = movie.get('viewOffset', 0)
    duration = int(mediaarguments.get('duration', movie.get('duration', 0))) / 1000

    # Required listItem entries for XBMC
    details = {'plot': movie.get('summary', '').encode('utf-8'),
               'title': movie.get('title', 'Unknown').encode('utf-8'),
               'sorttitle': movie.get('titleSort', movie.get('title', 'Unknown')).encode('utf-8'),
               'rating': float(movie.get('rating', 0)),
               'studio': movie.get('studio', '').encode('utf-8'),
               'mpaa': movie.get('contentRating', '').encode('utf-8'),
               'year': int(movie.get('year', 0)),
               'date': movie.get('originallyAvailableAt', '1970-01-01'),
               'premiered': movie.get('originallyAvailableAt', '1970-01-01'),
               'tagline': movie.get('tagline', ''),
               'dateAdded': str(datetime.datetime.fromtimestamp(int(movie.get('addedAt', 0)))),
               'mediatype': "movie"}

    # Extra data required to manage other properties
    extraData = {'type': "Video",
                 'source': 'movies',
                 'thumb': get_thumb_image(movie, server),
                 'fanart_image': get_fanart_image(movie, server),
                 'key': movie.get('key', ''),
                 'ratingKey': str(movie.get('ratingKey', 0)),
                 'duration': duration,
                 'resume': int(int(view_offset) / 1000)}

    # Determine what type of watched flag [overlay] to use
    if int(movie.get('viewCount', 0)) > 0:
        details['playcount'] = 1
    elif int(movie.get('viewCount', 0)) == 0:
        details['playcount'] = 0

    # Extended Metadata
    if not settings.get_setting('skipmetadata'):
        details['cast'] = tempcast
        details['director'] = " / ".join(tempdir)
        details['writer'] = " / ".join(tempwriter)
        details['genre'] = " / ".join(tempgenre)

    if movie.get('primaryExtraKey') is not None:
        details['trailer'] = "plugin://plugin.video.plexbmc/?url=%s%s?t=%s&mode=%s" % (server.get_url_location(), movie.get('primaryExtraKey', ''), random_number, MODE_PLAYLIBRARY)
        log_print.debug('Trailer plugin url added: %s' % details['trailer'])

    # Add extra media flag data
    if not settings.get_setting('skipflags'):
        extraData.update(get_media_data(mediaarguments))

    # Build any specific context menu entries
    if not settings.get_setting('skipcontextmenus'):
        context = build_context_menu(url, extraData, server)
    else:
        context = None
    # http:// <server> <path> &mode=<mode> &t=<rnd>
    extraData['mode'] = MODE_PLAYLIBRARY
    separator = "?"
    if "?" in extraData['key']:
        separator = "&"
    final_url = "%s%s%st=%s" % (server.get_url_location(), extraData['key'], separator, random_number)

    add_item_to_gui(final_url, details, extraData, context, folder=False)
    return


def get_media_data(tag_dict):
    '''
        Extra the media details from the XML
        @input: dict of <media /> tag attributes
        @output: dict of required values
    '''
    log_print.debug("== ENTER ==")

    return {'VideoResolution': tag_dict.get('videoResolution', ''),
            'VideoCodec': tag_dict.get('videoCodec', ''),
            'AudioCodec': tag_dict.get('audioCodec', ''),
            'AudioChannels': tag_dict.get('audioChannels', ''),
            'VideoAspect': tag_dict.get('aspectRatio', ''),
            'xbmc_height': tag_dict.get('height'),
            'xbmc_width': tag_dict.get('width'),
            'xbmc_VideoCodec': tag_dict.get('videoCodec'),
            'xbmc_AudioCodec': tag_dict.get('audioCodec'),
            'xbmc_AudioChannels': tag_dict.get('audioChannels'),
            'xbmc_VideoAspect': tag_dict.get('aspectRatio')}


def track_tag(server, tree, track, sectionart="", sectionthumb="", listing=True):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'songs')

    for child in track:
        for babies in child:
            if babies.tag == "Part":
                partDetails = (dict(babies.items()))

    log_print.debug("Part is %s" % partDetails)

    details = {'TrackNumber': int(track.get('index', 0)),
               'discnumber': int(track.get('parentIndex', 0)),
               'title': str(track.get('index', 0)).zfill(2) + ". " + track.get('title', 'Unknown').encode('utf-8'),
               'rating': float(track.get('rating', 0)),
               'album': track.get('parentTitle', tree.get('parentTitle', '')).encode('utf-8'),
               'artist': track.get('grandparentTitle', tree.get('grandparentTitle', '')).encode('utf-8'),
               'duration': int(track.get('duration', 0)) / 1000}

    extraData = {'type': "music",
                 'fanart_image': sectionart,
                 'thumb': sectionthumb,
                 'key': track.get('key', ''),
                 'mode': MODE_PLAYLIBRARY}

    # If we are streaming, then get the virtual location
    u = "%s%s" % (server.get_url_location(), extraData['key'])

    if listing:
        add_item_to_gui(u, details, extraData, folder=False)
    else:
        return u, details


def playlist_tag(url, server, tree, track, sectionart="", sectionthumb="", listing=True):
    log_print.debug("== ENTER ==")

    details = {'title': track.get('title', 'Unknown').encode('utf-8'),
               'duration': int(track.get('duration', 0)) / 1000
               }

    extraData = {'type': track.get('playlistType', ''),
                 'thumb': get_thumb_image({'thumb': track.get('composite', '')}, server)}

    if extraData['type'] == "video":
        extraData['mode'] = MODE_MOVIES
    elif extraData['type'] == "audio":
        extraData['mode'] = MODE_TRACKS
    else:
        extraData['mode'] = MODE_GETCONTENT

    u = get_link_url(url, track, server)

    if listing:
        add_item_to_gui(u, details, extraData, folder=True)
    else:
        return url, details


def photo(url, tree=None):
    log_print.debug("== ENTER ==")
    server = plex_network.get_server_from_url(url)

    xbmcplugin.setContent(pluginhandle, 'photo')

    tree = get_xml(url, tree)
    if tree is None:
        return

    sectionArt = get_fanart_image(tree, server)
    set_window_heading(tree)
    for picture in tree:

        details = {'title': picture.get('title', picture.get('name', 'Unknown')).encode('utf-8')}

        if not details['title']:
            details['title'] = "Unknown"

        extraData = {'thumb': get_thumb_image(picture, server),
                     'fanart_image': get_fanart_image(picture, server),
                     'type': "image"}

        if extraData['fanart_image'] == "":
            extraData['fanart_image'] = sectionArt

        u = get_link_url(url, picture, server)

        if picture.tag == "Directory":
            extraData['mode'] = MODE_PHOTOS
            add_item_to_gui(u, details, extraData)

        elif picture.tag == "Photo":

            if tree.get('viewGroup', '') == "photo":
                for pics in picture:
                    if pics.tag == "Media":
                        for images in pics:
                            if images.tag == "Part":
                                extraData['key'] = server.get_url_location() + images.get('key', '')
                                details['size'] = int(images.get('size', 0))
                                u = extraData['key']

            add_item_to_gui(u, details, extraData, folder=False)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def music(url, tree=None):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'artists')

    server = plex_network.get_server_from_url(url)

    tree = get_xml(url, tree)
    if tree is None:
        return

    set_window_heading(tree)
    for grapes in tree:

        if grapes.get('key') is None:
            continue

        details = {'genre': grapes.get('genre', '').encode('utf-8'),
                   'artist': grapes.get('artist', '').encode('utf-8'),
                   'year': int(grapes.get('year', 0)),
                   'album': grapes.get('album', '').encode('utf-8'),
                   'tracknumber': int(grapes.get('index', 0)),
                   'title': "Unknown"}

        extraData = {'type': "Music",
                     'thumb': get_thumb_image(grapes, server),
                     'fanart_image': get_fanart_image(grapes, server)}

        if extraData['fanart_image'] == "":
            extraData['fanart_image'] = get_fanart_image(tree, server)

        u = get_link_url(url, grapes, server)

        if grapes.tag == "Track":
            log_print.debug("Track Tag")
            xbmcplugin.setContent(pluginhandle, 'songs')

            details['title'] = grapes.get('track', grapes.get('title', 'Unknown')).encode('utf-8')
            details['duration'] = int(int(grapes.get('totalTime', 0)) / 1000)

            extraData['mode'] = MODE_BASICPLAY
            add_item_to_gui(u, details, extraData, folder=False)

        else:

            if grapes.tag == "Artist":
                log_print.debug("Artist Tag")
                xbmcplugin.setContent(pluginhandle, 'artists')
                details['title'] = grapes.get('artist', 'Unknown').encode('utf-8')

            elif grapes.tag == "Album":
                log_print.debug("Album Tag")
                xbmcplugin.setContent(pluginhandle, 'albums')
                details['title'] = grapes.get('album', 'Unknown').encode('utf-8')

            elif grapes.tag == "Genre":
                details['title'] = grapes.get('genre', 'Unknown').encode('utf-8')

            else:
                log_print.debug("Generic Tag: %s" % grapes.tag)
                details['title'] = grapes.get('title', 'Unknown').encode('utf-8')

            extraData['mode'] = MODE_MUSIC
            add_item_to_gui(u, details, extraData)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def get_thumb_image(data, server, width=720, height=720):
    '''
        Simply take a URL or path and determine how to format for images
        @ input: elementTree element, server name
        @ return formatted URL
    '''

    if settings.get_setting('skipimages'):
        return ''

    thumbnail = data.get('thumb', '').split('?t')[0].encode('utf-8')

    if thumbnail.startswith("http"):
        return thumbnail

    elif thumbnail.startswith('/'):
        if settings.get_setting('fullres_thumbs'):
            return server.get_kodi_header_formatted_url(thumbnail)
        else:
            return server.get_kodi_header_formatted_url('/photo/:/transcode?url=%s&width=%s&height=%s'
                                                        % (urllib.quote_plus('http://localhost:32400' + thumbnail),
                                                           width, height))

    return GENERIC_THUMBNAIL


def get_banner_image(data, server, width=720, height=720):
    """
        Simply take a URL or path and determine how to format for images
        @ input: elementTree element, server name
        @ return formatted URL
    """

    if settings.get_setting('skipimages'):
        return ''

    thumbnail = data.get('banner', '').split('?t')[0].encode('utf-8')

    if thumbnail.startswith("http"):
        return thumbnail

    elif thumbnail.startswith('/'):
        if settings.get_setting('fullres_thumbs'):
            return server.get_kodi_header_formatted_url(thumbnail)
        else:
            return server.get_kodi_header_formatted_url('/photo/:/transcode?url=%s&width=%s&height=%s'
                                                        % (urllib.quote_plus('http://localhost:32400' + thumbnail),
                                                           width, height))

    return GENERIC_THUMBNAIL


def get_fanart_image(data, server, width=1280, height=720):
    '''
        Simply take a URL or path and determine how to format for fanart
        @ input: elementTree element, server name
        @ return formatted URL for photo resizing
    '''
    if settings.get_setting('skipimages'):
        return ''

    fanart = data.get('art', '').encode('utf-8')

    if fanart.startswith('http'):
        return fanart

    elif fanart.startswith('/'):
        if settings.get_setting('fullres_fanart'):
            return server.get_kodi_header_formatted_url(fanart)
        else:
            return server.get_kodi_header_formatted_url('/photo/:/transcode?url=%s&width=%s&height=%s' % (urllib.quote_plus('http://localhost:32400' + fanart), width, height))

    return ''


def get_link_url(url, pathData, server):
    path = pathData.get('key', '')

    log_print.debug("Path is %s" % path)

    if path == '':
        log_print.debug("Empty Path")
        return

    # If key starts with http, then return it
    if path.startswith('http'):
        log_print.debug("Detected http(s) link")
        return path

    # If key starts with a / then prefix with server address
    elif path.startswith('/'):
        log_print.debug("Detected base path link")
        return '%s%s' % (server.get_url_location(), path)

    # If key starts with plex:// then it requires transcoding
    elif path.startswith("plex:"):
        log_print.debug("Detected plex link")
        components = path.split('&')
        for i in components:
            if 'prefix=' in i:
                del components[components.index(i)]
                break
        if pathData.get('identifier') is not None:
            components.append('identifier=' + pathData['identifier'])

        path = '&'.join(components)
        return 'plex://' + server.get_location() + '/' + '/'.join(path.split('/')[3:])

    elif path.startswith("rtmp"):
        log_print.debug("Detected RTMP link")
        return path

    # Any thing else is assumed to be a relative path and is built on existing url
    else:
        log_print.debug("Detected relative link")
        return "%s/%s" % (url, path)


def plex_online(url):
    log_print.debug("== ENTER ==")
    xbmcplugin.setContent(pluginhandle, 'addons')

    server = plex_network.get_server_from_url(url)

    tree = server.processed_xml(url)
    if tree is None:
        return

    for plugin in tree:

        details = {'title': plugin.get('title', plugin.get('name', 'Unknown')).encode('utf-8')}
        extraData = {'type': "Video",
                     'installed': int(plugin.get('installed', 2)),
                     'key': plugin.get('key', ''),
                     'thumb': get_thumb_image(plugin, server),
                     'mode': MODE_CHANNELINSTALL}

        if extraData['installed'] == 1:
            details['title'] = details['title'] + " (installed)"

        elif extraData['installed'] == 2:
            extraData['mode'] = MODE_PLEXONLINE

        u = get_link_url(url, plugin, server)

        extraData['parameters'] = {'name': details['title']}

        add_item_to_gui(u, details, extraData)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def install(url, name):
    log_print.debug("== ENTER ==")
    server = plex_network.get_server_from_url(url)
    tree = server.processed_xml(url)
    if tree is None:
        return

    operations = {}
    i = 0
    for plums in tree.findall('Directory'):
        operations[i] = plums.get('title')

        # If we find an install option, switch to a yes/no dialog box
        if operations[i].lower() == "install":
            log_print.debug("Not installed.  Print dialog")
            ret = xbmcgui.Dialog().yesno(ADDON.getLocalizedString(32002), ADDON.getLocalizedString(32003) + name)

            if ret:
                log_print.debug("Installing....")
                tree = server.processed_xml(url + "/install")

                msg = tree.get('message', '(blank)')
                log_print.debug(msg)
                xbmcgui.Dialog().ok(ADDON.getLocalizedString(32002), msg)
            return

        i += 1

    # Else continue to a selection dialog box
    ret = xbmcgui.Dialog().select(ADDON.getLocalizedString(32004), operations.values())

    if ret == -1:
        log_print.debug("No option selected, cancelling")
        return

    log_print.debug("Option %s selected.  Operation is %s" % (ret, operations[ret]))
    u = url + "/" + operations[ret].lower()
    tree = server.processed_xml(u)

    msg = tree.get('message')
    log_print.debug(msg)
    xbmcgui.Dialog().ok(ADDON.getLocalizedString(32002), msg)
    xbmc.executebuiltin("Container.Refresh")

    return


def channel_view(url):
    log_print.debug("== ENTER ==")
    server = plex_network.get_server_from_url(url)
    tree = server.processed_xml(url)

    if tree is None:
        return

    set_window_heading(tree)
    for channels in tree.getiterator('Directory'):

        if channels.get('local', '') == "0":
            continue

        arguments = dict(channels.items())

        extraData = {'fanart_image': get_fanart_image(channels, server),
                     'thumb': get_thumb_image(channels, server)}

        details = {'title': channels.get('title', 'Unknown')}

        suffix = channels.get('key').split('/')[1]

        if channels.get('unique', '') == '0':
            details['title'] = "%s (%s)" % (details['title'], suffix)

        # Alter data sent into getlinkurl, as channels use path rather than key
        p_url = get_link_url(url, {'key': channels.get('key'), 'identifier': channels.get('key')}, server)

        if suffix == "photos":
            extraData['mode'] = MODE_PHOTOS
        elif suffix == "video":
            extraData['mode'] = MODE_PLEXPLUGINS
        elif suffix == "music":
            extraData['mode'] = MODE_MUSIC
        else:
            extraData['mode'] = MODE_GETCONTENT

        add_item_to_gui(p_url, details, extraData)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def display_content(acceptable_level, content_level):
    '''
        Takes a content Rating and decides whether it is an allowable
        level, as defined by the content filter
        @input: content rating
        @output: boolean
    '''

    log_print.info("Checking rating flag [%s] against [%s]" % (content_level, acceptable_level))

    if acceptable_level == "2":
        log_print.debug("OK to display")
        return True

    content_map = {0: ADDON.getLocalizedString(32589),
                   1: ADDON.getLocalizedString(32590),
                   2: ADDON.getLocalizedString(32591)}

    rating_map = {'G': 0,  # MPAA Kids
                  'PG': 0,  # MPAA Kids
                  'PG-13': 1,  # MPAA Teens
                  'R': 2,  # MPAA Adults
                  'NC-17': 2,  # MPAA Adults
                  'NR': 2,  # MPAA Adults
                  'Unrated': 2,  # MPAA Adults

                  'U': 0,  # BBFC Kids
                  'PG': 0,  # BBFC Kids
                  '12': 1,  # BBFC Teens
                  '12A': 1,  # BBFC Teens
                  '15': 1,  # BBFC Teens
                  '18': 2,  # BBFC Adults
                  'R18': 2,  # BBFC Adults

                  'E': 0,  # ACB Kids (hopefully)
                  'G': 0,  # ACB Kids
                  'PG': 0,  # ACB Kids
                  'M': 1,  # ACB Teens
                  'MA15+': 2,  # ADC Adults
                  'R18+': 2,  # ACB Adults
                  'X18+': 2,  # ACB Adults

                  'TV-Y': 0,  # US TV - Kids
                  'TV-Y7': 0,  # US TV - Kids
                  'TV -G': 0,  # Us TV - kids
                  'TV-PG': 1,  # US TV - Teens
                  'TV-14': 1,  # US TV - Teens
                  'TV-MA': 2,  # US TV - Adults

                  'G': 0,  # CAN - kids
                  'PG': 0,  # CAN - kids
                  '14A': 1,  # CAN - teens
                  '18A': 2,  # CAN - Adults
                  'R': 2,  # CAN - Adults
                  'A': 2}  # CAN - Adults

    if content_level is None or content_level == "None":
        log_print.debug("Setting [None] rating as %s" % content_map[settings.get_setting('contentNone')])
        if settings.get_setting('contentNone') <= acceptable_level:
            log_print.debug("OK to display")
            return True
    else:
        try:
            if rating_map[content_level] <= acceptable_level:
                log_print.debug("OK to display")
                return True
        except:
            log_print.error("Unknown rating flag [%s] whilst lookuing for [%s] - will filter for now, but needs to be added" % (content_level, content_map[acceptable_level]))

    log_print.debug("NOT OK to display")
    return False


def myplex_queue():
    log_print.debug("== ENTER ==")

    if not plex_network.is_myplex_signedin():
        xbmc.executebuiltin("Notification(" + ADDON.getLocalizedString(32069) + ",)")
        return

    tree = plex_network.get_myplex_queue()

    plex_plugins('https://plex.tv/playlists/queue/all', tree)
    return


def refresh_plex_library(server_uuid, section_id):
    log_print.debug("== ENTER ==")

    server = plex_network.get_server_from_uuid(server_uuid)
    server.refresh_section(section_id)

    log_print.info("Library refresh requested")
    xbmc.executebuiltin("Notification(" + ADDON.getLocalizedString(32068) + ",100)")
    return


def watched(server_uuid, metadata_id, watched_status='watch'):
    log_print.debug("== ENTER ==")

    server = plex_network.get_server_from_uuid(server_uuid)

    if watched_status == 'watch':
        log_print.info("Marking %s as watched" % metadata_id)
        server.mark_item_watched(metadata_id)
    else:
        log_print.info("Marking %s as unwatched" % metadata_id)
        server.mark_item_unwatched(metadata_id)

    xbmc.executebuiltin("Container.Refresh")

    return


def delete_library_media(server_uuid, metadata_id):
    log_print.debug("== ENTER ==")
    log_print.info("Deleting media at: %s" % metadata_id)

    return_value = xbmcgui.Dialog().yesno(ADDON.getLocalizedString(32000), ADDON.getLocalizedString(32001))

    if return_value:
        log_print.debug("Deleting....")
        server = plex_network.get_server_from_uuid(server_uuid)
        server.delete_metadata(metadata_id)
        xbmc.executebuiltin("Container.Refresh")

    return True


def set_library_subtitiles(server_uuid, metadata_id):
    """
        Display a list of available Subtitle streams and allow a user to select one.
        The currently selected stream will be annotated with a *
    """
    log_print.debug("== ENTER ==")

    server = plex_network.get_server_from_uuid(server_uuid)
    tree = server.get_metadata(metadata_id)

    sub_list = ['']
    display_list = ["None"]
    fl_select = False
    for parts in tree.getiterator('Part'):

        part_id = parts.get('id')

        for streams in parts:

            if streams.get('streamType', '') == "3":

                stream_id = streams.get('id')
                lang = streams.get('languageCode', "Unknown").encode('utf-8')
                log_print.debug("Detected Subtitle stream [%s] [%s]" % (stream_id, lang))

                if streams.get('format', streams.get('codec')) == "idx":
                    log_print.debug("Stream: %s - Ignoring idx file for now" % stream_id)
                    continue
                else:
                    sub_list.append(stream_id)

                    if streams.get('selected') == '1':
                        fl_select = True
                        language = streams.get('language', 'Unknown') + "*"
                    else:
                        language = streams.get('language', 'Unknown')

                    display_list.append(language)
        break

    if not fl_select:
        display_list[0] = display_list[0] + "*"

    subtitle_screen = xbmcgui.Dialog()
    result = subtitle_screen.select(ADDON.getLocalizedString(32072), display_list)
    if result == -1:
        return False

    log_print.debug("User has selected stream %s" % sub_list[result])
    server.set_subtitle_stream(part_id, sub_list[result])

    return True


def set_library_audio(server_uuid, metadata_id):
    """
        Display a list of available audio streams and allow a user to select one.
        The currently selected stream will be annotated with a *
    """
    log_print.debug("== ENTER ==")

    server = plex_network.get_server_from_uuid(server_uuid)
    tree = server.get_metadata(metadata_id)

    audio_list = []
    display_list = []
    for parts in tree.getiterator('Part'):

        part_id = parts.get('id')

        for streams in parts:

            if streams.get('streamType', '') == "2":

                stream_id = streams.get('id')
                audio_list.append(stream_id)
                lang = streams.get('languageCode', "Unknown")

                log_print.debug("Detected Audio stream [%s] [%s] " % (stream_id, lang))

                if streams.get('channels', 'Unknown') == '6':
                    channels = "5.1"
                elif streams.get('channels', 'Unknown') == '7':
                    channels = "6.1"
                elif streams.get('channels', 'Unknown') == '2':
                    channels = "Stereo"
                else:
                    channels = streams.get('channels', 'Unknown')

                if streams.get('codec', 'Unknown') == "ac3":
                    codec = "AC3"
                elif streams.get('codec', 'Unknown') == "dca":
                    codec = "DTS"
                else:
                    codec = streams.get('codec', 'Unknown')

                language = "%s (%s %s)" % (streams.get('language', 'Unknown').encode('utf-8'), codec, channels)

                if streams.get('selected') == '1':
                    language = language + "*"

                display_list.append(language)
        break

    audio_screen = xbmcgui.Dialog()
    result = audio_screen.select(ADDON.getLocalizedString(32073), display_list)
    if result == -1:
        return False

    log_print.debug("User has selected stream %s" % audio_list[result])

    server.set_audio_stream(part_id, audio_list[result])

    return True


def set_window_heading(tree):
    gui_window = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    try:
        gui_window.setProperty("heading", tree.get('title1'))
    except:
        gui_window.clearProperty("heading")
    try:
        gui_window.setProperty("heading2", heading2_translate(tree))
    except:
        gui_window.clearProperty("heading2")


def get_master_server(all_servers=False):
    log_print.debug("== ENTER ==")

    possible_servers = []
    current_master = settings.get_setting('masterServer')
    for serverData in plex_network.get_server_list():
        log_print.debug(str(serverData))
        if serverData.get_master() == 1:
            possible_servers.append(serverData)
    log_print.debug("Possible master servers are: %s" % possible_servers)

    if all_servers:
        return possible_servers

    if len(possible_servers) > 1:
        preferred = "local"
        for serverData in possible_servers:
            if serverData.get_name == current_master:
                log_print.debug("Returning current master")
                return serverData
            if preferred == "any":
                log_print.debug("Returning 'any'")
                return serverData
            else:
                if serverData.get_discovery() == preferred:
                    log_print.debug("Returning local")
                    return serverData
    elif len(possible_servers) == 0:
        return

    return possible_servers[0]


def set_master_server():
    log_print.debug("== ENTER ==")

    servers = get_master_server(True)
    log_print.debug(str(servers))

    current_master = settings.get_setting('masterServer')

    display_option_list = []
    for address in servers:
        found_server = address.get_name()
        if found_server == current_master:
            found_server = found_server + "*"
        display_option_list.append(found_server)

    audio_select_screen = xbmcgui.Dialog()
    result = audio_select_screen.select(ADDON.getLocalizedString(32074), display_option_list)
    if result == -1:
        return False

    log_print.debug("Setting master server to: %s" % servers[result].get_name())
    settings.update_master_server(servers[result].get_name())
    return


def display_known_servers():
    known_servers = plex_network.get_server_list()
    display_list = []

    for device in known_servers:
        name = device.get_name()
        status = device.get_status()
        if device.is_secure():
            secure = "SSL"
        else:
            secure = "Not Secure"

        log_print.debug("Device: %s [%s] [%s]" % (name, status, secure))
        log_print.debugplus("Full device dump [%s]" % device.__dict__)
        display_list.append("%s [%s] [%s]" % (name, status, secure))

    server_display_screen = xbmcgui.Dialog()
    server_display_screen.select(ADDON.getLocalizedString(32075), display_list)
    return


def display_plex_servers(url):
    log_print.debug("== ENTER ==")
    ctype = url.split('/')[2]
    log_print.debug("Displaying entries for %s" % ctype)
    servers = plex_network.get_server_list()
    servers_list = len(servers)

    # For each of the servers we have identified
    for mediaserver in servers:

        if mediaserver.is_secondary():
            continue

        details = {'title': mediaserver.get_name()}

        extra_data = {}

        if ctype == "video":
            extra_data['mode'] = MODE_PLEXPLUGINS
            s_url = '%s%s' % (mediaserver.get_url_location(), '/video')
            if servers_list == 1:
                plex_plugins(s_url)
                return

        elif ctype == "online":
            extra_data['mode'] = MODE_PLEXONLINE
            s_url = '%s%s' % (mediaserver.get_url_location(), '/system/plexonline')
            if servers_list == 1:
                plex_online(s_url)
                return

        elif ctype == "music":
            extra_data['mode'] = MODE_MUSIC
            s_url = '%s%s' % (mediaserver.get_url_location(), '/music')
            if servers_list == 1:
                music(s_url)
                return

        elif ctype == "photo":
            extra_data['mode'] = MODE_PHOTOS
            s_url = '%s%s' % (mediaserver.get_url_location(), '/photos')
            if servers_list == 1:
                photo(s_url)
                return
        else:
            s_url = None

        add_item_to_gui(s_url, details, extra_data)

    xbmcplugin.endOfDirectory(pluginhandle, cacheToDisc=settings.get_setting('kodicache'))


def switch_user():
    # Get listof users
    user_list = plex_network.get_plex_home_users()
    # zero means we are not plexHome'd up
    if user_list is None or len(user_list) == 1:
        log_print.debug("No users listed or only one user, plexHome not enabled")
        return False

    log_print.debug("found %s users: %s" % (len(user_list), user_list.keys()))

    # Get rid of currently logged in user.
    user_list.pop(plex_network.get_myplex_user(), None)

    select_screen = xbmcgui.Dialog()
    result = select_screen.select(ADDON.getLocalizedString(32076), user_list.keys())
    if result == -1:
        log_print.debug("Dialog cancelled")
        return False

    log_print.debug("user [%s] selected" % user_list.keys()[result])
    user = user_list[user_list.keys()[result]]

    pin = None
    if user['protected'] == '1':
        log_print.debug("Protected user [%s], requesting password" % user['title'])
        pin = select_screen.input(ADDON.getLocalizedString(32077), type=xbmcgui.INPUT_NUMERIC, option=xbmcgui.ALPHANUM_HIDE_INPUT)

    success, msg = plex_network.switch_plex_home_user(user['id'], pin)

    if not success:
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(32005), msg)
        return False

    return True


# #So this is where we really start the addon 
log_print = PrintDebug("PleXBMC")

log_print.debug("PleXBMC -> Running PleXBMC: %s " % GLOBAL_SETUP['__version__'])

wake_servers()

if settings.get_debug() >= log_print.DEBUG_INFO:
    log_print.debug("PleXBMC -> Running Python: %s" % str(sys.version_info))
    log_print.debug("PleXBMC -> CWD is set to: %s" % GLOBAL_SETUP['__cwd__'])
    log_print.debug("PleXBMC -> Platform: %s" % GLOBAL_SETUP['platform'])
    log_print.debug("PleXBMC -> Setting debug: %s" % log_print.get_name(settings.get_debug()))
    log_print.debug("PleXBMC -> FullRes Thumbs are set to: %s" % settings.get_setting('fullres_thumbs'))
    log_print.debug("PleXBMC -> Settings streaming: %s" % settings.get_stream())
    log_print.debug("PleXBMC -> Setting filter menus: %s" % settings.get_setting('secondary'))
    log_print.debug("PleXBMC -> Flatten is: %s" % settings.get_setting('flatten'))
    if settings.get_setting('streamControl') == SUB_AUDIO_XBMC_CONTROL:
        log_print.debug("PleXBMC -> Setting stream Control to : XBMC CONTROL")
    elif settings.get_setting('streamControl') == SUB_AUDIO_PLEX_CONTROL:
        log_print.debug("PleXBMC -> Setting stream Control to : PLEX CONTROL")
    elif settings.get_setting('streamControl') == SUB_AUDIO_NEVER_SHOW:
        log_print.debug("PleXBMC -> Setting stream Control to : NEVER SHOW")

    log_print.debug("PleXBMC -> Force DVD playback: %s" % settings.get_setting('forcedvd'))
    log_print.debug("PleXBMC -> SMB IP Override: %s" % settings.get_setting('nasoverride'))
    if settings.get_setting('nasoverride') and not settings.get_setting('nasoverrideip'):
        log_print.error("PleXBMC -> No NAS IP Specified.  Ignoring setting")
    else:
        log_print.debug("PleXBMC -> NAS IP: " + settings.get_setting('nasoverrideip'))
else:
    log_print.debug("PleXBMC -> Debug is turned off.  Running silent")

pluginhandle = 0
argv = []
plex_network = plex.Plex(load=False)


def start_plexbmc(sys_argv):
    global argv
    argv = sys_argv

    global pluginhandle
    try:
        pluginhandle = int(sys_argv[1])
    except (ValueError, IndexError):
        pass

    try:
        params = get_params(sys_argv[2])
    except:
        params = {}

    # Now try and assign some data to them
    param_url = params.get('url')
    command = None

    if param_url:
        if param_url.startswith('http') or param_url.startswith('file'):
            param_url = urllib.unquote(param_url)
        elif param_url.startswith('cmd'):
            command = urllib.unquote(param_url).split(':')[1]

    param_name = urllib.unquote_plus(params.get('name', ""))
    mode = int(params.get('mode', -1))
    play_transcode = True if int(params.get('transcode', 0)) == 1 else False
    param_identifier = params.get('identifier')
    param_indirect = params.get('indirect')
    force = params.get('force')
    helper = True if int(params.get('helper', 0)) == 1 else False

    if command is None:
        try:
            command = sys_argv[1]
        except:
            pass

    if command == "refresh":
        xbmc.executebuiltin("Container.Refresh")
    elif command == "switchuser":
        if switch_user():
            gui_window = xbmcgui.Window(10000)
            gui_window.setProperty("plexbmc.plexhome_user", str(plex_network.get_myplex_user()))
            gui_window.setProperty("plexbmc.plexhome_avatar", str(plex_network.get_myplex_avatar()))
            xbmc.executebuiltin("Container.Refresh")
        else:
            log_print.info("Switch User Failed")

    elif command == "signout":
        if not plex_network.is_admin():
            return xbmcgui.Dialog().ok(ADDON.getLocalizedString(32006), ADDON.getLocalizedString(32007))

        ret = xbmcgui.Dialog().yesno(ADDON.getLocalizedString(32008), ADDON.getLocalizedString(32009))
        if ret:
            plex_network.signout()
            gui_window = xbmcgui.Window(10000)
            gui_window.clearProperty("plexbmc.plexhome_user")
            gui_window.clearProperty("plexbmc.plexhome_avatar")
            xbmc.executebuiltin("Container.Refresh")

    elif command == "signin":
        from .plex import plexsignin
        signin_window = plexsignin.PlexSignin('Myplex Login')
        signin_window.set_authentication_target(plex_network)
        signin_window.start()
        del signin_window

    elif command == "signintemp":
        # Awful hack to get around running a script from a listitem..
        xbmc.executebuiltin('RunScript(plugin.video.plexbmc, signin)')

    elif command == "managemyplex":

        if not plex_network.is_myplex_signedin():
            ret = xbmcgui.Dialog().yesno(ADDON.getLocalizedString(32010), ADDON.getLocalizedString(32011))
            if ret:
                xbmc.executebuiltin('RunScript(plugin.video.plexbmc, signin)')
            else:
                return

        elif not plex_network.is_admin():
            return xbmcgui.Dialog().ok(ADDON.getLocalizedString(32010), ADDON.getLocalizedString(32012))

        from .plex import plexsignin
        manage_window = plexsignin.PlexManage('Manage myplex')
        manage_window.set_authentication_target(plex_network)
        manage_window.start()
        del manage_window

    else:
        plex_network.load()

        if command == "update":
            server_uuid = sys_argv[2]
            section_id = sys_argv[3]
            refresh_plex_library(server_uuid, section_id)

        # Mark an item as watched/unwatched in plex    
        elif command == "watch":
            server_uuid = sys_argv[2]
            metadata_id = sys_argv[3]
            watch_status = sys_argv[4]
            watched(server_uuid, metadata_id, watch_status)

        # delete media from PMS    
        elif command == "delete":
            server_uuid = sys_argv[2]
            metadata_id = sys_argv[3]
            delete_library_media(server_uuid, metadata_id)

        # Display subtitle selection screen    
        elif command == "subs":
            server_uuid = sys_argv[2]
            metadata_id = sys_argv[3]
            set_library_subtitiles(server_uuid, metadata_id)

        # Display audio streanm selection screen    
        elif command == "audio":
            server_uuid = sys_argv[2]
            metadata_id = sys_argv[3]
            set_library_audio(server_uuid, metadata_id)

        # Allow a mastre server to be selected (for myplex queue)    
        elif command == "master":
            set_master_server()

        # else move to the main code    
        else:
            gui_window = xbmcgui.Window(xbmcgui.getCurrentWindowId())
            gui_window.clearProperty("heading")
            gui_window.clearProperty("heading2")

            log_print.debug("PleXBMC -> Mode: %s " % mode)
            log_print.debug("PleXBMC -> URL: %s" % param_url)
            log_print.debug("PleXBMC -> Name: %s" % param_name)
            log_print.debug("PleXBMC -> identifier: %s" % param_identifier)

            # Run a function based on the mode variable that was passed in the URL
            if (mode is None) or (param_url is None) or (len(param_url) < 1):
                display_sections()

            elif mode == MODE_GETCONTENT:
                get_content(param_url)

            elif mode == MODE_TVSHOWS:
                process_tvshows(param_url)

            elif mode == MODE_MOVIES:
                process_movies(param_url)

            elif mode == MODE_ARTISTS:
                artist(param_url)

            elif mode == MODE_TVSEASONS:
                process_tvseasons(param_url)

            elif mode == MODE_PLAYLIBRARY:
                play_library_media(param_url, force=force, override=play_transcode, helper=helper)

            elif mode == MODE_TVEPISODES:
                process_tvepisodes(param_url)

            elif mode == MODE_PLEXPLUGINS:
                plex_plugins(param_url)

            elif mode == MODE_PROCESSXML:
                process_xml(param_url)

            elif mode == MODE_BASICPLAY:
                play_media_stream(param_url)

            elif mode == MODE_ALBUMS:
                albums(param_url)

            elif mode == MODE_TRACKS:
                tracks(param_url)

            elif mode == MODE_PHOTOS:
                photo(param_url)

            elif mode == MODE_MUSIC:
                music(param_url)

            elif mode == MODE_VIDEOPLUGINPLAY:
                play_video_channel(param_url, param_identifier, param_indirect)

            elif mode == MODE_PLEXONLINE:
                plex_online(param_url)

            elif mode == MODE_CHANNELINSTALL:
                install(param_url, param_name)

            elif mode == MODE_CHANNELVIEW:
                channel_view(param_url)

            elif mode == MODE_PLAYLIBRARY_TRANSCODE:
                play_library_media(param_url, override=True)

            elif mode == MODE_MYPLEXQUEUE:
                myplex_queue()

            elif mode == MODE_CHANNELSEARCH:
                channel_search(param_url, params.get('prompt'))

            elif mode == MODE_CHANNELPREFS:
                channel_settings(param_url, params.get('id'))

            elif mode == MODE_SHARED_MOVIES:
                display_sections(cfilter="movies", display_shared=True)

            elif mode == MODE_SHARED_SHOWS:
                display_sections(cfilter="tvshows", display_shared=True)

            elif mode == MODE_SHARED_PHOTOS:
                display_sections(cfilter="photos", display_shared=True)

            elif mode == MODE_SHARED_MUSIC:
                display_sections(cfilter="music", display_shared=True)

            elif mode == MODE_SHARED_ALL:
                display_sections(display_shared=True)

            elif mode == MODE_DELETE_REFRESH:
                plex_network.delete_cache()
                xbmc.executebuiltin("Container.Refresh")

            elif mode == MODE_PLAYLISTS:
                process_xml(param_url)

            elif mode == MODE_DISPLAYSERVERS:
                display_plex_servers(param_url)