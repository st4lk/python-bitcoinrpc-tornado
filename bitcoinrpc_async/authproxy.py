
"""
  Copyright 2014 Alexey Evseev

  Previous copyright, from python-bitcoinrpc
  Copyright 2011 Jeff Garzik

  AuthServiceProxy has the following improvements over python-jsonrpc's
  ServiceProxy class:

  - HTTP connections persist for the life of the AuthServiceProxy object
    (if server supports HTTP/1.1)
  - sends protocol 'version', per JSON-RPC 1.1
  - sends proper, incrementing 'id'
  - sends Basic HTTP authentication headers
  - parses all JSON numbers that look like floats as Decimal
  - uses standard Python json lib

  Previous copyright, from python-jsonrpc/jsonrpc/proxy.py:

  Copyright (c) 2007 Jan-Klaas Kollhof

  This file is part of jsonrpc.

  jsonrpc is free software; you can redistribute it and/or modify
  it under the terms of the GNU Lesser General Public License as published by
  the Free Software Foundation; either version 2.1 of the License, or
  (at your option) any later version.

  This software is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU Lesser General Public License for more details.

  You should have received a copy of the GNU Lesser General Public License
  along with this software; if not, write to the Free Software
  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""

import logging
import base64
import json
import decimal
from datetime import timedelta
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse
from tornado import gen, ioloop
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError

l = logging.getLogger(__name__)

USER_AGENT = "AuthServiceProxy/0.1"
HTTP_TIMEOUT = 30


class JSONRPCException(Exception):
    def __init__(self, rpc_error):
        Exception.__init__(self)
        self.error = rpc_error


class AsyncAuthServiceProxy(object):
    def __init__(self, service_url, service_name=None, timeout=HTTP_TIMEOUT,
                reconnect_timeout=2, reconnect_amount=5):
        """
        :arg string service_url: Format http://{user}:{password}@{host}:{port}
        :arg string service_name: TBD
        :arg string timeout: TBD
        :arg string reconnect_timeout: TBD
        :arg string reconnect_amount: TBD
        """

        self.__service_url = service_url
        self.__reconnect_timeout = reconnect_timeout
        self.__reconnect_amount = reconnect_amount or 1
        self.__service_name = service_name
        self.__url = urlparse.urlparse(service_url)
        self.__http_client = AsyncHTTPClient()
        self.__id_count = 0
        (user, passwd) = (self.__url.username, self.__url.password)
        try:
            user = user.encode('utf8')
        except AttributeError:
            pass
        try:
            passwd = passwd.encode('utf8')
        except AttributeError:
            pass
        authpair = user + b':' + passwd
        self.__auth_header = b'Basic ' + base64.b64encode(authpair)

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            # Python internal stuff
            raise AttributeError
        if self.__service_name is not None:
            name = "%s.%s" % (self.__service_name, name)
        return AsyncAuthServiceProxy(self.__service_url, name)

    @gen.coroutine
    def __call__(self, *args):
        self.__id_count += 1

        postdata = json.dumps({'version': '1.1',
                               'method': self.__service_name,
                               'params': args,
                               'id': self.__id_count})
        headers = {
            'Host': self.__url.hostname,
            'User-Agent': USER_AGENT,
            'Authorization': self.__auth_header,
            'Content-type': 'application/json'
        }

        req = HTTPRequest(url=self.__service_url, method="POST",
            body=postdata,
            headers=headers)

        for i in range(self.__reconnect_amount):
            try:
                if i > 0:
                    l.info("Reconnect try #{0}".format(i+1))
                response = yield self.__http_client.fetch(req)
                break
            except HTTPError:
                err_msg = 'Failed to connect to {0}:{1}'.format(
                    self.__url.hostname, self.__url.port)
                rtm = self.__reconnect_timeout
                if rtm:
                    err_msg += ". Waiting {0} seconds.".format(rtm)
                l.exception(err_msg)
                if rtm:
                    io_loop = ioloop.IOLoop.current()
                    yield gen.Task(io_loop.add_timeout, timedelta(seconds=rtm))
        else:
            l.warning("Reconnect tries exceed.")
        response = json.loads(response.body)

        if response['error'] is not None:
            raise JSONRPCException(response['error'])
        elif 'result' not in response:
            raise JSONRPCException({
                'code': -343, 'message': 'missing JSON-RPC result'})
        else:
            raise gen.Return(response['result'])

    # def _batch(self, rpc_call_list):
    #     postdata = json.dumps(list(rpc_call_list))
    #     self.__conn.request('POST', self.__url.path, postdata,
    #                         {'Host': self.__url.hostname,
    #                          'User-Agent': USER_AGENT,
    #                          'Authorization': self.__auth_header,
    #                          'Content-type': 'application/json'})

    #     return self._get_response()

    # def _get_response(self):
    #     for i in range(10):
    #         try:
    #             http_response = self.__conn.getresponse()
    #             break
    #         except socket.error:
    #             l.exception("Got error")
    #     if http_response is None:
    #         raise JSONRPCException({
    #             'code': -342, 'message': 'missing HTTP response from server'})

    #     return json.loads(http_response.read().decode('utf8'),
    #                       parse_float=decimal.Decimal)
