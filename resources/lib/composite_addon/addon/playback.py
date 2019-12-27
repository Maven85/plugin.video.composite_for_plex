# -*- coding: utf-8 -*-
"""

    Copyright (C) 2011-2018 PleXBMC (plugin.video.plexbmc) by hippojay (Dave Hawes-Johnson)
    Copyright (C) 2018-2019 Composite (plugin.video.composite_for_plex)

    This file is part of Composite (plugin.video.composite_for_plex)

    SPDX-License-Identifier: GPL-2.0-or-later
    See LICENSES/GPL-2.0-or-later.txt for more information.
"""

from six.moves import range
from six.moves.urllib_parse import unquote

from kodi_six import xbmc  # pylint: disable=import-error
from kodi_six import xbmcgui  # pylint: disable=import-error
from kodi_six import xbmcplugin  # pylint: disable=import-error
from kodi_six import xbmcvfs  # pylint: disable=import-error

from .common import get_handle
from .constants import CONFIG
from .constants import StreamControl
from .items.common import get_thumb_image
from .items.track import create_track_item
from .logger import Logger
from .strings import encode_utf8
from .strings import i18n
from .utils import get_file_type
from .utils import get_xml
from .utils import write_pickled

LOG = Logger()


def monitor_channel_transcode_playback(context, server, session_id):
    # Logic may appear backward, but this does allow for a failed start to be detected
    # First while loop waiting for start
    if context.settings.get_setting('monitoroff'):
        return

    count = 0
    monitor = xbmc.Monitor()
    player = xbmc.Player()

    LOG.debug('Not playing yet...sleeping for up to 20 seconds at 2 second intervals')
    while not player.isPlaying() and not monitor.abortRequested():
        count += 1
        if count >= 10:
            # Waited 20 seconds and still no movie playing - assume it isn't going to..
            return
        if monitor.waitForAbort(2.0):
            return

    LOG.debug('Waiting for playback to finish')
    while player.isPlaying() and not monitor.abortRequested():
        if monitor.waitForAbort(0.5):
            break

    LOG.debug('Playback Stopped')
    LOG.debug('Stopping PMS transcode job with session: %s' % session_id)
    server.stop_transcode_session(session_id)


def play_media_id_from_uuid(context, data):
    server = context.plex_network.get_server_from_uuid(data['server_uuid'])
    data['url'] = server.get_formatted_url('/library/metadata/%s' % data['media_id'])
    play_library_media(context, data)


def play_library_media(context, data):
    server = context.plex_network.get_server_from_url(data['url'])
    media_id = data['url'].split('?')[0].split('&')[0].split('/')[-1]

    tree = get_xml(context, data['url'])
    if tree is None:
        return

    streams = get_audio_subtitles_from_media(context, server, tree, True)

    stream_data = streams.get('full_data', {})
    stream_media = streams.get('media', {})

    if data.get('force') and streams['type'] == 'music':
        play_playlist(context, server, streams)
        return

    url = MediaSelect(context, server, streams).media_url

    if url is None:
        return

    transcode = is_transcode_required(context, streams.get('details', [{}]), data['transcode'])
    try:
        transcode_profile = int(data['transcode_profile'])
    except ValueError:
        transcode_profile = 0

    url, session = get_playback_url_and_session(server, url, streams, transcode, transcode_profile)

    details = {
        'resume': int(int(stream_media['viewOffset']) / 1000),
        'duration': int(int(stream_media['duration']) / 1000),
    }

    if isinstance(data.get('force'), int):
        if int(data['force']) > 0:
            details['resume'] = int(int(data['force']) / 1000)
        else:
            details['resume'] = data['force']

    LOG.debug('Resume has been set to %s' % details['resume'])

    list_item = create_playback_item(url, session, streams, stream_data, details)

    if streams['type'] in ['music', 'video']:
        server.settings = None  # can't pickle xbmcaddon.Addon()
        write_pickled('playback_monitor.pickle', {
            'media_id': media_id,
            'playing_file': url,
            'session': session,
            'server': server,
            'streams': streams,
            'callback_args': {
                'transcode': transcode,
                'transcode_profile': transcode_profile
            }
        })

    xbmcplugin.setResolvedUrl(get_handle(), True, list_item)

    set_now_playing_properties(server, media_id)


def create_playback_item(url, session, streams, data, details):
    if CONFIG['kodi_version'] >= 18:
        list_item = xbmcgui.ListItem(path=url, offscreen=True)
    else:
        list_item = xbmcgui.ListItem(path=url)

    if data:
        thumb = data.get('thumbnail', CONFIG['icon'])
        if 'thumbnail' in data:
            del data['thumbnail']  # not a valid info label

        list_item.setInfo(type=streams['type'], infoLabels=data)
        list_item.setArt({
            'icon': thumb,
            'thumb': thumb
        })

    list_item.setProperty('TotalTime', str(details['duration']))
    if session is not None and details.get('resume'):
        list_item.setProperty('ResumeTime', str(details['resume']))
        list_item.setProperty('StartOffset', str(details['resume']))
        LOG.debug('Playback from resume point: %s' % details['resume'])

    return list_item


def set_now_playing_properties(server, media_id):
    window = xbmcgui.Window(10000)
    window.setProperty('plugin.video.composite-nowplaying.server', server.get_location())
    window.setProperty('plugin.video.composite-nowplaying.id', media_id)


def get_playback_url_and_session(server, url, streams, transcode, transcode_profile):
    protocol = url.split(':', 1)[0]

    if protocol == 'file':
        LOG.debug('We are playing a local file')
        return url.split(':', 1)[1], None

    if protocol.startswith('http'):
        LOG.debug('We are playing a stream')
        if transcode:
            LOG.debug('We will be transcoding the stream')
            return server.get_universal_transcode(streams['extra']['path'],
                                                  transcode_profile=transcode_profile)

        return server.get_formatted_url(url), None

    return url, None


def is_transcode_required(context, stream_details, default=False):
    codec = stream_details[0].get('codec')
    resolution = stream_details[0].get('videoResolution')
    try:
        bit_depth = int(stream_details[0].get('bitDepth', 8))
    except ValueError:
        bit_depth = None

    if codec and (context.settings.get_setting('transcode_hevc') and codec.lower() == 'hevc'):
        return True
    if resolution and (context.settings.get_setting('transcode_g1080') and
                       resolution.lower() == '4k'):
        return True
    if bit_depth and (context.settings.get_setting('transcode_g8bit') and bit_depth > 8):
        return True

    return default


def get_audio_subtitles_from_media(context, server, tree, full=False):  # pylint: disable=too-many-locals, too-many-statements, too-many-branches
    """
        Cycle through the Parts sections to find all 'selected' audio and subtitle streams
        If a stream is marked as selected=1 then we will record it in the dict
        Any that are not, are ignored as we do not need to set them
        We also record the media locations for playback decision later on
    """
    LOG.debug('Gather media stream info')

    parts = []
    parts_count = 0
    subtitle = {}
    sub_count = 0
    audio = {}
    audio_count = 0
    media = {}
    sub_offset = -1
    audio_offset = -1
    selected_sub_offset = -1
    selected_audio_offset = -1
    full_data = {}
    contents = 'type'
    extra = {}

    timings = tree.find('Video')
    if timings is not None:
        media_type = 'video'
        extra['path'] = timings.get('key')
    else:
        timings = tree.find('Track')
        if timings:
            media_type = 'music'
            extra['path'] = timings.get('key')
        else:
            timings = tree.find('Photo')
            if timings:
                media_type = 'picture'
                extra['path'] = timings.get('key')
            else:
                LOG.debug('No Video data found')
                return {}

    media['viewOffset'] = timings.get('viewOffset', 0)
    media['duration'] = timings.get('duration', 12 * 60 * 60)

    if full:
        if media_type == 'video':
            full_data = {
                'plot': encode_utf8(timings.get('summary', '')),
                'title': encode_utf8(timings.get('title', i18n('Unknown'))),
                'sorttitle':
                    encode_utf8(timings.get('titleSort',
                                            timings.get('title', i18n('Unknown')))),
                'rating': float(timings.get('rating', 0)),
                'studio': encode_utf8(timings.get('studio', '')),
                'mpaa': encode_utf8(timings.get('contentRating', '')),
                'year': int(timings.get('year', 0)),
                'tagline': timings.get('tagline', ''),
                'thumbnail': get_thumb_image(context, server, timings),
                'mediatype': 'video'
            }

            if timings.get('type') == 'movie':
                full_data['mediatype'] = 'movie'
            elif timings.get('type') == 'episode':
                full_data['episode'] = int(timings.get('index', 0))
                full_data['aired'] = timings.get('originallyAvailableAt', '')
                full_data['tvshowtitle'] = \
                    encode_utf8(timings.get('grandparentTitle', tree.get('grandparentTitle', '')))
                full_data['season'] = int(timings.get('parentIndex', tree.get('parentIndex', 0)))
                full_data['mediatype'] = 'episode'

            if not context.settings.get_setting('skipmetadata'):
                tree_genres = timings.findall('Genre')
                if tree_genres is not None:
                    full_data['genre'] = [encode_utf8(tree_genre.get('tag', ''))
                                          for tree_genre in tree_genres]

        elif media_type == 'music':
            track_title = '%s. %s' % \
                          (str(timings.get('index', 0)).zfill(2),
                           encode_utf8(timings.get('title', i18n('Unknown'))))
            full_data = {
                'TrackNumber': int(timings.get('index', 0)),
                'discnumber': int(timings.get('parentIndex', 0)),
                'title': track_title,
                'rating': float(timings.get('rating', 0)),
                'album': encode_utf8(timings.get('parentTitle',
                                                 tree.get('parentTitle', ''))),
                'artist': encode_utf8(timings.get('grandparentTitle',
                                                  tree.get('grandparentTitle', ''))),
                'duration': int(timings.get('duration', 0)) / 1000,
                'thumbnail': get_thumb_image(context, server, timings)
            }

            extra['album'] = timings.get('parentKey')
            extra['index'] = timings.get('index')

    details = timings.findall('Media')

    media_details_list = []
    for media_details in details:

        try:
            if media_details.get('videoResolution') == 'sd':
                resolution = 'SD'
            elif int(media_details.get('videoResolution', 0)) > 1088:
                resolution = '4K'
            elif int(media_details.get('videoResolution', 0)) >= 1080:
                resolution = 'HD 1080'
            elif int(media_details.get('videoResolution', 0)) >= 720:
                resolution = 'HD 720'
            else:
                resolution = 'SD'
        except ValueError:
            resolution = ''

        media_details_temp = {
            'bitrate': round(float(media_details.get('bitrate', 0)) / 1000, 1),
            'bitDepth': media_details.get('bitDepth', 8),
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
                parts_count += 1
            except:  # pylint: disable=bare-except
                pass

    # if we are deciding internally or forcing an external subs file, then collect the data
    if media_type == 'video' and \
            context.settings.get_setting('streamControl') == StreamControl().PLEX:

        contents = 'all'
        tags = tree.getiterator('Stream')

        for bits in tags:
            stream = dict(bits.items())

            # Audio Streams
            if stream['streamType'] == '2':
                audio_count += 1
                audio_offset += 1
                if stream.get('selected') == '1':
                    LOG.debug('Found preferred audio id: %s ' % stream['id'])
                    audio = stream
                    selected_audio_offset = audio_offset

            # Subtitle Streams
            elif stream['streamType'] == '3':

                if sub_offset == -1:
                    sub_offset = int(stream.get('index', -1))
                elif 0 < int(stream.get('index', -1)) < sub_offset:
                    sub_offset = int(stream.get('index', -1))

                if stream.get('selected') == '1':
                    LOG.debug('Found preferred subtitles id : %s ' % stream['id'])
                    sub_count += 1
                    subtitle = stream
                    if stream.get('key'):
                        subtitle['key'] = server.get_formatted_url(stream['key'])
                    else:
                        selected_sub_offset = int(stream.get('index')) - sub_offset

    else:
        LOG.debug('Stream selection is set OFF')

    stream_data = {
        'contents': contents,  # What type of data we are holding
        'audio': audio,  # Audio data held in a dict
        'audio_count': audio_count,  # Number of audio streams
        'subtitle': subtitle,  # Subtitle data (embedded) held as a dict
        'sub_count': sub_count,  # Number of subtitle streams
        'parts': parts,  # The different media locations
        'parts_count': parts_count,  # Number of media locations
        'media': media,  # Resume/duration data for media
        'details': media_details_list,  # Bitrate, resolution and container for each part
        'sub_offset': selected_sub_offset,  # Stream index for selected subs
        'audio_offset': selected_audio_offset,  # Stream index for select audio
        'full_data': full_data,  # Full metadata extract if requested
        'type': media_type,  # Type of metadata
        'extra': extra
    }  # Extra data

    LOG.debug(stream_data)
    return stream_data


class MediaSelect:
    def __init__(self, context, server, data):
        self.context = context
        self.server = server
        self.data = data

        self.dvd_playback = False

        self._media_index = None
        self._media_url = None

        self.update_selection()

    def update_selection(self):
        self._select_media()
        self._get_media_url()

    @property
    def media_url(self):
        return self._media_url

    @media_url.setter
    def media_url(self, value):
        self._media_url = value

    def _select_media(self):
        count = self.data['parts_count']
        options = self.data['parts']
        details = self.data['details']

        if count > 1:

            dialog_options = []
            dvd_index = []
            index_count = 0
            for items in options:

                if items[1]:
                    name = items[1].split('/')[-1]
                    # name='%s %s %sMbps' % (items[1].split('/')[-1],
                    # details[index_count]['videoResolution'], details[index_count]['bitrate'])
                else:
                    name = '%s %s %sMbps' % (items[0].split('.')[-1],
                                             details[index_count]['videoResolution'],
                                             details[index_count]['bitrate'])

                if self.context.settings.get_setting('forcedvd'):
                    if '.ifo' in name.lower():
                        LOG.debug('Found IFO DVD file in ' + name)
                        name = 'DVD Image'
                        dvd_index.append(index_count)

                dialog_options.append(name)
                index_count += 1

            LOG.debug('Create selection dialog box - we have a decision to make!')
            dialog = xbmcgui.Dialog()
            result = dialog.select(i18n('Select media to play'), dialog_options)
            if result == -1:
                self._media_index = None

            if result in dvd_index:
                LOG.debug('DVD Media selected')
                self.dvd_playback = True

            self._media_index = result

        else:
            if self.context.settings.get_setting('forcedvd'):
                if '.ifo' in options[0]:
                    self.dvd_playback = True

            self._media_index = 0

    def _get_media_url(self):
        if self._media_index is None:
            self.media_url = None
            return

        stream = self.data['parts'][self._media_index][0]
        filename = self.data['parts'][self._media_index][1]

        if self._http(filename, stream):
            return

        file_type = get_file_type(filename)

        if self._auto(filename, file_type, stream):
            return

        if self._smb_afp(filename, file_type):
            return

        LOG.debug('No option detected, streaming is safest to choose')
        self.media_url = self.server.get_formatted_url(stream)

    def _http(self, filename, stream):
        if filename is None or self.context.settings.get_stream() == '1':  # http
            LOG.debug('Selecting stream')
            self.media_url = self.server.get_formatted_url(stream)
            return True

        return False

    def _auto(self, filename, file_type, stream):
        if self.context.settings.get_stream() == '0':  # auto
            # check if the file can be found locally
            if file_type in ['NIX', 'WIN']:
                LOG.debug('Checking for local file')
                if xbmcvfs.exists(filename):
                    LOG.debug('Local file exists')
                    self.media_url = 'file:%s' % filename
                    return True

            LOG.debug('No local file')
            if self.dvd_playback:
                LOG.debug('Forcing SMB for DVD playback')
                self.context.settings.set_stream('2')
            else:
                self.media_url = self.server.get_formatted_url(stream)
                return True

        return False

    def _smb_afp(self, filename, file_type):
        if self.context.settings.get_stream() in ['2', '3']:  # smb / AFP

            filename = unquote(filename)
            if self.context.settings.get_stream() == '2':
                protocol = 'smb'
            else:
                protocol = 'afp'

            LOG.debug('Selecting smb/unc')
            if file_type == 'UNC':
                self.media_url = '%s:%s' % (protocol, filename.replace('\\', '/'))
            else:
                # Might be OSX type, in which case, remove Volumes and replace with server
                server = self.server.get_location().split(':')[0]
                login_string = ''

                if self.context.settings.get_setting('nasoverride'):
                    if self.context.settings.get_setting('nasoverrideip'):
                        server = self.context.settings.get_setting('nasoverrideip')
                        LOG.debug('Overriding server with: %s' % server)

                    if self.context.settings.get_setting('nasuserid'):
                        login_string = '%s:%s@' % (self.context.settings.get_setting('nasuserid'),
                                                   self.context.settings.get_setting('naspass'))
                        LOG.debug('Adding AFP/SMB login info for user: %s' %
                                  self.context.settings.get_setting('nasuserid'))

                if filename.find('Volumes') > 0:
                    self.media_url = '%s:/%s' % \
                                     (protocol, filename.replace('Volumes', login_string + server))
                else:
                    if file_type == 'WIN':
                        self.media_url = ('%s://%s%s/%s' %
                                          (protocol, login_string, server,
                                           filename[3:].replace('\\', '/')))
                    else:
                        # else assume its a file local to server available over smb/samba.
                        # Add server name to file path.
                        self.media_url = '%s://%s%s%s' % (protocol, login_string, server, filename)

            # nas override
            self._nas_override()

            return self.media_url is not None

        return False

    def _nas_override(self):
        if (self.context.settings.get_setting('nasoverride') and
                self.context.settings.get_setting('nasroot')):
            # Re-root the file path
            LOG.debug('Altering path %s so root is: %s' %
                      (self.media_url, self.context.settings.get_setting('nasroot')))
            if '/' + self.context.settings.get_setting('nasroot') + '/' in self.media_url:
                components = self.media_url.split('/')
                index = components.index(self.context.settings.get_setting('nasroot'))
                for _ in list(range(3, index)):
                    components.pop(3)
                self.media_url = '/'.join(components)


def play_playlist(context, server, data):
    LOG.debug('Creating new playlist')
    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()

    tree = get_xml(context, server.get_url_location() + data['extra'].get('album') + '/children')

    if tree is None:
        return

    track_tags = tree.findall('Track')
    for track in track_tags:
        LOG.debug('Adding playlist item')

        url, details = create_track_item(context, server, tree, track, listing=False)
        if CONFIG['kodi_version'] >= 18:
            list_item = xbmcgui.ListItem(details.get('title', i18n('Unknown')), offscreen=True)
        else:
            list_item = xbmcgui.ListItem(details.get('title', i18n('Unknown')))

        thumb = data['full_data'].get('thumbnail', CONFIG['icon'])
        if 'thumbnail' in data['full_data']:
            del data['full_data']['thumbnail']  # not a valid info label

        list_item.setArt({
            'icon': thumb,
            'thumb': thumb
        })
        list_item.setInfo(type='music', infoLabels=details)
        playlist.add(url, list_item)

    index = int(data['extra'].get('index', 0)) - 1
    LOG.debug('Playlist complete.  Starting playback from track %s [playlist index %s] ' %
              (data['extra'].get('index', 0), index))
    xbmc.Player().playselected(index)
