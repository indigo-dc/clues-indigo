import unittest
import os
from indigo_orchestrator import powermanager
from mock import MagicMock, Mock, patch, call

from clueslib.node import Node, NodeInfo
from cpyutils.db import DB_mysql
import indigo_orchestrator

def read_file_as_string(file_name):
    tests_path = os.path.dirname(os.path.abspath(__file__))
    abs_file_path = os.path.join(tests_path, file_name)
    return open(abs_file_path, 'r').read()

class TestMesosPlugin(unittest.TestCase):

    def test_powermanager_Task(self):
        task = powermanager.Task(powermanager.POWER_ON, 'test')
        assert task.nname == 'test'
        assert task.operation == powermanager.POWER_ON
        
    def test_powermanager_Task_cmp(self):
        task1 = powermanager.Task(powermanager.POWER_ON, 'test')
        task2 = powermanager.Task(powermanager.POWER_ON, 'test')
        task3 = powermanager.Task(powermanager.POWER_OFF, 'test')
        assert task1.__cmp__(task2) == 0
        assert task1.__cmp__(task3) == -1
        
    def test_powermanager_Task_str(self):
        task1 = powermanager.Task(powermanager.POWER_OFF, 'test')
        assert str(task1) == 'Power Off on test'
        task2 = powermanager.Task(powermanager.POWER_ON, 'test')
        assert str(task2) == 'Power On on test'        
        
    @patch('cpyutils.eventloop.now')        
    def test_powermanager_VmNode(self, mock_timer):
        mock_timer.return_value = 5
        vm = powermanager.VM_Node('1')
        assert vm.vm_id == "1"
        assert vm.timestamp_recovered == 0
        assert vm.timestamp_created == 5
        assert vm.timestamp_seen == 5
        
    def test_powermanager_get_auth_header(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._auth_data = {'username':'paco', 'password':'12345'}
        assert powermanager._get_auth_header(mock_pm) == {'Authorization': 'Basic cGFjbzoxMjM0NQ=='}

    def test_powermanager_power_on(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1", "test2", "test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 5
        assert powermanager.power_on(mock_pm, "test5") == (True, 'test5')
        
    def test_powermanager_power_on_max_vm(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1", "test2", "test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 1
        assert powermanager.power_on(mock_pm, "test2") == (False, 'test2')

    def test_powermanager_power_on_vm_exists(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1", "test2", "test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 5
        assert powermanager.power_on(mock_pm, "test2") == (True, 'test2')

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
        load_mvs_seen.return_value = {'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        load_pending_tasks.return_value = []
        cpyutils_db_create.return_value = None
        get_resources_page.side_effect = self.get_resources_page
        vms = powermanager()._get_vms()
        assert vms["vnode1"].timestamp_seen == 1.0
        
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
        load_mvs_seen.return_value = {'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
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
        
        assert str(pm._pending_tasks[0]) == "Power Off on ee6a8510-974c-411c-b8ff-71bb133148eb"


    def test_load_pending_tasks_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._db = MagicMock(DB_mysql)
        mock_pm._db.sql_query.return_value = False, None, {}
        assert powermanager._load_pending_tasks(mock_pm) == []
        
    def test_load_pending_tasks(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._db = MagicMock(DB_mysql)
        mock_pm._db.sql_query.return_value = True, None, [{'task1', 'POWER_ON'}, {'task2', 'POWER_OFF'}]
        powermanager._load_pending_tasks(mock_pm)
        assert mock_pm.Task.call_count == 2
        
        expected = [call('task1', 'POWER_ON'), call('POWER_OFF', 'task2')]
        assert mock_pm.Task.call_args_list == expected
 
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
                       load_pending_tasks, create_db, cpyutils_db_create, now, delete_task, power_on):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        cpyutils_db_create.return_value = None
        get_resources_page.side_effect = self.get_resources_page
        get_deployment_status.return_value = "CREATE_COMPLETE"
        delete_task.return_value = True
        power_on.return_value = True

        task1 = powermanager.Task(powermanager.POWER_ON, 'task1')
        task2 = powermanager.Task(powermanager.POWER_OFF, 'task2')
        load_pending_tasks.return_value = [task1, task2]
        
        powermanager()._process_pending_tasks()
        
        assert delete_task.call_args_list == [call(task1)]        
        assert power_on.call_args_list == [call('task1')]
        
    @patch('indigo_orchestrator.powermanager._power_off')
    @patch('indigo_orchestrator.powermanager._delete_task') 
    @patch('cpyutils.eventloop.now')
    @patch('cpyutils.db.DB.create_from_string')
    @patch('indigo_orchestrator.powermanager._create_db')
    @patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @patch('indigo_orchestrator.powermanager._get_resources_page')
    @patch('indigo_orchestrator.powermanager._get_deployment_status')
    def test_process_pending_tasks_power_off(self, get_deployment_status, get_resources_page, load_mvs_seen,
                       load_pending_tasks, create_db, cpyutils_db_create, now, delete_task, power_off):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        cpyutils_db_create.return_value = None
        get_resources_page.side_effect = self.get_resources_page
        get_deployment_status.return_value = "CREATE_COMPLETE"
        delete_task.return_value = True
        power_off.return_value = True

        task1 = powermanager.Task(powermanager.POWER_ON, 'task1')
        task2 = powermanager.Task(powermanager.POWER_OFF, 'task2')
        load_pending_tasks.return_value = [task2, task1]
        
        powermanager()._process_pending_tasks()
        
        assert delete_task.call_args_list == [call(task2)]
        assert power_off.call_args_list == [call(['task2'])]
    
    def test_power_off(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._modify_deployment.return_value = 200, 'test'
        mock_pm._mvs_seen = {}        
        assert powermanager._power_off(mock_pm, ['task2']) == True
        
    def test_power_off_error(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._modify_deployment.return_value = 404, 'test'
        mock_pm._mvs_seen = {}        
        assert powermanager._power_off(mock_pm, ['task2']) == False
        
    def test_power_off_exception(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._modify_deployment.side_effect = Exception()
        mock_pm._mvs_seen = {}        
        assert powermanager._power_off(mock_pm, ['task2']) == False
        

if __name__ == '__main__':
    unittest.main()
