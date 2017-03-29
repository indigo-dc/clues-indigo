import unittest
import os
from indigo_orchestrator import powermanager
from mock import MagicMock, Mock, patch, call
import json
from StringIO import StringIO
import logging
import httplib
import yaml

from clueslib.node import Node, NodeInfo
from cpyutils.db import DB_mysql


def read_file_as_string(file_name):
    tests_path = os.path.dirname(os.path.abspath(__file__))
    abs_file_path = os.path.join(tests_path, file_name)
    return open(abs_file_path, 'r').read()


def read_file_as_json(file_name):
    return json.loads(read_file_as_string(file_name))


def read_file_as_yaml(file_name):
    return yaml.load(read_file_as_string(file_name))


class TestMesosPlugin(unittest.TestCase):

    @classmethod
    def setUp(cls):
        cls.get_resources_call_count = 0
        cls.log = StringIO()
        ch = logging.StreamHandler(cls.log)
        cls.ch = ch
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)

        logging.RootLogger.propagate = 0
        logging.root.setLevel(logging.ERROR)

        logger = logging.getLogger("[PLUGIN-INDIGO-ORCHESTRATOR]")
        logger.setLevel(logging.DEBUG)
        logger.propagate = 0
        logger.addHandler(ch)

    def test_powermanager_Task(self):
        task = powermanager.Task(powermanager.POWER_ON, 'test')

        self.assertEquals(task.nname, 'test')
        self.assertEquals(task.operation, powermanager.POWER_ON)

    def test_powermanager_Task_cmp(self):
        task1 = powermanager.Task(powermanager.POWER_ON, 'test')
        task2 = powermanager.Task(powermanager.POWER_ON, 'test')
        task3 = powermanager.Task(powermanager.POWER_OFF, 'test')

        self.assertEquals(task1.__cmp__(task2), 0)
        self.assertEquals(task1.__cmp__(task3), -1)

    def test_powermanager_Task_str(self):
        task1 = powermanager.Task(powermanager.POWER_OFF, 'test')
        task2 = powermanager.Task(powermanager.POWER_ON, 'test')

        self.assertEquals(str(task1), 'Power Off on test')
        self.assertEquals(str(task2), 'Power On on test')

    @patch('cpyutils.eventloop.now')
    def test_powermanager_VmNode(self, mock_timer):
        mock_timer.return_value = 5
        vm = powermanager.VM_Node('1')

        self.assertEquals(vm.vm_id, "1")
        self.assertEquals(vm.timestamp_recovered, 0)
        self.assertEquals(vm.timestamp_created, 5)
        self.assertEquals(vm.timestamp_seen, 5)

    def test_powermanager_power_on(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1", "test2", "test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 5

        self.assertEquals(
            powermanager.power_on(mock_pm, "test5"), (True, 'test5'))

    def test_powermanager_power_on_max_vm(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1", "test2", "test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 1

        self.assertEquals(
            powermanager.power_on(mock_pm, "test2"), (False, 'test2'))

    def test_powermanager_power_on_vm_exists(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1", "test2", "test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 5

        self.assertEquals(
            powermanager.power_on(mock_pm, "test2"), (True, 'test2'))

    def get_resources_page(self, page=0):
        return 200, read_file_as_string("test-files/orchestrator-resources-p%d.json" % page)

    @patch('cpyutils.eventloop.now')
    @patch('cpyutils.db.DB.create_from_string')
    @patch('indigo_orchestrator.powermanager._create_db')
    @patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @patch('indigo_orchestrator.powermanager._get_resources_page')
    def test_get_vms(self, get_resources_page, load_mvs_seen, load_pending_tasks, create_db, cpyutils_db_create, now):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {
            'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        load_pending_tasks.return_value = []
        cpyutils_db_create.return_value = None
        get_resources_page.side_effect = self.get_resources_page
        vms = powermanager()._get_vms()
        self.assertEquals(vms["vnode1"].timestamp_seen, 1.0)

    @patch('cpyutils.eventloop.now')
    @patch('cpyutils.db.DB.create_from_string')
    @patch('indigo_orchestrator.powermanager._create_db')
    @patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @patch('indigo_orchestrator.powermanager._get_resources_page')
    @patch('indigo_orchestrator.powermanager._get_deployment_status')
    @patch('indigo_orchestrator.powermanager._process_pending_tasks')
    def test_lifecycle(self, process_pending_tasks, get_deployment_status, get_resources_page, load_mvs_seen,
                       load_pending_tasks, create_db, cpyutils_db_create, now):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {
            'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        load_pending_tasks.return_value = []
        cpyutils_db_create.return_value = None
        get_resources_page.side_effect = self.get_resources_page
        get_deployment_status.return_value = "CREATE_COMPLETE"
        process_pending_tasks.return_value = True
        pm = powermanager()

        pm._clues_daemon = MagicMock()
        pm._db = MagicMock()
        pm._db.sql_query = Mock(return_value=True)
        monitoring_info = MagicMock()
        node = Node("vnode1", 1, 1, 512, 512)
        node.set_state(NodeInfo.OFF)
        monitoring_info.nodelist = {node}
        pm._clues_daemon.get_monitoring_info.return_value = monitoring_info
        now.return_value = 10000.0

        pm.lifecycle()

        self.assertEquals(
            str(pm._pending_tasks[0]), "Power Off on ee6a8510-974c-411c-b8ff-71bb133148eb")

    def test_load_pending_tasks_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._db = MagicMock(DB_mysql)
        mock_pm._db.sql_query.return_value = False, None, {}

        self.assertEquals(powermanager._load_pending_tasks(mock_pm), [])
        self.assertIn(
            "Error trying to load INDIGO orchestrator tasks data", self.log.getvalue())

    def test_load_pending_tasks(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._db = MagicMock(DB_mysql)
        mock_pm._db.sql_query.return_value = True, None, [
            {'task1', 'POWER_ON'}, {'task2', 'POWER_OFF'}]
        powermanager._load_pending_tasks(mock_pm)

        self.assertEquals(mock_pm.Task.call_count, 2)
        self.assertEquals(mock_pm.Task.call_args_list, [
                          call('task1', 'POWER_ON'), call('POWER_OFF', 'task2')])

    def test_load_mvs_seen(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._db = MagicMock(DB_mysql)
        mock_pm._db.sql_query.return_value = True, None, [
            {'vnode1', 'ee6a8510-974c-411c-b8ff-71bb133148eb'}]
        powermanager._load_mvs_seen(mock_pm)

        self.assertEquals(mock_pm.VM_Node.call_count, 1)
        self.assertEquals(
            mock_pm.VM_Node.call_args_list, [call('ee6a8510-974c-411c-b8ff-71bb133148eb')])

    @patch('indigo_orchestrator.powermanager._power_on')
    @patch('indigo_orchestrator.powermanager._delete_task')
    @patch('cpyutils.eventloop.now')
    @patch('cpyutils.db.DB.create_from_string')
    @patch('indigo_orchestrator.powermanager._create_db')
    @patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @patch('indigo_orchestrator.powermanager._get_resources_page')
    @patch('indigo_orchestrator.powermanager._get_deployment_status')
    def test_process_pending_tasks_power_on(self, get_deployment_status, get_resources_page, load_mvs_seen,
                                            load_pending_tasks, create_db, cpyutils_db_create, now,
                                            delete_task, power_on):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {
            'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        cpyutils_db_create.return_value = None
        get_resources_page.side_effect = self.get_resources_page
        get_deployment_status.return_value = "CREATE_COMPLETE"
        delete_task.return_value = True
        power_on.return_value = True

        task1 = powermanager.Task(powermanager.POWER_ON, 'node1')
        task2 = powermanager.Task(powermanager.POWER_OFF, 'node2')
        load_pending_tasks.return_value = [task1, task2]

        monitoring_info = MagicMock()
        powermanager()._process_pending_tasks(monitoring_info)

        self.assertEquals(delete_task.call_args_list, [call(task1)])
        self.assertEquals(power_on.call_args_list, [call('node1')])
        self.assertIn("Processing pending tasks:", self.log.getvalue())
        self.assertIn(
            "Task Power On on node1 correctly processed", self.log.getvalue())

    def get_nodename_from_uuid(self, uuid):
        return uuid

    @patch('indigo_orchestrator.powermanager._power_off')
    @patch('indigo_orchestrator.powermanager._delete_task')
    @patch('cpyutils.eventloop.now')
    @patch('cpyutils.db.DB.create_from_string')
    @patch('indigo_orchestrator.powermanager._create_db')
    @patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @patch('indigo_orchestrator.powermanager._get_resources_page')
    @patch('indigo_orchestrator.powermanager._get_deployment_status')
    @patch('indigo_orchestrator.powermanager._get_nodename_from_uuid')
    def test_process_pending_tasks_power_off(self, get_nodename_from_uuid, get_deployment_status,
                                             get_resources_page, load_mvs_seen, load_pending_tasks,
                                             create_db, cpyutils_db_create, now,
                                             delete_task, power_off):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {
            'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        cpyutils_db_create.return_value = None
        get_resources_page.side_effect = self.get_resources_page
        get_deployment_status.return_value = "CREATE_COMPLETE"
        delete_task.return_value = True
        power_off.return_value = True

        task1 = powermanager.Task(powermanager.POWER_ON, 'node1')
        task2 = powermanager.Task(powermanager.POWER_OFF, 'node2')
        task3 = powermanager.Task(powermanager.POWER_ON, 'node3')
        task4 = powermanager.Task(powermanager.POWER_OFF, 'node4')
        task5 = powermanager.Task(powermanager.POWER_OFF, 'node5')
        task6 = powermanager.Task(powermanager.POWER_OFF, 'node6')
        load_pending_tasks.return_value = [task6, task5, task4, task3, task2, task1]

        node1 = MagicMock()
        node1.name = "node4"
        node1.state = 0
        node2 = MagicMock()
        node2.name = "node5"
        node2.state = 0
        node3 = MagicMock()
        node3.name = "node6"
        node3.state = 1
        monitoring_info = MagicMock()
        monitoring_info.nodelist = [node1, node2, node3]

        get_nodename_from_uuid.side_effect = self.get_nodename_from_uuid

        powermanager()._process_pending_tasks(monitoring_info)

        self.assertEquals(delete_task.call_args_list, [call(task6), call(task5), call(task4)])
        self.assertEquals(power_off.call_args_list, [call(['node5', 'node4'])])
        self.assertIn("Processing pending tasks:", self.log.getvalue())
        self.assertIn(
            "Tasks PowerOff node5,node4 correctly processed", self.log.getvalue())
        self.assertIn(
            "Node node6 is currently used, discard poweroff operation", self.log.getvalue())

        task1 = powermanager.Task(powermanager.POWER_OFF, 'node7')
        load_pending_tasks.return_value = [task1]

        node1 = MagicMock()
        node1.name = "node7"
        node1.state = 0
        monitoring_info = MagicMock()
        monitoring_info.nodelist = [node1]
        powermanager()._process_pending_tasks(monitoring_info)

        self.assertEquals(delete_task.call_args_list[3], call(task1))
        self.assertEquals(len(power_off.call_args_list), 2)
        self.assertEquals(power_off.call_args_list[1], call(['node7']))
        self.assertIn(
            "Tasks PowerOff node7 correctly processed", self.log.getvalue())

        task1 = powermanager.Task(powermanager.POWER_OFF, 'node8')
        load_pending_tasks.return_value = [task1]

        node1 = MagicMock()
        node1.name = "node8"
        node1.state = 1
        monitoring_info = MagicMock()
        monitoring_info.nodelist = [node1]
        powermanager()._process_pending_tasks(monitoring_info)

        self.assertEquals(delete_task.call_args_list[4], call(task1))
        self.assertEquals(len(power_off.call_args_list), 2)
        self.assertIn(
            "Node node8 is currently used, discard poweroff operation", self.log.getvalue())

    def test_power_off(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._modify_deployment.return_value = 200, 'test'
        mock_pm._mvs_seen = {}

        self.assertEquals(powermanager._power_off(mock_pm, ['task2']), True)
        self.assertIn(
            "Nodes ['task2'] successfully deleted", self.log.getvalue())

    def test_power_off_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._modify_deployment.return_value = 404, 'test'
        mock_pm._mvs_seen = {}

        self.assertEquals(powermanager._power_off(mock_pm, ['task2']), False)
        self.assertIn(
            "ERROR deleting nodes: ['task2']: test", self.log.getvalue())

    def test_power_off_exception(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._modify_deployment.side_effect = Exception()
        mock_pm._mvs_seen = {}

        self.assertEquals(powermanager._power_off(mock_pm, ['task2']), False)
        self.assertIn(
            "Error powering off nodes ['task2']", self.log.getvalue())

    @patch('indigo_orchestrator.powermanager._power_off')
    @patch('indigo_orchestrator.powermanager._delete_task')
    @patch('cpyutils.eventloop.now')
    @patch('cpyutils.db.DB.create_from_string')
    @patch('indigo_orchestrator.powermanager._create_db')
    @patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @patch('indigo_orchestrator.powermanager._get_resources')
    @patch('indigo_orchestrator.powermanager._get_deployment_status')
    @patch('indigo_orchestrator.powermanager._modify_deployment')
    def test_power_on_timeout(self, modify_deployment, get_deployment_status, get_resources, load_mvs_seen,
                              load_pending_tasks, create_db, cpyutils_db_create, now, delete_task, power_off):

        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {
            'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        cpyutils_db_create.return_value = None
        get_deployment_status.return_value = "CREATE_COMPLETE"
        delete_task.return_value = True
        power_off.return_value = True
        get_resources.return_value = read_file_as_json(
            "test-files/get-resources-output.json")
        modify_deployment.return_value = 200, 'test'
        powermanager()._power_on('vnode1')
        self.assertIn("Node vnode1 successfully created", self.log.getvalue())
        self.assertIn(
            "Trying to get the uuids of the new node and get no new uuids", self.log.getvalue())

    def get_resources(self):
        if self.get_resources_call_count == 0:
            self.get_resources_call_count = 1
            return read_file_as_json("test-files/get-resources-output.json")
        else:
            return read_file_as_json("test-files/get-resources-output2.json")

    @patch('indigo_orchestrator.powermanager._add_mvs_seen')
    @patch('indigo_orchestrator.powermanager._power_off')
    @patch('indigo_orchestrator.powermanager._delete_task')
    @patch('cpyutils.eventloop.now')
    @patch('cpyutils.db.DB.create_from_string')
    @patch('indigo_orchestrator.powermanager._create_db')
    @patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @patch('indigo_orchestrator.powermanager._get_resources')
    @patch('indigo_orchestrator.powermanager._get_deployment_status')
    @patch('indigo_orchestrator.powermanager._modify_deployment')
    def test_power_on(self, modify_deployment, get_deployment_status, get_resources, load_mvs_seen,
                      load_pending_tasks, create_db, cpyutils_db_create, now, delete_task, power_off, add_mvs_seen):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {
            'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148aa')}
        cpyutils_db_create.return_value = None
        get_deployment_status.return_value = "CREATE_COMPLETE"
        delete_task.return_value = True
        power_off.return_value = True
        get_resources.side_effect = self.get_resources
        modify_deployment.return_value = 200, 'test'
        self.assertEquals(powermanager()._power_on('vnode1'), True)
        self.assertIn("Node vnode1 successfully created", self.log.getvalue())

    def test_get_resources_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_resources_page.return_value = 404, 'test'
        self.assertEquals(powermanager._get_resources(mock_pm), [])
        self.assertIn(
            "ERROR getting deployment info: test", self.log.getvalue())

    def test_create_db(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._db = MagicMock()
        mock_pm._db.sql_query.return_value = (True, "", "")
        powermanager._create_db(mock_pm)

        call1 = call(
            'CREATE TABLE IF NOT EXISTS orchestrator_vms(node_name varchar(128) PRIMARY KEY, uuid varchar(128))', True)
        call2 = call(
            'CREATE TABLE IF NOT EXISTS orchestrator_tasks(node_name varchar(128), operation int)', True)
        call3 = call(
            'CREATE TABLE IF NOT EXISTS orchestrator_token(token BLOB, num int)', True)
        self.assertEquals(mock_pm._db.sql_query.call_args_list, [call1, call2, call3])

    def test_create_db_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._db = MagicMock()
        powermanager._create_db(mock_pm)
        self.assertIn(
            "Error creating INDIGO orchestrator plugin DB", self.log.getvalue())

    @patch('requests.request')
    def test_get_deployment_status_error(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'ORCH_ID'
        mock_pm._get_auth_header.return_value = None
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"
        powermanager._get_deployment_status(mock_pm)

        self.assertEquals(requests.call_args_list,
                          [call('GET', 'https://localhost/orchestrator/deployments/ORCH_ID',
                                headers={'Connection': 'close', 'Accept': 'application/json'})])
        self.assertIn("ERROR getting deployment status:", self.log.getvalue())

    @patch('requests.request')
    def test_get_deployment_status(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'ORCH_ID'
        mock_pm._get_auth_header.return_value = None
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status" : "test_stat"}'
        requests.return_value = mock_response

        self.assertEquals(
            powermanager._get_deployment_status(mock_pm), "test_stat")
        self.assertEquals(requests.call_args_list,
                          [call('GET', 'https://localhost/orchestrator/deployments/ORCH_ID',
                                headers={'Connection': 'close', 'Accept': 'application/json'})])
        self.assertIn("Deployment in status: test_stat", self.log.getvalue())

    def test_delete_mvs_seen(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = {
            'test_name_0': '0', 'test_name_1': '1', 'test_name_2': '2'}
        mock_pm._db = MagicMock()
        mock_pm._db.sql_query.return_value = (True, "", "")
        powermanager._delete_mvs_seen(mock_pm, 'test_name_1')

        self.assertEquals(
            mock_pm._mvs_seen, {'test_name_0': '0', 'test_name_2': '2'})
        self.assertEquals(mock_pm._db.sql_query.call_args_list,
                          [call("DELETE FROM orchestrator_vms WHERE node_name = 'test_name_1'", True)])

    def test_delete_mvs_seen_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = {
            'test_name_0': '0', 'test_name_1': '1', 'test_name_2': '2'}
        powermanager._delete_mvs_seen(mock_pm, 'test_name_1')
        self.assertIn(
            "Error trying to save INDIGO orchestrator plugin data", self.log.getvalue())

    def test_add_mvs_seen(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = {'test_name_0': '0'}
        mock_pm._db = MagicMock()
        mock_pm._db.sql_query.return_value = (True, "", "")
        mock_vm = MagicMock()
        mock_vm.vm_id = 1
        powermanager._add_mvs_seen(mock_pm, 'test_name_1', mock_vm)

        self.assertEquals(
            mock_pm._mvs_seen, {'test_name_0': '0', 'test_name_1': mock_vm})
        self.assertEquals(mock_pm._db.sql_query.call_args_list,
                          [call("INSERT INTO orchestrator_vms VALUES ('test_name_1', '1')", True)])

    def test_add_mvs_seen_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = {'test_name_0': '0'}
        powermanager._add_mvs_seen(mock_pm, 'test_name_1', '1')
        self.assertIn(
            "Error trying to save INDIGO orchestrator plugin data", self.log.getvalue())

    @patch('requests.request')
    def test_modify_deployment(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'TEST_ID'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status" : "test_stat"}'
        requests.return_value = mock_response

        mock_pm._get_auth_header.return_value = None
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"
        mock_pm._get_template.return_value = 'test_template\n"test_parser"'

        self.assertEquals(powermanager._modify_deployment(
            mock_pm, ['1', '2']), (200, '{"status" : "test_stat"}'))
        self.assertIn('test_template\n"test_parser"', self.log.getvalue())
        self.assertEquals(requests.call_args_list,
                          [call('PUT', 'https://localhost/orchestrator/deployments/TEST_ID',
                                data='{ "template": "test_template\\n\\"test_parser\\"" }',
                                headers={'Connection': 'close', 'Content-Type': 'application/json',
                                         'Accept': 'application/json'})])

    def test_find_wn_nodetemplate_name(self):
        mock_pm = MagicMock(powermanager)
        template = read_file_as_yaml('test-files/tosca_template.yaml')
        self.assertEquals(
            powermanager._find_wn_nodetemplate_name(mock_pm, template), 'torque_wn')

    def test_find_wn_nodetemplate_name_error(self):
        mock_pm = MagicMock(powermanager)
        powermanager._find_wn_nodetemplate_name(mock_pm, '')
        self.assertIn(
            'Error trying to get the WN template', self.log.getvalue())

    @patch('requests.request')
    def test_get_template_no_node_changes(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'TEST_ID'
        mock_pm._get_auth_header.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = read_file_as_string('test-files/tosca_template.yaml')
        requests.return_value = mock_response
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"

        mock_pm._find_wn_nodetemplate_name.return_value = 'torque_wn'
        self.assertEquals(powermanager._get_template(mock_pm, 0, [], []),
                          read_file_as_string('test-files/template_result_no_node_changes'))
        self.assertEquals(requests.call_args_list,
                          [call('GET', 'https://localhost/orchestrator/deployments/TEST_ID/template',
                                headers={'Connection': 'close', 'Accept': 'text/plain'})])

    @patch('requests.request')
    def test_get_template_error(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'TEST_ID'
        mock_pm._get_auth_header.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = 'test'
        requests.return_value = mock_response
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"

        mock_pm._find_wn_nodetemplate_name.return_value = 'torque_wn'
        powermanager._get_template(mock_pm, 0, [], [])

        self.assertIn(
            'ERROR getting deployment template: test', self.log.getvalue())

    @patch('requests.request')
    def test_get_template_add_one_node(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'TEST_ID'
        mock_pm._get_auth_header.return_value = None

        mock_response = MagicMock(httplib.HTTPResponse)
        mock_response.status_code = 200
        mock_response.text = read_file_as_string('test-files/tosca_template.yaml')
        requests.return_value = mock_response
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"

        mock_pm._find_wn_nodetemplate_name.return_value = 'torque_wn'

        self.assertEquals(powermanager._get_template(mock_pm, 0, [], ['test_node']),
                          read_file_as_string('test-files/template_result_add_one_node'))
        self.assertEquals(requests.call_args_list,
                          [call('GET', 'https://localhost/orchestrator/deployments/TEST_ID/template',
                                headers={'Connection': 'close', 'Accept': 'text/plain'})])

    @patch('requests.request')
    def test_get_template_add_several_nodes(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'TEST_ID'
        mock_pm._get_auth_header.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = read_file_as_string(
            'test-files/tosca_template.yaml')
        requests.return_value = mock_response
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"

        mock_pm._find_wn_nodetemplate_name.return_value = 'torque_wn'

        self.assertEquals(powermanager._get_template(mock_pm, 0, [],
                                                     ['test_node_1', 'test_node_1', 'test_node_2']),
                          read_file_as_string('test-files/template_result_add_several_nodes'))

        self.assertEquals(requests.call_args_list,
                          [call('GET', 'https://localhost/orchestrator/deployments/TEST_ID/template',
                                headers={'Connection': 'close', 'Accept': 'text/plain'})])

    @patch('requests.request')
    def test_get_template_remove_nodes(self, requests):
        mock_pm = MagicMock(powermanager)
        mock_pm._get_inf_id.return_value = 'TEST_ID'
        mock_pm._get_auth_header.return_value = None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = read_file_as_string(
            'test-files/tosca_template.yaml')
        requests.return_value = mock_response
        mock_pm._INDIGO_ORCHESTRATOR_URL = "https://localhost/orchestrator"

        mock_pm._find_wn_nodetemplate_name.return_value = 'torque_wn'

        self.assertEquals(powermanager._get_template(mock_pm, 1, ['test_node_1', 'test_node_1'], []),
                          read_file_as_string('test-files/template_result_remove_nodes'))
        self.assertEquals(requests.call_args_list,
                          [call('GET', 'https://localhost/orchestrator/deployments/TEST_ID/template',
                                headers={'Connection': 'close', 'Accept': 'text/plain'})])

    @patch('requests.request')
    def test_get_refresh_token(self, requests):
        mock_pm = MagicMock(powermanager)
        access_token = ("eyJraWQiOiJyc2ExIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJkYzVkNWFiNy02ZGI5LTQwNzktOTg1Yy04MGF"
                        "jMDUwMTcwNjYiLCJpc3MiOiJodHRwczpcL1wvaWFtLXRlc3QuaW5kaWdvLWRhdGFjbG91ZC5ldVwvIiwiZXhwI"
                        "joxNDY1NDcxMzU0LCJpYXQiOjE0NjU0Njc3NTUsImp0aSI6IjA3YjlkYmE4LTc3NWMtNGI5OS1iN2QzLTk4Njg"
                        "5ODM1N2FiYSJ9.DwpZizVaYtvIj7fagQqDFpDh96szFupf6BNMIVLcopqQtZ9dBvwN9lgZ_w7Htvb3r-erho_hc"
                        "me5mqDMVbSKwsA2GiHfiXSnh9jmNNVaVjcvSPNVGF8jkKNxeSSgoT3wED8xt4oU4s5MYiR075-RAkt6AcWqVbXU"
                        "z5BzxBvANko")
        mock_pm._auth_data = access_token
        mock_pm._client_id = "cid"
        mock_pm._client_secret = "csec"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = {
            "access_token": "access_token",
            "refresh_token": "refresh_token",
        }
        requests.return_value = mock_response

        self.assertTrue(powermanager._get_refresh_token(mock_pm))
        self.assertEquals(requests.call_args_list,
                          [call('POST', u'https://iam-test.indigo-datacloud.eu//token',
                                data=('client_id=cid&client_secret=csec&grant_type=urn%3Aietf%3Aparams%3Aoauth%3A'
                                      'grant-type%3Atoken-exchange&subject_token=' + access_token + '&scope'
                                      '=openid profile offline_access'),
                                headers={'content-type': 'application/x-www-form-urlencoded'}, verify=False)])

    @patch('requests.request')
    def test_refresh_access_token(self, requests):
        mock_pm = MagicMock(powermanager)
        access_token = ("eyJraWQiOiJyc2ExIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJkYzVkNWFiNy02ZGI5LTQwNzktOTg1Yy04MGF"
                        "jMDUwMTcwNjYiLCJpc3MiOiJodHRwczpcL1wvaWFtLXRlc3QuaW5kaWdvLWRhdGFjbG91ZC5ldVwvIiwiZXhwI"
                        "joxNDY1NDcxMzU0LCJpYXQiOjE0NjU0Njc3NTUsImp0aSI6IjA3YjlkYmE4LTc3NWMtNGI5OS1iN2QzLTk4Njg"
                        "5ODM1N2FiYSJ9.DwpZizVaYtvIj7fagQqDFpDh96szFupf6BNMIVLcopqQtZ9dBvwN9lgZ_w7Htvb3r-erho_hc"
                        "me5mqDMVbSKwsA2GiHfiXSnh9jmNNVaVjcvSPNVGF8jkKNxeSSgoT3wED8xt4oU4s5MYiR075-RAkt6AcWqVbXU"
                        "z5BzxBvANko")
        mock_pm._auth_data = access_token
        mock_pm._refresh_token = "refresh_token"
        mock_pm._client_id = "cid"
        mock_pm._client_secret = "csec"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = {
            "access_token": "access_token",
        }
        requests.return_value = mock_response

        self.assertTrue(powermanager._refresh_access_token(mock_pm))
        self.assertEquals(requests.call_args_list,
                          [call('POST', u'https://iam-test.indigo-datacloud.eu//token',
                                data=('client_id=cid&client_secret=csec&grant_type=refresh_token&'
                                      'scope=openid profile offline_access&refresh_token=refresh_token'),
                                headers={'content-type': 'application/x-www-form-urlencoded'}, verify=False)])

    def test_is_access_token_to_expire(self):
        mock_pm = MagicMock(powermanager)
        access_token = ("eyJraWQiOiJyc2ExIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiJkYzVkNWFiNy02ZGI5LTQwNzktOTg1Yy04MGF"
                        "jMDUwMTcwNjYiLCJpc3MiOiJodHRwczpcL1wvaWFtLXRlc3QuaW5kaWdvLWRhdGFjbG91ZC5ldVwvIiwiZXhwI"
                        "joxNDY1NDcxMzU0LCJpYXQiOjE0NjU0Njc3NTUsImp0aSI6IjA3YjlkYmE4LTc3NWMtNGI5OS1iN2QzLTk4Njg"
                        "5ODM1N2FiYSJ9.DwpZizVaYtvIj7fagQqDFpDh96szFupf6BNMIVLcopqQtZ9dBvwN9lgZ_w7Htvb3r-erho_hc"
                        "me5mqDMVbSKwsA2GiHfiXSnh9jmNNVaVjcvSPNVGF8jkKNxeSSgoT3wED8xt4oU4s5MYiR075-RAkt6AcWqVbXU"
                        "z5BzxBvANko")
        mock_pm._auth_data = access_token
        mock_pm._refresh_time_diff = 300

        self.assertTrue(powermanager._is_access_token_to_expire(mock_pm))

    def test_get_master_node_id(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._master_nodes_ids = []
        resources = [{u'uuid': u'8fef4c1c-18c6-4091-9b8f-5d5e48bcef31', u'creationTime': u'2017-03-22T15:29+0000'},
                     {u'uuid': u'8e1304bf-916c-4587-88e8-44bb27ea6720', u'creationTime': u'2017-03-22T15:18+0000'},
                     {u'uuid': u'58d0dfa3-50e4-4e64-8237-819fce6fe8ec', u'creationTime': u'2017-03-22T15:00+0000'},
                     {u'uuid': u'ee650cbf-f942-49b6-8fbf-096f06cab7d8', u'creationTime': u'2017-03-22T14:33+0000'},
                     {u'uuid': u'ac44b30a-f00b-4b6c-8b25-ab3852883046', u'creationTime': u'2017-03-22T14:33+0000'}]
        masters = powermanager._get_master_node_id(mock_pm, resources)
        expected_res = [u'ee650cbf-f942-49b6-8fbf-096f06cab7d8', u'ac44b30a-f00b-4b6c-8b25-ab3852883046']
        self.assertEquals(masters, expected_res)

if __name__ == '__main__':
    unittest.main()
