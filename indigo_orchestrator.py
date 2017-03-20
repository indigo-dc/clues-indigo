#!/usr/bin/env python
#
# CLUES - Cluster Energy Saving System
# Copyright (C) 2015 - GRyCAP - Universitat Politecnica de Valencia
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
Created on 26/1/2015

@author: micafer
'''

import re
import yaml
import time
import json
import logging
import base64
import requests

import cpyutils.db
import cpyutils.config
import cpyutils.eventloop
from clueslib.node import Node
from clueslib.platform import PowerManager

_LOGGER = logging.getLogger("[PLUGIN-INDIGO-ORCHESTRATOR]")


class powermanager(PowerManager):

    POWER_ON = 1
    POWER_OFF = 0

    class JWT(object):

        @staticmethod
        def b64d(b):
            """Decode some base64-encoded bytes.

            Raises Exception if the string contains invalid characters or padding.

            :param b: bytes
            """

            cb = b.rstrip(b"=")  # shouldn't but there you are

            # Python's base64 functions ignore invalid characters, so we need to
            # check for them explicitly.
            b64_re = re.compile(b"^[A-Za-z0-9_-]*$")
            if not b64_re.match(cb):
                raise Exception(cb, "base64-encoded data contains illegal characters")

            if cb == b:
                b = powermanager.JWT.add_padding(b)

            return base64.urlsafe_b64decode(b)

        @staticmethod
        def add_padding(b):
            # add padding chars
            m = len(b) % 4
            if m == 1:
                # NOTE: for some reason b64decode raises *TypeError* if the
                # padding is incorrect.
                raise Exception(b, "incorrect padding")
            elif m == 2:
                b += b"=="
            elif m == 3:
                b += b"="
            return b

        @staticmethod
        def get_info(token):
            """
            Unpacks a JWT into its parts and base64 decodes the parts
            individually, returning the part 1 json decoded, where the
            token info is stored.

            :param token: The JWT token
            """
            part = tuple(str(token).split(b"."))
            part = [powermanager.JWT.b64d(p) for p in part]
            return json.loads(part[1])

    class Task:

        def __init__(self, operation, nname):
            self.operation = int(operation)
            self.nname = str(nname)

        def __cmp__(self, other):
            if self.nname == other.nname and self.operation == other.operation:
                return 0
            else:
                return -1

        def __str__(self):
            return "%s on %s" % ("Power On" if self.operation == powermanager.POWER_ON else "Power Off", self.nname)

    class VM_Node:

        def __init__(self, vm_id):
            self.vm_id = vm_id
            self.timestamp_recovered = 0
            self.timestamp_created = self.timestamp_seen = cpyutils.eventloop.now()

        def seen(self):
            self.timestamp_seen = cpyutils.eventloop.now()
            # _LOGGER.debug("seen %s" % self.vm_id)

        def recovered(self):
            self.timestamp_recovered = cpyutils.eventloop.now()

    def __init__(self):
        #
        # NOTE: This fragment provides the support for global config files. It is a bit awful.
        #       I do not like it because it is like having global vars. But it is managed in
        #       this way for the sake of using configuration files
        #
        config_indigo = cpyutils.config.Configuration(
            "INDIGO ORCHESTRATOR",
            {
                "INDIGO_ORCHESTRATOR_URL": "http://172.30.15.43:8080",
                "INDIGO_ORCHESTRATOR_DEPLOY_ID": None,
                "INDIGO_ORCHESTRATOR_MAX_INSTANCES": 0,
                "INDIGO_ORCHESTRATOR_FORGET_MISSING_VMS": 30,
                "INDIGO_ORCHESTRATOR_DROP_FAILING_VMS": 30,
                "INDIGO_ORCHESTRATOR_DB_CONNECTION_STRING": "sqlite:///var/lib/clues2/clues.db",
                "INDIGO_ORCHESTRATOR_PAGE_SIZE": 20,
                "INDIGO_ORCHESTRATOR_AUTH_DATA": "",
                "INDIGO_ORCHESTRATOR_CLIENT_ID": "",
                "INDIGO_ORCHESTRATOR_CLIENT_SECRET": ""
            }
        )

        self._INDIGO_ORCHESTRATOR_URL = config_indigo.INDIGO_ORCHESTRATOR_URL
        self._INDIGO_ORCHESTRATOR_DEPLOY_ID = config_indigo.INDIGO_ORCHESTRATOR_DEPLOY_ID
        self._INDIGO_ORCHESTRATOR_MAX_INSTANCES = config_indigo.INDIGO_ORCHESTRATOR_MAX_INSTANCES
        self._INDIGO_ORCHESTRATOR_FORGET_MISSING_VMS = config_indigo.INDIGO_ORCHESTRATOR_FORGET_MISSING_VMS
        self._INDIGO_ORCHESTRATOR_DROP_FAILING_VMS = config_indigo.INDIGO_ORCHESTRATOR_DROP_FAILING_VMS
        self._INDIGO_ORCHESTRATOR_PAGE_SIZE = config_indigo.INDIGO_ORCHESTRATOR_PAGE_SIZE
        self._auth_data = config_indigo.INDIGO_ORCHESTRATOR_AUTH_DATA
        self._client_id = config_indigo.INDIGO_ORCHESTRATOR_CLIENT_ID
        self._client_secret = config_indigo.INDIGO_ORCHESTRATOR_CLIENT_SECRET
        self._refresh_token = None

        self._refresh_time_diff = 300
        self._inf_id = None
        self._master_nodes_ids = []
        # Structure for the recovery of nodes
        self._db = cpyutils.db.DB.create_from_string(
            config_indigo.INDIGO_ORCHESTRATOR_DB_CONNECTION_STRING)
        self._create_db()
        self._mvs_seen = self._load_mvs_seen()
        self._pending_tasks = self._load_pending_tasks()

        new_token = self._load_token()
        if new_token:
            self._auth_data = new_token

        # Initially we get the refresh token and a new access token
        self._get_refresh_token()

    def _save_token(self):
        try:
            self._db.sql_query("DELETE FROM orchestrator_token", True)
            self._db.sql_query("INSERT into orchestrator_token values ('%s', 0)" % self._auth_data, True)
        except:
            _LOGGER.exception(
                "Error trying to save INDIGO orchestrator token data.")

    def _load_token(self):
        try:
            result, _, rows = self._db.sql_query("select * from orchestrator_token")
            if result:
                for (token, _) in rows:
                    return token
            else:
                _LOGGER.error(
                    "Error trying to load INDIGO orchestrator token data.")
        except:
            _LOGGER.exception(
                "Error trying to load INDIGO orchestrator tasks data.")

        return None

    def _get_refresh_token(self):
        """
        Get the access_token and refresj_token of the plugin client
        """
        if self._auth_data and self._client_id and self._client_secret:
            try:
                decoded_token = powermanager.JWT().get_info(self._auth_data)
                token_scopes = "openid profile offline_access"
                url = "%s/token" % decoded_token['iss']
                payload = ("client_id=%s&client_secret=%s&grant_type=urn%%3Aietf%%3Aparams%%3Aoauth%%3Agrant-type%%3A"
                           "token-exchange&subject_token=%s&scope=%s") % (self._client_id, self._client_secret,
                                                                          self._auth_data, token_scopes)
                headers = {'content-type': 'application/x-www-form-urlencoded'}
                resp = requests.request("POST", url, data=payload, headers=headers, verify=False)
                if resp.status_code == 200:
                    info = resp.json()
                    self._refresh_token = info["refresh_token"]
                    self._auth_data = info["access_token"]
                    self._save_token()
                    _LOGGER.debug("Refresh token successfully obtained")
                    return True
                else:
                    _LOGGER.error("Error getting refresh token: Code %d. Message: %s" % (resp.status_code, resp.text))
                    return False
            except:
                _LOGGER.error("Error getting refresh token")
                return False
        else:
            _LOGGER.error("Error getting refresh token: No auth_data or client info provided.")
            return False

    def _refresh_access_token(self):
        """
        Refresh the current access_token
        """
        if self._refresh_token and self._client_id and self._client_secret:
            try:
                decoded_token = powermanager.JWT().get_info(self._auth_data)
                token_scopes = "openid profile offline_access"
                url = "%s/token" % decoded_token['iss']
                payload = ("client_id=%s&client_secret=%s&grant_type=refresh_token&scope=%s"
                           "&refresh_token=%s") % (self._client_id, self._client_secret,
                                                   token_scopes, self._refresh_token)
                headers = {'content-type': 'application/x-www-form-urlencoded'}
                resp = requests.request("POST", url, data=payload, headers=headers, verify=False)
                if resp.status_code == 200:
                    info = resp.json()
                    self._auth_data = info["access_token"]
                    self._save_token()
                    _LOGGER.debug("Access token successfully refreshed.")
                    return True
                else:
                    _LOGGER.error("Error refreshing access token: Code %d. Message: %s" % (resp.status_code, resp.text))
                    return False
            except:
                _LOGGER.error("Error refreshing access token.")
                return False
        else:
            _LOGGER.error("Error refreshing access token: No client info provided.")
            return False

    def _is_access_token_to_expire(self):
        """
        Check if the current access token is to expire
        """
        if self._auth_data:
            try:
                decoded_token = powermanager.JWT().get_info(self._auth_data)
                now = int(time.time())
                expires = int(decoded_token['exp'])
                _LOGGER.debug("The access token is valid for %s seconds." % (expires - now))
                if expires - now < self._refresh_time_diff:
                    return True
                else:
                    return False
            except:
                _LOGGER.exception("Error getting token info.")
                return False
        else:
            _LOGGER.error("No access token to check expiration.")
            return False

    def _get_auth_header(self):
        auth_header = None
        if self._auth_data:
            auth_header = {'Authorization': 'Bearer %s' % self._auth_data}

        return auth_header

    def _get_inf_id(self):
        return self._INDIGO_ORCHESTRATOR_DEPLOY_ID

    def _get_nodename_from_uuid(self, uuid):
        for node_name, vm in self._mvs_seen.items():
            if vm.vm_id == uuid:
                return node_name
        return None

    def _get_uuid_from_nodename(self, nodename):
        for node_name, vm in self._mvs_seen.items():
            if node_name == nodename:
                return vm.vm_id
        return None

    def _get_master_node_id(self, resources):
        if not self._master_nodes_ids:
            older_resources = []
            # if this plugin is used after year 5000 please change this
            last_time = time.strptime("5000-12-01T00:00", "%Y-%m-%dT%H:%M")
            for resource in resources:
                # date format: 2016-02-04T10:43+0000
                creation_time = time.strptime(resource['creationTime'][:-5], "%Y-%m-%dT%H:%M")
                if creation_time <= last_time:
                    last_time = creation_time
                    older_resources.append(resource)

            self._master_nodes_ids = [res['uuid'] for res in older_resources]

        return self._master_nodes_ids

    def _get_resources_page(self, page=0):
        inf_id = self._get_inf_id()
        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/json', 'Connection': 'close'}
        auth = self._get_auth_header()
        if auth:
            headers.update(auth)
        url = "%s/%s" % (self._INDIGO_ORCHESTRATOR_URL, "deployments/%s/resources?size=%d&page=%d" %
                         (inf_id, self._INDIGO_ORCHESTRATOR_PAGE_SIZE, page))
        resp = requests.request("GET", url, headers=headers)
        return resp.status_code, resp.text

    def _get_resources(self):
        try:
            status, output = self._get_resources_page()

            resources = []
            if status != 200:
                _LOGGER.error("ERROR getting deployment info: %s" %
                              str(output))
            else:
                res = json.loads(output)
                if 'content' in res:
                    resources.extend(res['content'])

                if 'page' in res and res['page']['totalPages'] > 1:
                    for page in range(1, res['page']['totalPages']):
                        status, output = self._get_resources_page(page)

                        if status != 200:
                            _LOGGER.error(
                                "ERROR getting deployment info: %s, page %d" % (str(output), page))
                        else:
                            res = json.loads(output)
                            if 'content' in res:
                                resources.extend(res['content'])

                return [resource for resource in resources if resource['toscaNodeType'] == "tosca.nodes.indigo.Compute"]

            return resources
        except:
            _LOGGER.exception("ERROR getting deployment info.")
            return []

    def _get_vms(self):
        now = cpyutils.eventloop.now()
        resources = self._get_resources()

        if not resources:
            _LOGGER.warning("No resources obtained from orchestrator.")
        else:
            for resource in resources:
                if resource['uuid'] not in self._get_master_node_id(resources):
                    vm = self.VM_Node(resource['uuid'])
                    status = resource['state']
                    # Possible status (TOSCA node status)
                    # initial, creating, created, configuring, configured,
                    # starting, started, stopping, deleting, error

                    if status in ["ERROR"]:
                        # This VM is in a "terminal" state remove it from the
                        # infrastructure
                        msg = ""
                        if 'statusReason' in resource:
                            msg = resource['statusReason']
                        _LOGGER.error("VM with id %s is in state: %s, msg: %s. Powering off." % (
                            vm.vm_id, status, msg))
                        self._add_task(self.POWER_OFF, vm.vm_id)
                    elif status in ["DELETING"]:
                        _LOGGER.debug("VM with id %s is in state: %s. Ignoring." % (
                            vm.vm_id, status))
                    else:
                        # The name of the associated node has been stored in VM
                        # launch
                        node_name = self._get_nodename_from_uuid(vm.vm_id)

                        if not node_name:
                            _LOGGER.error(
                                "No node name obtained for VM ID: %s" % vm.vm_id)
                            self._add_task(self.POWER_OFF, vm.vm_id)
                        else:
                            # The VM is OK
                            if node_name not in self._mvs_seen:
                                # This must never happen but ...
                                _LOGGER.warning(
                                    "Node name %s not in the list of seen VMs." % node_name)
                                self._mvs_seen[node_name] = vm
                            else:
                                self._mvs_seen[node_name].seen()

        # from the nodes that we have powered on, check which of them are still
        # running
        for nname, node in self._mvs_seen.items():
            if (now - node.timestamp_seen) > self._INDIGO_ORCHESTRATOR_FORGET_MISSING_VMS:
                _LOGGER.debug(
                    "vm %s is not seen for a while... let's forget it" % nname)
                self._delete_mvs_seen(nname)

        return self._mvs_seen

    def _recover_ids(self, nodenames):
        for nodename in nodenames:
            self.recover(nodename)

    def recover(self, nname):
        success, nname = self.power_off(nname)
        if success:
            return Node.OFF

        return False

    def _add_task(self, operation, nname):
        task = self.Task(operation, nname)
        if task not in self._pending_tasks:
            self._pending_tasks.append(task)
            try:
                self._db.sql_query(
                    "INSERT INTO orchestrator_tasks VALUES ('%s', %d)" % (nname, operation), True)
            except:
                _LOGGER.exception(
                    "Error trying to save INDIGO orchestrator tasks data.")

    def _delete_task(self, task):
        try:
            self._db.sql_query(
                "DELETE FROM orchestrator_tasks WHERE node_name = '%s' and operation = %d" % (task.nname,
                                                                                              task.operation), True)
        except:
            _LOGGER.exception(
                "Error trying to save INDIGO orchestrator tasks data.")

    def _get_node_info(self, monitoring_info, nname):
        for node in monitoring_info.nodelist:
            if node.name == nname:
                return node
        return None

    def _process_pending_tasks(self, monitoring_info):
        if not self._pending_tasks:
            return

        status = self._get_deployment_status()
        # Possible status
        # CREATE_IN_PROGRESS, CREATE_COMPLETE, CREATE_FAILED, UPDATE_IN_PROGRESS, UPDATE_COMPLETE
        # UPDATE_FAILED, DELETE_IN_PROGRESS, DELETE_COMPLETE, DELETE_FAILED, UNKNOWN
        if status in ["CREATE_IN_PROGRESS", "UPDATE_IN_PROGRESS", "DELETE_IN_PROGRESS"]:
            _LOGGER.debug("The deployment is in an unmodifiable state do not process tasks.")
            return

        _LOGGER.debug("Processing pending tasks: %s." % self._pending_tasks)
        task = self._pending_tasks[0]

        if task.operation == self.POWER_ON:
            task = self._pending_tasks.pop(0)
            self._delete_task(task)
            if not self._power_on(task.nname):
                _LOGGER.error("Error processing task: %s" % task)
            else:
                _LOGGER.debug("Task %s correctly processed." % task)
        elif task.operation == self.POWER_OFF:
            tasks = []
            while self._pending_tasks:
                if task.operation == self.POWER_OFF:
                    self._pending_tasks.pop(0)
                    self._delete_task(task)
                    node_info = self._get_node_info(monitoring_info, task.nname)
                    if not node_info:
                        _LOGGER.warn("Trying to poweroff node %s that is not in then monitoring info. "
                                     "Discard poweroff operation." % task.nname)
                    else:
                        if node_info.state != Node.USED:
                            tasks.append(task.nname)
                        else:
                            _LOGGER.debug("Node %s is currently used, discard poweroff operation." % task.nname)
                else:
                    break
                task = self._pending_tasks[0]
            if not self._power_off(tasks):
                _LOGGER.error("Error processing tasks: %s" % ",".join(tasks))
            else:
                _LOGGER.debug("Tasks PowerOff %s correctly processed." % ",".join(tasks))
        else:
            # it must not happen ...
            _LOGGER.error("Operation %s unknown." % task.operation)

    def lifecycle(self):
        try:
            # First check if we have to refresh de access token
            if self._is_access_token_to_expire():
                self._refresh_access_token()

            monitoring_info = self._clues_daemon.get_monitoring_info()
            now = cpyutils.eventloop.now()

            vms = self._get_vms()

            recover = []
            # To store the name of the nodes to use it in the third case
            node_names = []

            # Two cases: (1) a VM that is on in the monitoring info, but it is
            # not seen in IM; and (2) a VM that is off in the monitoring info,
            # but it is seen in IM
            for node in monitoring_info.nodelist:
                node_names.append(node.name)
                if node.enabled:
                    if node.state in [Node.OFF, Node.OFF_ERR, Node.UNKNOWN]:
                        if self._INDIGO_ORCHESTRATOR_DROP_FAILING_VMS > 0:
                            if node.name in vms:
                                vm = vms[node.name]
                                time_off = now - node.timestamp_state
                                time_recovered = now - vm.timestamp_recovered
                                _LOGGER.warning("node %s has a VM running but it is OFF or UNKNOWN in the monitoring "
                                                "system since %d seconds" % (node.name, time_off))
                                if time_off > self._INDIGO_ORCHESTRATOR_DROP_FAILING_VMS:
                                    if time_recovered > self._INDIGO_ORCHESTRATOR_DROP_FAILING_VMS:
                                        _LOGGER.warning(
                                            "Trying to recover it (state: %s)" % node.state)
                                        vm.recovered()
                                        recover.append(node.name)
                                    else:
                                        _LOGGER.debug("node %s has been recently recovered %d seconds ago. Do not "
                                                      "recover it yet." % (node.name, time_recovered))
                    else:
                        if node.name not in vms:
                            # This may happen because it is launched by hand
                            # using other credentials than those for the user
                            # used for IM (and he cannot manage the VMS)
                            _LOGGER.warning("node %s is detected by the monitoring system, but there is not any VM "
                                            "associated to it (there are any problem connecting with the "
                                            "Orchestrator?)" % node.name)

            # A third case: a VM that it is seen in Orchestrator but does not correspond to
            # any node in the monitoring info
            # This is a strange case but we assure not to have uncontrolled VMs
            for name in vms:
                vm = vms[name]
                if name not in node_names:
                    _LOGGER.warning("VM with name %s is detected by the Orchestrator but it does not exist "
                                    "in the monitoring system... recovering it.)" % name)
                    vm.recovered()
                    recover.append(name)

            self._recover_ids(recover)

            self._process_pending_tasks(monitoring_info)
        except:
            _LOGGER.exception(
                "Error executing lifecycle of INDIGO Orchestrator PowerManager.")

        return PowerManager.lifecycle(self)

    def _create_db(self):
        try:
            result, _, _ = self._db.sql_query("CREATE TABLE IF NOT EXISTS orchestrator_vms(node_name varchar(128) "
                                              "PRIMARY KEY, uuid varchar(128))", True)
            result, _, _ = self._db.sql_query("CREATE TABLE IF NOT EXISTS orchestrator_tasks(node_name varchar(128), "
                                              "operation int)", True)
            result, _, _ = self._db.sql_query("CREATE TABLE IF NOT EXISTS orchestrator_token(token BLOB, "
                                              "num int)", True)
        except:
            _LOGGER.exception(
                "Error creating INDIGO orchestrator plugin DB. The data persistence will not work!")
            result = False
        return result

    def _delete_mvs_seen(self, nname):
        if nname in self._mvs_seen:
            del self._mvs_seen[nname]
        try:
            self._db.sql_query(
                "DELETE FROM orchestrator_vms WHERE node_name = '%s'" % nname, True)
        except:
            _LOGGER.exception(
                "Error trying to save INDIGO orchestrator plugin data.")

    def _add_mvs_seen(self, nname, vm):
        self._mvs_seen[nname] = vm
        try:
            self._db.sql_query(
                "INSERT INTO orchestrator_vms VALUES ('%s', '%s')" % (nname, vm.vm_id), True)
        except:
            _LOGGER.exception(
                "Error trying to save INDIGO orchestrator plugin data.")

    def _load_mvs_seen(self):
        res = {}
        try:
            result, _, rows = self._db.sql_query(
                "select * from orchestrator_vms")
            if result:
                for (node_name, uuid) in rows:
                    res[node_name] = self.VM_Node(uuid)
            else:
                _LOGGER.error(
                    "Error trying to load INDIGO orchestrator plugin data.")
        except:
            _LOGGER.exception(
                "Error trying to load INDIGO orchestrator plugin data.")

        return res

    def _load_pending_tasks(self):
        res = []
        try:
            result, _, rows = self._db.sql_query(
                "select * from orchestrator_tasks")
            if result:
                for (nname, operation) in rows:
                    res.append(self.Task(operation, nname))
            else:
                _LOGGER.error(
                    "Error trying to load INDIGO orchestrator tasks data.")
        except:
            _LOGGER.exception(
                "Error trying to load INDIGO orchestrator tasks data.")

        return res

    def _get_deployment_status(self):
        inf_id = self._get_inf_id()
        headers = {'Accept': 'application/json', 'Connection': 'close'}
        auth = self._get_auth_header()
        if auth:
            headers.update(auth)
        url = "%s/%s" % (self._INDIGO_ORCHESTRATOR_URL, "deployments/%s" % inf_id)
        resp = requests.request("GET", url, headers=headers)

        if resp.status_code != 200:
            _LOGGER.error("ERROR getting deployment status: %s (%d)" %
                          (str(resp.text), resp.status_code))
            return None
        else:
            deployment_info = json.loads(resp.text)
            _LOGGER.debug("Deployment in status: %s" % deployment_info['status'])
            return deployment_info['status']

    def _modify_deployment(self, vms, remove_nodes=None, add_nodes=None):
        inf_id = self._get_inf_id()

        headers = {'Accept': 'application/json', 'Connection': 'close', 'Content-Type': 'application/json'}
        auth = self._get_auth_header()
        if auth:
            headers.update(auth)

        template = self._get_template(len(vms), remove_nodes, add_nodes)
        _LOGGER.debug("template: " + template)
        body = '{ "template": "%s" }' % template.replace('"', '\\"').replace('\n', '\\n')

        url = "%s/%s" % (self._INDIGO_ORCHESTRATOR_URL, "deployments/%s" % inf_id)
        resp = requests.request("PUT", url, headers=headers, data=body)
        return resp.status_code, resp.text

    def power_on(self, nname):
        vms = self._mvs_seen
        if len(vms) >= self._INDIGO_ORCHESTRATOR_MAX_INSTANCES:
            _LOGGER.debug(
                "There are %d VMs running, we are at the maximum number. Do not power on %s." % (len(vms), nname))
            return False, nname

        if nname in vms:
            _LOGGER.warning("Trying to launch an existing node %s. Ignoring it." % nname)
            return True, nname

        self._add_task(self.POWER_ON, nname)
        return True, nname

    def _power_on(self, node_name):
        try:
            vms = self._mvs_seen

            resp_status, output = self._modify_deployment(vms, add_nodes=[node_name])

            if resp_status not in [200, 201, 202, 204]:
                _LOGGER.error("Error launching node %s: %s" % (node_name, output))
                return False
            else:
                _LOGGER.debug("Node %s successfully created" % node_name)
                # res = json.loads(output)

                # wait to assure the orchestrator process the operation
                delay = 2
                wait = 0
                timeout = 60
                new_uuids = []
                while not new_uuids and wait < timeout:
                    # Get the list of resources now to get the new vm added
                    resources = self._get_resources()
                    current_uuids = [vm.vm_id for vm in vms.values()]
                    for resource in resources:
                        if (resource['uuid'] not in self._get_master_node_id(resources) and
                                resource['uuid'] not in current_uuids):
                            new_uuids.append(resource['uuid'])
                    if len(new_uuids) < 1:
                        time.sleep(delay)
                        wait += delay

                if len(new_uuids) != 1:
                    _LOGGER.warning(
                        "Trying to get the uuids of the new node and get %d uuids!!" % len(new_uuids))
                else:
                    self._add_mvs_seen(node_name, self.VM_Node(new_uuids[0]))
                    return True
        except:
            _LOGGER.exception("Error launching node %s " % node_name)
            return False

    def _power_off(self, node_list):
        try:
            resp_status, output = self._modify_deployment(self._mvs_seen, remove_nodes=node_list)

            if resp_status not in [200, 201, 202, 204]:
                _LOGGER.error("ERROR deleting nodes: %s: %s" % (node_list, output))
                return False
            else:
                _LOGGER.debug("Nodes %s successfully deleted." % node_list)
                return True
        except:
            _LOGGER.exception("Error powering off nodes %s " % node_list)
            return False

    def power_off(self, nname):
        vmid = self._get_uuid_from_nodename(nname)
        if not vmid:
            _LOGGER.error("There is not any VM associated to node %s. Nothing to power off." % nname)
            return False, nname
        else:
            self._add_task(self.POWER_OFF, str(vmid))
            return True, nname

    def _get_template(self, count, remove_nodes, add_nodes):
        inf_id = self._get_inf_id()
        headers = {'Accept': 'text/plain', 'Connection': 'close'}
        auth = self._get_auth_header()
        if auth:
            headers.update(auth)

        url = "%s/%s" % (self._INDIGO_ORCHESTRATOR_URL, "deployments/%s/template" % inf_id)
        resp = requests.request("GET", url, headers=headers)

        if resp.status_code != 200:
            _LOGGER.error("ERROR getting deployment template: %s" %
                          str(resp.text))
            return None
        else:
            templateo = yaml.load(resp.text)
            node_name = self._find_wn_nodetemplate_name(templateo)
            node_template = templateo['topology_template']['node_templates'][node_name]

            if remove_nodes:
                if count < len(remove_nodes):
                    count = 1
                node_template['capabilities']['scalable']['properties']['count'] = count - len(remove_nodes)
                node_template['capabilities']['scalable']['properties']['removal_list'] = remove_nodes
            else:
                node_template['capabilities']['scalable']['properties']['count'] = count + len(add_nodes)
                # Put the dns name
                if 'endpoint' not in node_template['capabilities']:
                    node_template['capabilities']['endpoint'] = {}
                if 'properties' not in node_template['capabilities']['endpoint']:
                    node_template['capabilities']['endpoint']['properties'] = {}
                # TODO: see the dns_name issue
                if len(add_nodes) == 1:
                    node_template['capabilities']['endpoint']['properties']['dns_name'] = add_nodes[0]
                else:
                    node_template['capabilities']['endpoint']['properties']['dns_name'] = add_nodes

        return yaml.dump(templateo)

    def _find_wn_nodetemplate_name(self, template):
        try:
            for name, node in template['topology_template']['node_templates'].items():
                if node['type'].startswith("tosca.nodes.indigo.LRMS.WorkerNode"):
                    for req in node['requirements']:
                        if 'host' in req:
                            return req['host']
        except Exception:
            _LOGGER.exception("Error trying to get the WN template.")

        return None
