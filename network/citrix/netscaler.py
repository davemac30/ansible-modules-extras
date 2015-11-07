#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module to manage Citrix NetScaler entities
(c) 2013, Nandor Sivok <nandor@gawker.com>

This file is part of Ansible

Ansible is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Ansible is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
"""

DOCUMENTATION = '''
---
module: netscaler
version_added: "1.1"
short_description: Manages Citrix NetScaler entities
description:
     - Manages Citrix NetScaler server and service entities.
options:
  nsc_host:
    description:
      - hostname or ip of your netscaler
    required: true
    default: null
    aliases: []
  nsc_protocol:
    description:
      - protocol used to access netscaler
    required: false
    default: https
    aliases: []
  user:
    description:
      - username
    required: true
    default: null
    aliases: []
  password:
    description:
      - password
    required: true
    default: null
    aliases: []
  action:
    description:
      - the action you want to perform on the entity
    required: false
    default: disable
    choices: ["enable", "disable"]
    aliases: []
  name:
    description:
      - name of the entity
    required: true
    default: hostname
    aliases: []
  type:
    description:
      - type of the entity
    required: false
    default: server
    choices: ["server", "service"]
    aliases: []
  validate_certs:
    description:
      - If C(no), SSL certificates for the target url will not be validated. This should only be used
        on personally controlled sites using self-signed certificates.
    required: false
    default: 'yes'
    choices: ['yes', 'no']
  partition:
    description:
      - Admin partitition containing the resource to be managed. If NetScaler is partitioned
        and partition not specified then user's default partition will be assumed.
    required: false

requirements: []
author: "Nandor Sivok (@dominis)"
'''

EXAMPLES = '''
# Disable the server
ansible host -m netscaler -a "nsc_host=nsc.example.com user=apiuser password=apipass"

# Enable the server
ansible host -m netscaler -a "nsc_host=nsc.example.com user=apiuser password=apipass action=enable"

# Disable the service local:8080
ansible host -m netscaler -a "nsc_host=nsc.example.com user=apiuser password=apipass name=local:8080 type=service action=disable"
'''

import urllib
from cookielib import CookieJar

class netscaler(object):

    _nitro_base_url = '/nitro/v1/'

    def __init__(self, module):

        self.changed = False
        self.urlbase = '%s://%s/nitro/v1' % (module.params['nsc_protocol'], module.params['nsc_host'])

        # the opener in ansible.module_utils.urls doesn't support cookies,
        # so that's no good here.
        cookie_handler = urllib2.HTTPCookieProcessor(CookieJar())

        # if possible use the built-in ssl support from urllib2, otherwise use
        # SSLValidationHandler from ansible.module_utils.urls
        https_handler = urllib2.HTTPSHandler()
        if sys.version_info >= (2, 7, 9):
            if not module.params['validate_certs']:
                https_handler = urllib2.HTTPSHandler(context = ssl._create_unverified_context())
        else:
            if module.params['validate_certs']:
                https_handler = SSLValidationHandler(module.params['nsc_host'], 443)

        self._opener = urllib2.build_opener(cookie_handler, https_handler)

    def api_get(self, api):
        req = urllib2.Request('%s/%s/%s/%s' % (self.urlbase, api, self._type, self._name))
        return self._opener.open(req)

    def api_post(self, api, data):
        headers = { 'Content-Type' : 'application/x-www-form-urlencoded' }
        form_data = urllib.urlencode({ 'object': json.dumps(data) })
        req = urllib2.Request('%s/%s' % (self.urlbase, api), headers = headers, data = form_data)
        return self._opener.open(req)

    def login(self):
        self.api_post('config', { 'login': { 'username': self._nsc_user, "password": self._nsc_pass, "timeout":5 } })

    def logout(self):
        self.api_post('config', { 'logout':{} })

    def do_server(self, action):
        result = {}
        request_data = {
            "params": {"action": action},
            self._type: {"name": self._name}
        }            
        r = json.load(self.api_get('config'))
        
        if r[self._type][0]['state'] != action.upper() + 'D':
            result = json.load(self.api_post('config', request_data))
            self.changed = True
        return result

    def do_service(self, action):
        result = {}
        request_data = {
            "params": {"action": action},
            self._type: {"name": self._name}
        }            
        r = json.load(self.api_get('config'))
        if r[self._type][0]['svrstate'] == 'OUT OF SERVICE':
            if action == 'enable':
                result = json.load(self.api_post('config', request_data))
                self.changed = True
        else:
            if action == 'disable':
                result = json.load(self.api_post('config', request_data))
                self.changed = True
        return result

    def do(self, action):

        # this, rather unusual, default result is an attempt to maintain
        # consistency with the previous version's behaviour
        result = { 'errorcode': 0, 'message': 'Done', 'severity': 'NONE' }

        self.login()

        if self._partition:
            request_data = {
                'nspartition': { 'partitionname': self._partition },
                'params': { 'action': 'switch' }
            }
            self.api_post('config', request_data)

        # call the appropriate 'do_' submethod
        result.update(getattr(self, 'do_%s' % self._type)(action))

        self.logout()
        return result

def core(module):
    n = netscaler(module)
    n._nsc_host = module.params.get('nsc_host')
    n._nsc_user = module.params.get('user')
    n._nsc_pass = module.params.get('password')
    n._nsc_protocol = module.params.get('nsc_protocol')
    n._name = module.params.get('name')
    n._type = module.params.get('type')
    n._partition = module.params.get('partition')
    action = module.params.get('action')

    r = n.do(action)
    r['changed'] = n.changed

    return r['errorcode'], r


def main():

    module = AnsibleModule(
        argument_spec = dict(
            nsc_host = dict(required=True),
            nsc_protocol = dict(default='https'),
            user = dict(required=True),
            password = dict(required=True),
            action = dict(default='enable', choices=['enable','disable']),
            name = dict(default=socket.gethostname()),
            type = dict(default='server', choices=['service', 'server']),
            validate_certs=dict(default='yes', type='bool'),
            partition=dict(required=False)
        )
    )

    rc = 0
    try:
        rc, result = core(module)
    except urllib2.HTTPError as he:
        module.fail_json(msg = he.reason, code = he.code, ns_api_error = json.loads(he.read()))
    except Exception, e:
        module.fail_json(msg=str(e))

    if rc != 0:
        module.fail_json(rc=rc, msg=result)
    else:
        module.exit_json(**result)


# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.urls import *
main()
