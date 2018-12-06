"""

    This class implements the Plex GDM (G'Day Mate) protocol to discover
    local Plex Media Servers. Also allow client registration into all local
    media servers.

    Copyright (C) 2011-2018 PleXBMC (plugin.video.plexbmc) by hippojay (Dave Hawes-Johnson)
    Copyright (C) 2018 bPlex (plugin.video.bplex)

    This file is part of bPlex (plugin.video.bplex)

    SPDX-License-Identifier: GPL-2.0-or-later
    See LICENSES/GPL-2.0-or-later for more information.
"""

import socket
import struct
import threading
import time

from six.moves.urllib_request import urlopen

from ..common import CONFIG
from ..common import PrintDebug
from ..common import encode_utf8

_log_print = PrintDebug(CONFIG['name'], 'PlexGDM')


class PlexGDM:

    def __init__(self, interface=None):

        self.discover_message = 'M-SEARCH * HTTP/1.0'
        self.client_header = '* HTTP/1.0'
        self.client_data = None
        self.client_id = None

        self.interface = interface

        self._multicast_address = '239.0.0.250'
        self.discover_group = (self._multicast_address, 32414)
        self.client_register_group = (self._multicast_address, 32413)
        self.client_update_port = 32412

        self.server_list = []
        self.discovery_interval = 120

        self._discovery_is_running = False
        self._registration_is_running = False

        self.discovery_complete = False
        self.client_registered = False

        self.discover_t = None
        self.register_t = None

    def client_details(self, c_id, c_name, c_post, c_product, c_version):
        self.client_data = 'Content-Type: plex/media-player\nResource-Identifier: %s\nName: %s\nPort: %s\nProduct: %s\nVersion: %s' % (c_id, c_name, c_post, c_product, c_version)
        self.client_id = c_id

    def get_client_details(self):
        if not self.client_data:
            _log_print.error('Client data has not been initialised.  Please use PlexGDM.client_details()')

        return self.client_data

    def client_update(self):
        update_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

        # Set socket reuse, may not work on all OSs.
        try:
            update_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except:
            pass

        # Attempt to bind to the socket to recieve and send data.  If we can;t do this, then we cannot send registration
        try:
            update_sock.bind(('0.0.0.0', self.client_update_port))
        except:
            _log_print.error('Error: Unable to bind to port [%s] - client will not be registered' % self.client_update_port)
            return

        update_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        update_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(self._multicast_address) + socket.inet_aton('0.0.0.0'))
        # noinspection PyTypeChecker
        update_sock.setblocking(0)
        _log_print.debugplus('Sending registration data: HELLO %s\n%s' % (self.client_header, self.client_data))

        # Send initial client registration
        try:
            update_sock.sendto('HELLO %s\n%s' % (self.client_header, self.client_data), self.client_register_group)
        except:
            _log_print.debug('Error: Unable to send registration message')

        # Now, listen for client discovery requests and respond.
        while self._registration_is_running:
            try:
                data, addr = update_sock.recvfrom(1024)
                _log_print.debug('Received UDP packet from [%s] containing [%s]' % (addr, data.strip()))
            except socket.error:
                pass
            else:
                if 'M-SEARCH * HTTP/1.' in data:
                    _log_print.debug('Detected client discovery request from %s.  Replying' % str(addr))
                    try:
                        update_sock.sendto('HTTP/1.0 200 OK\n%s' % self.client_data, addr)
                    except:
                        _log_print.debug('Error: Unable to send client update message')

                    _log_print.debug('Sending registration data: HTTP/1.0 200 OK\n%s' % self.client_data)
                    self.client_registered = True
            time.sleep(0.5)

        _log_print.debug('Client Update loop stopped')

        # When we are finished, then send a final goodbye message to de-register cleanly.
        _log_print.debug('Sending registration data: BYE %s\n%s' % (self.client_header, self.client_data))
        try:
            update_sock.sendto('BYE %s\n%s' % (self.client_header, self.client_data), self.client_register_group)
        except:
            _log_print.error('Error: Unable to send client update message')

        self.client_registered = False

    def check_client_registration(self):

        if self.client_registered and self.discovery_complete:

            if not self.server_list:
                _log_print.debug('Server list is empty. Unable to check')
                return False

            try:
                media_server = self.server_list[0]['server']
                media_port = self.server_list[0]['port']

                _log_print.debug('Checking server [%s] on port [%s]' % (media_server, media_port))
                f = urlopen('http://%s:%s/clients' % (media_server, media_port))
                client_result = f.read()
                if self.client_id in client_result:
                    _log_print.debug('Client registration successful')
                    _log_print.debug('Client data is: %s' % client_result)
                    return True
                else:
                    _log_print.debug('Client registration not found')
                    _log_print.debug('Client data is: %s' % client_result)

            except:
                _log_print.debug('Unable to check status')
                pass

        return False

    def get_server_list(self):
        return self.server_list

    def discover(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set a timeout so the socket does not block indefinitely
        sock.settimeout(0.6)

        # Set the time-to-live for messages to 1 for local network
        ttl = struct.pack('b', 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

        if self.interface:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.interface))

        return_data = []
        try:
            # Send data to the multicast group
            _log_print.debug('Sending discovery messages: %s' % self.discover_message)
            # noinspection PyUnusedLocal
            sent = sock.sendto(encode_utf8(self.discover_message, py2_only=False), self.discover_group)
            # Look for responses from all recipients
            while True:
                try:
                    data, server = sock.recvfrom(1024)
                    _log_print.debug('Received data from %s:%s' % (server[0], server[1]))
                    _log_print.debug('Data received is:\n %s' % data)
                    return_data.append({'from': server,
                                        'data': data})
                except socket.timeout:
                    break
        finally:
            sock.close()

        self.discovery_complete = True

        discovered_servers = []

        if return_data:

            for response in return_data:
                update = {'server': response.get('from')[0]}

                # Check if we had a positive HTTP response
                if '200 OK' in response.get('data'):

                    update['discovery'] = 'auto'
                    update['owned'] = '1'
                    update['master'] = 1
                    update['role'] = 'master'
                    update['class'] = None

                    for each in response.get('data').split('\n'):

                        if 'Content-Type:' in each:
                            update['content-type'] = each.split(':')[1].strip()
                        elif 'Resource-Identifier:' in each:
                            update['uuid'] = each.split(':')[1].strip()
                        elif 'Name:' in each:
                            update['serverName'] = each.split(':')[1].strip()
                        elif 'Port:' in each:
                            update['port'] = each.split(':')[1].strip()
                        elif 'Updated-At:' in each:
                            update['updated'] = each.split(':')[1].strip()
                        elif 'Version:' in each:
                            update['version'] = each.split(':')[1].strip()
                        elif 'Server-Class:' in each:
                            update['class'] = each.split(':')[1].strip()
                        elif 'Host:' in each:
                            update['host'] = each.split(':')[1].strip()

                discovered_servers.append(update)

        self.server_list = discovered_servers

        if not self.server_list:
            _log_print.debug('No servers have been discovered')
        else:
            _log_print.debug('Number of servers Discovered: %s' % len(self.server_list))
            for items in self.server_list:
                _log_print.debug('Server Discovered: %s' % items['serverName'])

    def set_interval(self, interval):
        self.discovery_interval = interval

    def stop_all(self):
        self.stop_discovery()
        self.stop_registration()

    def stop_discovery(self):
        if self._discovery_is_running:
            _log_print.debug('Discovery shutting down')
            self._discovery_is_running = False
            self.discover_t.join()
            del self.discover_t
        else:
            _log_print.debug('Discovery not running')

    def stop_registration(self):
        if self._registration_is_running:
            _log_print.debug('Registration shutting down')
            self._registration_is_running = False
            self.register_t.join()
            del self.register_t
        else:
            _log_print.debug('Registration not running')

    def run_discovery_loop(self):
        # Run initial discovery
        self.discover()

        discovery_count = 0
        while self._discovery_is_running:
            discovery_count += 1
            if discovery_count > self.discovery_interval:
                self.discover()
                discovery_count = 0
            time.sleep(1)

    def start_discovery(self, daemon=False):
        if not self._discovery_is_running:
            _log_print.debug('Discovery starting up')
            self._discovery_is_running = True
            self.discover_t = threading.Thread(target=self.run_discovery_loop)
            self.discover_t.setDaemon(daemon)
            self.discover_t.start()
        else:
            _log_print.debug('Discovery already running')

    def start_registration(self, daemon=False):
        if not self._registration_is_running:
            _log_print.debug('Registration starting up')
            self._registration_is_running = True
            self.register_t = threading.Thread(target=self.client_update)
            self.register_t.setDaemon(daemon)
            self.register_t.start()
        else:
            _log_print.debug('Registration already running')

    def start_all(self, daemon=False):
        self.start_discovery(daemon)
        self.start_registration(daemon)


# Example usage
if __name__ == '__main__':
    client = PlexGDM()
    client.client_details('Test-Name', 'Test Client', '3003', 'Test-App', '1.2.3')
    client.start_all()
    while not client.discovery_complete:
        _log_print.debug('Waiting for results')
        time.sleep(1)
    time.sleep(20)
    _log_print.debug(client.get_server_list())
    if client.check_client_registration():
        _log_print.debug('Successfully registered')
    else:
        _log_print.debug('Unsuccessfully registered')
    client.stop_all()
