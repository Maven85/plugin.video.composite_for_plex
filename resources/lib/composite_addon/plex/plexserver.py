"""

    Copyright (C) 2011-2018 PleXBMC (plugin.video.plexbmc) by hippojay (Dave Hawes-Johnson)
    Copyright (C) 2018-2019 Composite (plugin.video.composite_for_plex)

    This file is part of Composite (plugin.video.composite_for_plex)

    SPDX-License-Identifier: GPL-2.0-or-later
    See LICENSES/GPL-2.0-or-later for more information.
"""

import base64
import hashlib
import hmac
import threading
import time
import uuid
import xml.etree.ElementTree as ETree

import requests
from six.moves import range
from six.moves.urllib_parse import urlparse
from six.moves.urllib_parse import urlunparse
from six.moves.urllib_parse import parse_qsl
from six.moves.urllib_parse import quote
from six.moves.urllib_parse import quote_plus
from six.moves.urllib_parse import urlencode

from . import plexsection
from ..common import CONFIG
from ..common import PrintDebug
from ..common import encode_utf8
from ..common import settings

log_print = PrintDebug(CONFIG['name'], 'plexserver')

DEFAULT_PORT = '32400'

log_print.debug('Using Requests version for HTTP: %s' % requests.__version__)


class PlexMediaServer:

    def __init__(self, server_uuid=None, name=None, address=None, port=32400, token=None, discovery=None, class_type='primary'):

        self.__revision = CONFIG['required_revision']
        self.protocol = 'https'
        self.uuid = server_uuid
        self.server_name = name
        self.discovery = discovery
        self.local_address = []
        self.external_address = None
        self.external_address_uri = None
        self.local_address_uri = []

        if self.discovery == 'myplex':
            self.external_address = '%s:%s' % (address, port)
            self.external_address_uri = None
        elif self.discovery == 'discovery':
            self.local_address = ['%s:%s' % (address, port)]
            self.local_address_uri = [None]

        self.access_address = '%s:%s' % (address, port)

        self.section_list = []
        self.token = token
        self.owned = 1
        self.master = 1
        self.class_type = class_type
        self.discovered = False
        self.offline = False
        self.user = None
        self.client_id = None
        self.device_name = None
        self.plex_home_enabled = False
        self.best_address = 'address'
        self.connection_test_results = []
        self.plex_identification_header = None
        self.plex_identification_string = None
        self.update_identification()

    def update_identification(self):
        self.plex_identification_header = self.create_plex_identification()
        self.plex_identification_string = self.create_plex_identification_string()

    def get_revision(self):
        return self.__revision

    def get_status(self):
        if self.offline:
            return 'Offline'
        elif self.access_address == self.external_address or \
                (self.external_address_uri and (self.access_address in self.external_address_uri)):
            return 'Remote'
        elif self.access_address in self.local_address:
            return 'Nearby'
        else:
            return 'Unknown'

    def get_details(self):

        return {'serverName': self.server_name,
                'server': self.get_address(),
                'port': self.get_port(),
                'discovery': self.discovery,
                'token': self.token,
                'uuid': self.uuid,
                'owned': self.owned,
                'master': self.master,
                'class': self.class_type}

    def create_plex_identification(self):
        headers = {'X-Plex-Device': CONFIG['device'],
                   'X-Plex-Client-Platform': 'Kodi',
                   'X-Plex-Device-Name': self.get_device_name(),
                   'X-Plex-Language': 'en',
                   'X-Plex-Platform': CONFIG['platform'],
                   'X-Plex-Client-Identifier': self.get_client_identifier(),
                   'X-Plex-Product': CONFIG['name'],
                   'X-Plex-Platform-Version': CONFIG['platform_version'],
                   'X-Plex-Version': '0.0.0a1',
                   'X-Plex-Provides': 'player,controller'}

        if self.token is not None:
            headers['X-Plex-Token'] = self.token

        if self.user is not None:
            headers['X-Plex-User'] = self.user

        return headers

    def create_plex_identification_string(self):
        header = []
        for key, value in self.create_plex_identification().items():
            header.append('%s=%s' % (key, quote(value)))

        return '&'.join(header)

    def get_client_identifier(self):
        if self.client_id is None:
            self.client_id = settings.get_setting('client_id')

            if not self.client_id:
                self.client_id = str(uuid.uuid4())
                settings.set_setting('client_id', self.client_id)

        return self.client_id

    def get_device_name(self):
        if self.device_name is None:
            self.device_name = settings.get_setting('devicename')
        return self.device_name

    def get_uuid(self):
        return self.uuid

    def get_name(self):
        return self.server_name

    def get_address(self):
        return self.access_address.split(':')[0]

    def get_port(self):
        return self.access_address.split(':')[1]

    def get_location(self):
        return self.get_access_address()

    def get_access_address(self):
        return self.access_address

    def get_url_location(self):
        return '%s://%s' % (self.protocol, self.access_address)

    def get_token(self):
        return self.token

    def get_discovery(self):
        return self.discovery

    def is_secure(self):
        if self.protocol == 'https':
            return True
        return False

    def find_address_match(self, ipaddress, port):
        log_print.debug('Checking [%s:%s] against [%s]' % (ipaddress, port, self.access_address))
        if '%s:%s' % (ipaddress, port) == self.access_address:
            return True

        log_print.debug('Checking [%s:%s] against [%s]' % (ipaddress, port, self.external_address))
        if '%s:%s' % (ipaddress, port) == self.external_address:
            return True

        for test_address in self.local_address:
            log_print.debug('Checking [%s:%s] against [%s:%s]' % (ipaddress, port, ipaddress, 32400))
            if '%s:%s' % (ipaddress, port) == '%s:%s' % (test_address, 32400):
                return True

        return False

    def get_user(self):
        return self.user

    def get_owned(self):
        return self.owned

    def get_class(self):
        return self.class_type

    def get_master(self):
        return self.master

    # Set and add functions:

    def set_uuid(self, _uuid):
        self.uuid = _uuid

    def set_owned(self, value):
        self.owned = int(value)

    def set_token(self, value):
        self.token = value
        self.update_identification()

    def set_user(self, value):
        self.user = value
        self.update_identification()

    def set_class(self, value):
        self.class_type = value

    def set_master(self, value):
        self.master = value

    def set_protocol(self, value):
        self.protocol = value

    def set_plex_home_enabled(self):
        self.plex_home_enabled = True

    def set_plex_home_disabled(self):
        self.plex_home_enabled = False

    def add_external_connection(self, address, port, uri):
        self.external_address = '%s:%s' % (address, port)
        self.external_address_uri = uri

    def add_internal_connection(self, address, port, uri):
        if '%s:%s' % (address, port) not in self.local_address:
            self.local_address.append('%s:%s' % (address, port))
            self.local_address_uri.append(uri)

    def add_local_address(self, address):
        self.local_address = address.split(',')

    def connection_test(self, tag, uri):
        log_print.debug('[%s] Head request |%s|' % (self.uuid, uri))
        url_parts = urlparse(uri)
        status_code = requests.codes.not_found
        try:
            response = requests.head(uri, params=self.plex_identification_header, verify=False, timeout=(2, 60))
            status_code = response.status_code
            log_print.debug('[%s] Head status |%s| -> |%s|' % (self.uuid, uri, str(status_code)))
            if status_code == requests.codes.ok or \
                    status_code == requests.codes.unauthorized:
                self.connection_test_results.append((tag, url_parts.scheme, url_parts.netloc, True))
                return
        except:
            pass
        log_print.debug('[%s] Head status |%s| -> |%s|' % (self.uuid, uri, str(status_code)))
        self.connection_test_results.append((tag, url_parts.scheme, url_parts.netloc, False))

    def set_best_address(self, address=''):
        if not address:
            self.connection_test_results = []

        self.offline = False
        self.update_identification()

        use_https = settings.get_setting('secureconn')
        if not use_https:
            self.set_protocol('http')

        external_uri = ''
        internal_address = ''
        external_address = ''

        tags = []
        tested = []
        threads = []
        uris = []

        if address:
            if ':' not in address:
                address = '%s:%s' % (address, DEFAULT_PORT)
        else:
            if self.external_address_uri:
                url_parts = urlparse(self.external_address_uri)
                external_uri = url_parts.netloc
            if self.local_address:
                internal_address = self.local_address[0]
            if self.external_address and not self.external_address.lower().startswith('none:'):
                external_address = self.external_address

            # Ensure that ipaddress comes in an ip:port format
            if external_uri and ':' not in external_uri:
                external_uri = '%s:%s' % (external_uri, DEFAULT_PORT)
            if internal_address and ':' not in internal_address:
                internal_address = '%s:%s' % (internal_address, DEFAULT_PORT)
            if external_address and ':' not in external_address:
                external_address = '%s:%s' % (external_address, DEFAULT_PORT)

        if address:
            if use_https:
                uris.append('%s://%s/' % ('https', address))
                tags.append('user')
            uris.append('%s://%s/' % ('http', address))
            tags.append('user')
        else:
            if external_uri:
                if use_https:
                    uris.append('%s://%s/' % ('https', external_uri))
                    tags.append('external_uri')
                uris.append('%s://%s/' % ('http', external_uri))
                tags.append('external_uri')
            if internal_address:
                if use_https:
                    uris.append('%s://%s/' % ('https', internal_address))
                    tags.append('internal')
                uris.append('%s://%s/' % ('http', internal_address))
                tags.append('internal')
            if external_address:
                if use_https:
                    uris.append('%s://%s/' % ('https', external_address))
                    tags.append('external')
                uris.append('%s://%s/' % ('http', external_address))
                tags.append('external')

        for m in list(range(len(uris))):
            uri = uris[m]
            if uri in tested:
                continue
            tested.append(uri)
            threads.append(threading.Thread(target=self.connection_test, args=(tags[m], uri)))

        _ = [thread.start() for thread in threads]
        _ = [thread.join() for thread in threads]

        log_print.debug('[%s] Server connection test results |%s|' % (self.uuid, str(self.connection_test_results)))

        #  connection preference https (user provided, external uri, internal address, external address)
        if any(c[0] == 'user' and c[1] == 'https' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'user' and c[1] == 'https' and c[3])
            log_print.debug('[%s] Server [%s] not found in existing lists.  selecting as default' % (self.uuid, self.access_address))
        elif any(c[0] == 'external_uri' and c[1] == 'https' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'external_uri' and c[1] == 'https' and c[3])
            log_print.debug('[%s] Server [%s] found in existing external list.  selecting as default' % (self.uuid, self.access_address))
        elif any(c[0] == 'internal' and c[1] == 'https' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'internal' and c[1] == 'https' and c[3])
            log_print.debug('[%s] Server [%s] found on existing internal list.  Selecting as default' % (self.uuid, self.access_address))
        elif any(c[0] == 'external' and c[1] == 'https' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'external' and c[1] == 'https' and c[3])
            log_print.debug('[%s] Server [%s] found in existing external list.  selecting as default' % (self.uuid, self.access_address))

        #  connection preference http (user provided, external uri, internal address, external address)
        elif any(c[0] == 'user' and c[1] == 'http' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'user' and c[1] == 'http' and c[3])
            self.set_protocol('http')
            log_print.debug('[%s] Server [%s] not found in existing lists.  selecting as default' % (self.uuid, self.access_address))
        elif any(c[0] == 'external_uri' and c[1] == 'http' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'external_uri' and c[1] == 'http' and c[3])
            self.set_protocol('http')
            log_print.debug('[%s] Server [%s] found in existing external list.  selecting as default' % (self.uuid, self.access_address))
        elif any(c[0] == 'internal' and c[1] == 'http' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'internal' and c[1] == 'http' and c[3])
            self.set_protocol('http')
            log_print.debug('[%s] Server [%s] found on existing internal list.  Selecting as default' % (self.uuid, self.access_address))
        elif any(c[0] == 'external' and c[1] == 'http' and c[3] for c in self.connection_test_results):
            self.access_address = next(c[2] for c in self.connection_test_results if c[0] == 'external' and c[1] == 'http' and c[3])
            self.set_protocol('http')
            log_print.debug('[%s] Server [%s] found in existing external list.  selecting as default' % (self.uuid, self.access_address))
        else:
            self.offline = True
            log_print.debug('[%s] Server appears to be offline' % self.uuid)

    def talk(self, url='/', refresh=False, method='get'):
        if not self.offline or refresh:
            log_print.debug('URL is: %s using %s' % (url, self.protocol))
            start_time = time.time()

            verify_cert = False if self.protocol == 'http' else settings.get_setting('verify_cert')

            uri = '%s://%s:%s%s' % (self.protocol, self.get_address(), self.get_port(), url)

            try:
                if method == 'get':
                    response = requests.get(uri, params=self.plex_identification_header, verify=verify_cert, timeout=(2, 60))
                elif method == 'put':
                    response = requests.put(uri, params=self.plex_identification_header, verify=verify_cert, timeout=(2, 60))
                elif method == 'delete':
                    response = requests.delete(uri, params=self.plex_identification_header, verify=verify_cert, timeout=(2, 60))
                else:
                    response = None
                self.offline = False
            except requests.exceptions.ConnectionError as e:
                log_print.error('Server: %s is offline or uncontactable. error: %s' % (self.get_address(), e))

                if self.protocol == 'https' and refresh:
                    log_print.debug('Server: %s - switching to http' % self.get_address())
                    self.set_protocol('http')
                    return self.talk(url, refresh, method)
                else:
                    self.offline = True

            except requests.exceptions.ReadTimeout:
                log_print.debug('Server: read timeout for %s on %s ' % (self.get_address(), url))
            else:

                log_print.debug('URL was: %s' % response.url)

                if response.status_code == requests.codes.ok:
                    log_print.debug('Response: 200 OK - Encoding: %s' % response.encoding)
                    data = encode_utf8(response.text, py2_only=False)
                    log_print.debugplus('XML: \n%s' % data)
                    log_print.debug('DOWNLOAD: It took %.2f seconds to retrieve data from %s' % ((time.time() - start_time), self.get_address()))
                    return data
                elif response.status_code == requests.codes.unauthorized:
                    log_print.debug('Response: 401 Unauthorized - Please log into myPlex or check your myPlex password')
                    return '<?xml version="1.0" encoding="UTF-8"?><message status="unauthorized"></message>'
                else:
                    log_print.debug('Unexpected Response: %s ' % response.status_code)

        return '<?xml version="1.0" encoding="UTF-8"?><message status="offline"></message>'

    def tell(self, url, refresh=False):
        return self.talk(url, refresh, method='put')

    def refresh(self):
        data = self.talk(refresh=True)

        tree = ETree.fromstring(data)

        if tree is not None and not (tree.get('status') == 'offline' or tree.get('status') == 'unauthorized'):
            self.server_name = encode_utf8(tree.get('friendlyName'))
            self.uuid = tree.get('machineIdentifier')
            self.owned = 1
            self.master = 1
            self.class_type = tree.get('serverClass', 'primary')
            self.plex_home_enabled = True if tree.get('multiuser') == '1' else False
            self.discovered = True
        else:
            self.discovered = False

    def is_offline(self):
        return self.offline

    def get_sections(self):
        log_print.debug('Returning sections: %s' % self.section_list)
        return self.section_list

    def discover_sections(self):
        for section in self.processed_xml('/library/sections'):
            self.section_list.append(plexsection.PlexSection(section))
        return

    def get_recently_added(self, section=-1, start=0, size=0, hide_watched=True):

        if hide_watched:
            arguments = '?unwatched=1'
        else:
            arguments = '?unwatched=0'

        if section < 0:
            return self.processed_xml('/library/recentlyAdded%s' % arguments)

        if size > 0:
            arguments = '%s&X-Plex-Container-Start=%s&X-Plex-Container-Size=%s' % (arguments, start, size)

        return self.processed_xml('/library/sections/%s/recentlyAdded%s' % (section, arguments))

    def get_ondeck(self, section=-1, start=0, size=0):

        arguments = ''

        if section < 0:
            return self.processed_xml('/library/onDeck%s' % arguments)

        if size > 0:
            arguments = '%s?X-Plex-Container-Start=%s&X-Plex-Container-Size=%s' % (arguments, start, size)

        return self.processed_xml('/library/sections/%s/onDeck%s' % (section, arguments))

    def get_recently_viewed_shows(self, section=-1, start=0, size=0):

        arguments = ''

        if section < 0:
            return self.processed_xml('/library/recentlyViewedShows%s' % arguments)

        if size > 0:
            arguments = '%s?X-Plex-Container-Start=%s&X-Plex-Container-Size=%s' % (arguments, start, size)

        return self.processed_xml('/library/sections/%s/recentlyViewedShows%s' % (section, arguments))

    def get_server_recentlyadded(self):
        return self.get_recently_added(section=-1)

    def get_server_ondeck(self):
        return self.get_ondeck(section=-1)

    def get_channel_recentlyviewed(self):
        return self.processed_xml('/channels/recentlyViewed')

    def processed_xml(self, url):
        if url.startswith('http'):
            log_print.debug('We have been passed a full URL. Parsing out path')
            url_parts = urlparse(url)
            url = url_parts.path

            if url_parts.query:
                url = '%s?%s' % (url, url_parts.query)

        data = self.talk(url)
        start_time = time.time()
        tree = ETree.fromstring(data)
        log_print.debug('PARSE: it took %.2f seconds to parse data from %s' % ((time.time() - start_time), self.get_address()))
        return tree

    def raw_xml(self, url):
        if url.startswith('http'):
            log_print.debug('We have been passed a full URL. Parsing out path')
            url_parts = urlparse(url)
            url = url_parts.path

            if url_parts.query:
                url = '%s?%s' % (url, url_parts.query)

        start_time = time.time()

        data = self.talk(url)

        log_print.debug('PROCESSING: it took %.2f seconds to process data from %s' % ((time.time() - start_time), self.get_address()))
        return data

    def is_owned(self):

        if self.owned == 1 or self.owned == '1':
            return True
        return False

    def is_secondary(self):

        if self.class_type == 'secondary':
            return True
        return False

    def get_formatted_url(self, url, options=None):

        if options is None:
            options = {}

        url_options = self.plex_identification_header
        url_options.update(options)

        if url.startswith('http'):
            url_parts = urlparse(url)
            url = url_parts.path

            if url_parts.query:
                url = url + '?' + url_parts.query

        location = '%s%s' % (self.get_url_location(), url)

        url_parts = urlparse(location)

        query_args = parse_qsl(url_parts.query)
        query_args += url_options.items()

        new_query_args = urlencode(query_args, True)

        return urlunparse((url_parts.scheme, url_parts.netloc, url_parts.path, url_parts.params, new_query_args, url_parts.fragment))

    def get_kodi_header_formatted_url(self, url, options=None):

        if options is None:
            options = {}

        if url.startswith('http'):
            url_parts = urlparse(url)
            url = url_parts.path

            if url_parts.query:
                url = url + '?' + url_parts.query

        location = '%s%s' % (self.get_url_location(), url)

        url_parts = urlparse(location)

        query_args = parse_qsl(url_parts.query)
        query_args += options.items()

        if self.token is not None:
            query_args += {'X-Plex-Token': self.token}.items()

        new_query_args = urlencode(query_args, True)

        return '%s|%s' % (urlunparse((url_parts.scheme, url_parts.netloc, url_parts.path, url_parts.params, new_query_args, url_parts.fragment)), self.plex_identification_string)

    def get_fanart(self, section, width=1280, height=720):

        log_print.debug('Getting fanart for %s' % section.get_title())

        if settings.get_setting('skipimages'):
            return ''

        if section.get_art().startswith('/'):
            if settings.get_setting('fullres_fanart'):
                return self.get_formatted_url(section.get_art())
            else:
                return self.get_formatted_url('/photo/:/transcode?url=%s&width=%s&height=%s' % (quote_plus('http://localhost:32400' + section.get_art()), width, height))

        return section.get_art()

    def stop_transcode_session(self, session):
        self.talk('/video/:/transcode/segmented/stop?session=%s' % session)
        return

    def report_playback_progress(self, media_id, watched_time, state='playing', duration=0):
        try:
            mark_watched = False
            if state == 'stopped' and int((float(watched_time) / float(duration)) * 100) >= 98:
                watched_time = duration
                mark_watched = True

            self.talk('/:/timeline?duration=%s&guid=com.plexapp.plugins.library&key=/library/metadata/%s&ratingKey=%s&state=%s&time=%s' % (duration, media_id, media_id, state, watched_time))

            if mark_watched:
                self.mark_item_watched(media_id)

        except ZeroDivisionError:
            return
        
        return

    def mark_item_watched(self, media_id):
        self.talk('/:/scrobble?key=%s&identifier=com.plexapp.plugins.library' % media_id)
        return

    def mark_item_unwatched(self, media_id):
        self.talk('/:/unscrobble?key=%s&identifier=com.plexapp.plugins.library' % media_id)
        return

    def refresh_section(self, key):
        return self.talk('/library/sections/%s/refresh' % key)

    def get_metadata(self, media_id):
        return self.processed_xml('/library/metadata/%s' % media_id)

    def set_audio_stream(self, part_id, stream_id):
        return self.tell('/library/parts/%s?audioStreamID=%s' % (part_id, stream_id))

    def set_subtitle_stream(self, part_id, stream_id):
        return self.tell('/library/parts/%s?subtitleStreamID=%s' % (part_id, stream_id))

    def delete_metadata(self, media_id):
        return self.talk('/library/metadata/%s' % media_id, method='delete')

    def delete_playlist_item(self, playlist_item_id, path):
        return self.talk('%s/%s' % (path, playlist_item_id), method='delete')

    def get_playlists(self):
        return self.processed_xml('/playlists')

    def get_universal_transcode(self, url, transcode_profile=0):
        # Check for myplex user, which we need to alter to a master server
        log_print.debug('incoming URL is: %s' % url)

        try:
            resolution, bitrate = settings.get_setting('transcode_target_quality_%s' % transcode_profile).split(',')
            subtitle_size = settings.get_setting('transcode_target_sub_size_%s' % transcode_profile).split('.')[0]
            audio_boost = settings.get_setting('transcode_target_audio_size_%s' % transcode_profile).split('.')[0]
        except ValueError:
            resolution, bitrate = settings.get_setting('transcode_target_quality_0').split(',')
            subtitle_size = settings.get_setting('transcode_target_sub_size_0').split('.')[0]
            audio_boost = settings.get_setting('transcode_target_audio_size_0').split('.')[0]

        if bitrate.endswith('Mbps'):
            max_video_bitrate = float(bitrate.strip().split('Mbps')[0]) * 1000
        elif bitrate.endswith('Kbps'):
            max_video_bitrate = bitrate.strip().split('Kbps')[0]
        elif bitrate.endswith('unlimited'):
            max_video_bitrate = 20000
        else:
            max_video_bitrate = 2000  # a catch all amount for missing data

        transcode_request = '/video/:/transcode/universal/start.m3u8?'
        session = str(uuid.uuid4())
        quality = '100'
        transcode_settings = {'protocol': 'hls',
                              'container': 'mpegts',
                              'session': session,
                              'offset': 0,
                              'videoResolution': resolution,
                              'maxVideoBitrate': max_video_bitrate,
                              'videoQuality': quality,
                              'directStream': '1',
                              'directPlay': '0',
                              'subtitleSize': subtitle_size,
                              'audioBoost': audio_boost,
                              'fastSeek': '1',
                              'path': 'http://127.0.0.1:32400%s' % url}

        full_url = '%s%s' % (transcode_request, urlencode(transcode_settings))
        log_print.debug('\nURL: |%s|\nProfile: |[%s] %s@%s (%s/%s)|' %
                        (full_url, str(transcode_profile + 1), resolution, bitrate.strip(), subtitle_size, audio_boost))

        return session, self.get_formatted_url(full_url, options={'X-Plex-Device': 'Plex Home Theater'})

    def get_legacy_transcode(self, media_id, url, identifier=None):

        session = str(uuid.uuid4())

        # Check for myplex user, which we need to alter to a master server
        log_print.debug('Using preferred transcoding server: %s ' % self.get_name())
        log_print.debug('incoming URL is: %s' % url)

        quality = str(float(settings.get_setting('quality_leg')) + 3)
        log_print.debug('Transcode quality is %s' % quality)

        audio_output = settings.get_setting('audiotype')
        if audio_output == '0':
            audio = 'mp3,aac{bitrate:160000}'
        elif audio_output == '1':
            audio = 'ac3{channels:6}'
        elif audio_output == '2':
            audio = 'dts{channels:6}'
        else:
            audio = 'mp3'

        base_capability = 'http-live-streaming,http-mp4-streaming,http-streaming-video,http-streaming-video-1080p,http-mp4-video,http-mp4-video-1080p;videoDecoders=h264{profile:high&resolution:1080&level:51};audioDecoders=%s' % audio
        capability = 'X-Plex-Client-Capabilities=%s' % quote_plus(base_capability)

        transcode_request = '/video/:/transcode/segmented/start.m3u8'
        transcode_settings = {'3g': 0,
                              'offset': 0,
                              'quality': quality,
                              'session': session,
                              'identifier': identifier,
                              'httpCookie': '',
                              'userAgent': '',
                              'ratingKey': media_id,
                              'subtitleSize': settings.get_setting('subSize').split('.')[0],
                              'audioBoost': settings.get_setting('audioSize').split('.')[0],
                              'key': ''}

        if identifier:
            transcode_target = url.split('url=')[1]
            transcode_settings['webkit'] = 1
        else:
            transcode_settings['identifier'] = 'com.plexapp.plugins.library'
            transcode_settings['key'] = quote_plus('%s/library/metadata/%s' % (self.get_url_location(), media_id))
            transcode_target = quote_plus('http://127.0.0.1:32400' + '/' + '/'.join(url.split('/')[3:]))
            log_print.debug('filestream URL is: %s' % transcode_target)

        transcode_request = '%s?url=%s' % (transcode_request, transcode_target)

        for argument, value in transcode_settings.items():
            transcode_request = '%s&%s=%s' % (transcode_request, argument, value)

        log_print.debug('new transcode request is: %s' % transcode_request)

        now = str(float(round(time.time(), 0)))

        msg = transcode_request + '@' + now
        log_print.debug('Message to hash is %s' % msg)

        # These are the DEV API keys - may need to change them on release
        public_key = 'KQMIY6GATPC63AIMC4R2'
        private_key = base64.decodestring('k3U6GLkZOoNIoSgjDshPErvqMIFdE0xMTx8kgsrhnC0=')

        sha256_hash = hmac.new(private_key, msg, digestmod=hashlib.sha256)

        log_print.debug('HMAC after hash is %s' % sha256_hash.hexdigest())

        # Encode the binary hash in base64 for transmission
        token = base64.b64encode(sha256_hash.digest())

        # Send as part of URL to avoid the case sensitive header issue.
        full_url = '%s%s&X-Plex-Access-Key=%s&X-Plex-Access-Time=%s&X-Plex-Access-Code=%s&%s' % (self.get_url_location(), transcode_request, public_key, now, quote_plus(token), capability)

        log_print.debug('Transcoded media location URL: %s' % full_url)

        return session, full_url